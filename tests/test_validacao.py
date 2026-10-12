# -*- coding: utf-8 -*-
"""Testes da validação retrospectiva (sem rede: DBF escrito aqui, CPC simulada, internações sintéticas)."""
import json
import shutil
import struct
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from climasenior import brasil as B                          # noqa: E402
from climasenior import sih as SIH                           # noqa: E402
from climasenior import validacao as V                       # noqa: E402
from climasenior.simulacao_br import ClienteSimuladoBrasil   # noqa: E402

CAMPOS = [("UF_ZI", 6), ("IDENT", 1), ("MUNIC_RES", 6), ("NASC", 8), ("DT_INTER", 8), ("DIAG_PRINC", 4),
          ("CAR_INT", 2), ("COD_IDADE", 1), ("IDADE", 2), ("MORTE", 1)]


def escrever_dbf(caminho, linhas, apagadas=()):
    """DBF dBase III mínimo, no layout do RD do SIH (só campos de texto)."""
    tam_reg = 1 + sum(t for _, t in CAMPOS)
    cab = struct.pack("<B3BIHH20x", 3, 124, 1, 1, len(linhas), 32 + 32 * len(CAMPOS) + 1, tam_reg)
    desc = b"".join(n.encode().ljust(11, b"\x00") + b"C" + b"\x00" * 4 + bytes([t, 0]) + b"\x00" * 14 for n, t in CAMPOS)
    regs = b""
    for k, l in enumerate(linhas):
        regs += (b"*" if k in apagadas else b" ") + b"".join(str(l.get(n, "")).encode("latin1").ljust(t)[:t] for n, t in CAMPOS)
    Path(caminho).write_bytes(cab + desc + b"\x0d" + regs + b"\x1a")


def _linha(mun, dt, diag, idade, ident="1", car="02", cod="4"):
    return {"IDENT": ident, "MUNIC_RES": mun, "NASC": "19500101", "DT_INTER": dt, "DIAG_PRINC": diag,
            "CAR_INT": car, "COD_IDADE": cod, "IDADE": str(idade).rjust(2)}


def test_dbf_e_agregacao(tmp_path):
    linhas = [
        _linha("211130", "20240110", "E86 ", 70),        # calor e todas
        _linha("211130", "20240110", "N390", 81),        # calor (infecção urinária) e todas
        _linha("211130", "20240110", "I10 ", 65),        # circulatório e todas
        _linha("211130", "20240111", "J18 ", 60),        # respiratório e todas
        _linha("211130", "20240111", "S72 ", 90),        # fratura: fora de todas
        _linha("211130", "20240111", "T67 ", 77),        # efeito do calor: calor e todas
        _linha("211130", "20240111", "E86 ", 59),        # menor de 60: fora
        _linha("211130", "20240111", "E86 ", 70, car="01"),   # eletiva: fora
        _linha("211130", "20240111", "E86 ", 70, ident="5"),  # longa permanência: fora
        _linha("211130", "20240111", "E86 ", 2, cod="5"),     # 102 anos: dentro
        _linha("220040", "20240112", "A41 ", 66),        # outro município
        _linha("220040", "20240112", "E86 ", 66),        # apagado no DBF
    ]
    arq = tmp_path / "RD.dbf"
    escrever_dbf(arq, linhas, apagadas={11})
    col = SIH.ler_dbf(arq, ["DIAG_PRINC", "DT_INTER", "NAO_EXISTE"])
    assert len(col["DIAG_PRINC"]) == 11 and col["NAO_EXISTE"] is None
    df, info = SIH.agregar_dbf(arq)
    assert info["registros"] == 11 and info["idosos_urgencia"] == 8
    d = df.set_index(["mun6", "data"])
    assert d.loc[(211130, 20240110)].tolist() == [2, 1, 0, 3]      # calor, circ, resp, todas
    assert d.loc[(211130, 20240111)].tolist() == [2, 0, 1, 3]
    assert d.loc[(220040, 20240112)].tolist() == [1, 0, 0, 1]


def test_coletar_com_fonte_falsa(tmp_path):
    class Fonte:
        def listar(self, prefixo):
            return ["RDMA2401.dbc", "RDMA2402.dbc", "RDPI2401.dbc", "RDMA2301.dbc"]

        def baixar(self, nome, destino):
            if nome == "RDMA2402.dbc":
                raise SIH.ErroSIH("conexão caiu")
            escrever_dbf(destino, [_linha("211130" if "MA" in nome else "220040", "20240105", "E87 ", 72)])

    man = SIH.coletar(2024, tmp_path, ufs=["MA", "PI"], fonte=Fonte(), descompactar=shutil.copy, log=lambda *a: None)
    assert set(man["arquivos"]) == {"RDMA2401.DBC", "RDPI2401.DBC"} and set(man["falhas"]) == {"RDMA2402.DBC"}
    df = pd.read_parquet(tmp_path / "sih_2024.parquet")
    assert df["calor"].sum() == 2 and set(df["mun6"]) == {211130, 220040}


def _municipios_sinteticos(n=60, ncel=12):
    rng = np.random.default_rng(1)
    ufs = ["MA"] * (n // 2) + ["PI"] * (n - n // 2)
    return pd.DataFrame({
        "cod_ibge": [f"{21 if u == 'MA' else 22}{k:04d}0" for k, u in enumerate(ufs)], "nome": [f"M{k}" for k in range(n)],
        "uf": ufs, "celula": [f"c{k % ncel}" for k in range(n)], "prop60": rng.uniform(.08, .2, n),
        "prop80": rng.uniform(.01, .04, n), "pop60": rng.integers(2_000, 40_000, n), "populacao": 100_000})


def _exposicao_sintetica(dias, ncel=12, semente=2):
    """E diário com ondas de calor de 3 a 8 dias espalhadas no ano."""
    rng = np.random.default_rng(semente)
    E = rng.uniform(0.05, 0.45, (len(dias), ncel)).astype(np.float32)
    for c in range(ncel):
        for _ in range(len(dias) // 40):
            i, L = rng.integers(0, len(dias) - 10), rng.integers(3, 9)
            E[i:i + L, c] = rng.uniform(0.75, 1.0)
    return E


def _internacoes_sinteticas(m, E, dias, cels, inicio, rr_calor, semente=3):
    """Poisson com efeito multiplicativo rr_calor nos dias em alerta (definição da validação); 'todas' sem efeito."""
    rng = np.random.default_rng(semente)
    w = {"exposicao": .6 / .85, "sensibilidade": .25 / .85}
    S = B.sensibilidade(m)
    ivc = np.round(100 * (w["exposicao"] * E[:, pd.Index(cels).get_indexer(m["celula"])] + w["sensibilidade"] * S))
    k0 = dias.get_loc(pd.Timestamp(inicio))
    X = np.fmax(np.fmax(ivc[k0:], ivc[k0 - 1:-1]), ivc[k0 - 2:-2])
    d = dias[k0:]
    sazonal = (1 + 0.3 * np.sin(2 * np.pi * d.dayofyear.to_numpy() / 365) + 0.1 * (d.weekday.to_numpy() < 5))[:, None]
    base = (m["pop60"].to_numpy() / 10_000)[None, :] * sazonal
    calor = rng.poisson(base * np.where(X >= 60, rr_calor, 1.0))
    todas = rng.poisson(base * 4)
    linhas = []
    for j, cod in enumerate(m["cod_ibge"].str[:6].astype(int)):
        linhas.append(pd.DataFrame({"mun6": cod, "data": d.strftime("%Y%m%d").astype(int), "calor": calor[:, j],
                                    "circ": 0, "resp": 0, "todas": todas[:, j] + calor[:, j]}))
    return pd.concat(linhas, ignore_index=True), X


def test_analise_recupera_o_efeito(tmp_path):
    P = B.Pastas(tmp_path / "d", tmp_path / "s")
    m = _municipios_sinteticos()
    cels = [f"c{k}" for k in range(12)]
    dias = pd.date_range("2023-12-01", "2025-12-31")
    E = _exposicao_sintetica(dias)
    sih, X = _internacoes_sinteticas(m, E, dias, cels, date(2024, 1, 1), rr_calor=1.4)
    assert 0.03 < (X >= 60).mean() < 0.4                                # há dias em alerta e sem alerta
    res, series = V.analisar(E, dias, cels, m, P, sih, {"arquivos_lidos": 1}, date(2024, 1, 1), date(2025, 12, 31),
                             n_boot=150, log=lambda *a: None)
    br = res["areas"]["BR"]["grupos"]
    a = br["calor"]["alerta"]
    assert a["lo"] < 1.4 < a["hi"] and abs(a["rr"] - 1.4) < 0.08
    # internações a mais: N nos dias de alerta x (1 - 1/RR), com o mesmo intervalo da razão
    assert a["excesso_lo"] < a["excesso"] < a["excesso_hi"]
    assert a["excesso"] == pytest.approx(a["internacoes_em_alerta"] * (1 - 1 / a["rr"]), rel=0.003)   # rr arredondado
    # 'todas' inclui o efeito de 'calor', diluído; um grupo sem efeito fica perto de 1
    nulo = res["areas"]["BR"]["grupos"]["circ"]["alerta"]
    assert nulo["rr"] is None                                           # sem internações: não estima
    assert set(res["areas"]) == {"BR", "MA", "PI"} and set(res["regioes"]) == {"Nordeste"}
    f = {x["faixa"]: x for x in br["calor"]["faixas"]}
    assert f["BAIXA"]["rr"] == 1.0 and f["ALTA"]["rr"] > 1.2
    assert sum(x["dias_pct"] for x in br["calor"]["faixas"]) == pytest.approx(100, abs=0.1)
    lims = {x["k"]: x for x in br["calor"]["limiares"]}
    assert lims[40]["dias_pct"] > lims[60]["dias_pct"] > lims[80]["dias_pct"]
    assert len(series["BR"]["calor"]) == 731 and max(series["BR"]["alerta_pop"]) <= 100


def test_analise_sem_efeito(tmp_path):
    P = B.Pastas(tmp_path / "d", tmp_path / "s")
    m = _municipios_sinteticos()
    cels = [f"c{k}" for k in range(12)]
    dias = pd.date_range("2023-12-01", "2025-12-31")
    E = _exposicao_sintetica(dias, semente=5)
    sih, _ = _internacoes_sinteticas(m, E, dias, cels, date(2024, 1, 1), rr_calor=1.0, semente=8)
    res, _ = V.analisar(E, dias, cels, m, P, sih, {}, date(2024, 1, 1), date(2025, 12, 31), n_boot=150, log=lambda *a: None)
    a = res["areas"]["BR"]["grupos"]["calor"]["alerta"]
    # sem efeito simulado: estimativa perto de 1 (em 20 simulações, média 0,998 e cobertura de 100% do IC)
    assert abs(a["rr"] - 1) < 0.04 and a["lo"] < 1.0 < a["hi"]


@pytest.fixture
def operacao(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "ANOS_CLIMATOLOGIA", [2022, 2023, 2024, 2025])   # 4 anos: EHF85 estimável na maioria das células
    base, site = tmp_path / "data", tmp_path / "site"
    B.executar(ClienteSimuladoBrasil(date(2026, 10, 12)), date(2026, 10, 12), "simulacao", base=base, site=site,
               pausa=0, verbose=False)
    return B.Pastas(base, site)


def test_exposicao_igual_a_operacao_e_exportacao(operacao, tmp_path):
    P = operacao
    m = pd.read_csv(P.ref / "municipios_br.csv", dtype={"cod_ibge": str, "celula": str})
    cel = pd.read_csv(P.ref / "celulas.csv", dtype={"celula": str})
    cli = ClienteSimuladoBrasil(date(2026, 10, 12))
    cache = tmp_path / "cache" / "exp.npz"
    datas, cels, E = V.exposicao_historica(cli, P, cel, cache=cache, anos=[2025, 2026], log=lambda *a: None)
    # o IVC recalculado é o mesmo do painel diário nos dias observados pela CPC
    w, _ = B.pesos_ivc(m, P)
    S = B.sensibilidade(m)
    k = datas.get_loc(pd.Timestamp("2026-03-01"))
    ivc = np.round(100 * (w["exposicao"] * E[k, pd.Index(cels).get_indexer(m["celula"])].astype(float) + w["sensibilidade"] * S))
    painel = np.array(json.loads((P.site / "dia" / "2026-03-01.json").read_text(encoding="utf-8"))["ivc"], dtype=float)
    assert np.isfinite(painel).sum() > 40 and (np.isfinite(ivc) == np.isfinite(painel)).all()
    ok = np.isfinite(painel)
    assert np.abs(ivc[ok] - painel[ok]).max() <= 1                      # temperaturas gravadas com 0,1 °C no painel
    assert (ivc[ok] == painel[ok]).mean() > 0.9
    # segunda chamada usa o cache sem baixar nada
    class SemRede:
        def __getattr__(self, n):
            raise AssertionError(n)
    d2, _, E2 = V.exposicao_historica(SemRede(), P, cel, cache=cache, anos=[2025, 2026], log=lambda *a: None)
    assert len(d2) == len(datas) and np.allclose(E2, E, equal_nan=True, atol=1e-3)
    # análise com internações sintéticas e exportação para o painel
    sih, _ = _internacoes_sinteticas(m, E.astype(np.float32), datas, cels, date(2025, 2, 1), rr_calor=1.3)
    res, series = V.analisar(E.astype(np.float32), datas, cels, m, P, sih, {}, date(2025, 2, 1), date(2025, 12, 31),
                             n_boot=50, log=lambda *a: None)
    V.gravar(res, series, P)
    B.executar(SemRede(), date(2026, 10, 12), "simulacao", base=P.ref.parent, site=P.site, pausa=0, verbose=False,
               so_painel=True)
    r = json.loads((P.site / "validacao" / "resultados.json").read_text(encoding="utf-8"))
    assert r["periodo"] == ["2025-02-01", "2025-12-31"] and "BR" in r["areas"]
    assert (P.site / "validacao" / "serie" / "MA.json").exists()


def test_bootstrap_em_area_pequena(tmp_path):
    """Com poucos municípios (como o DF, com um só), o intervalo vem de município-ano e não colapsa."""
    P = B.Pastas(tmp_path / "d", tmp_path / "s")
    m = _municipios_sinteticos(n=4, ncel=2)
    cels = ["c0", "c1"]
    dias = pd.date_range("2021-12-01", "2025-12-31")
    E = _exposicao_sintetica(dias, ncel=2, semente=11)
    sih, _ = _internacoes_sinteticas(m, E, dias, cels, date(2022, 1, 1), rr_calor=1.3, semente=12)
    res, _ = V.analisar(E, dias, cels, m, P, sih, {}, date(2022, 1, 1), date(2025, 12, 31), n_boot=200, log=lambda *a: None)
    A = res["areas"]["BR"]
    a = A["grupos"]["calor"]["alerta"]
    assert A["bootstrap"] == "município-ano" and a["lo"] < a["rr"] < a["hi"] and a["hi"] - a["lo"] > 0.02
