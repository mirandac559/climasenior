# -*- coding: utf-8 -*-
"""Modelo de demanda: divisão temporal, ganho da informação de calor, gravação e previsão operacional."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from climasenior import brasil as B        # noqa: E402
from climasenior import demanda as D       # noqa: E402
from climasenior import validacao as V     # noqa: E402
from test_validacao import _exposicao_sintetica, _internacoes_sinteticas, _municipios_sinteticos   # noqa: E402


def test_modelo_de_demanda(tmp_path):
    P = B.Pastas(tmp_path / "d", tmp_path / "s")
    m = _municipios_sinteticos(n=40, ncel=8)
    cels = [f"c{k}" for k in range(8)]
    datas = pd.date_range("2013-12-01", "2025-12-31")
    E = _exposicao_sintetica(datas, ncel=8, semente=21)
    sih, _ = _internacoes_sinteticas(m, E, datas, cels, date(2014, 1, 1), rr_calor=1.6, semente=22)
    M = V.matrizes(E, datas, cels, m, P, sih, date(2014, 1, 1), date(2025, 12, 31), log=lambda *a: None)
    mods, meta, extra = D.treinar(M, log=lambda *a: None, fracao=0.5)
    g = meta["grupos"]["calor"]
    assert meta["periodos"]["treino"][1] == "2022-12-31" and meta["periodos"]["teste"] == ["2025-01-01", "2025-12-31"]
    # com a informação de calor o modelo explica mais e acerta melhor os dias de alerta
    assert g["com_clima"]["teste"]["d2"] > g["sem_clima"]["teste"]["d2"]
    assert abs(g["com_clima"]["teste"]["alerta_razao"] - 1) < abs(g["sem_clima"]["teste"]["alerta_razao"] - 1)
    assert 0.9 < g["com_clima"]["teste"]["razao_total"] < 1.1
    assert len(g["com_clima"]["teste"]["calibracao"]) == 10
    assert set(extra["series"]) >= {"BR", "MA", "PI"} and len(extra["series"]["BR"]["prev_calor"]) == 1096
    br = np.array(extra["series"]["BR"]["prev_todas"])
    assert (br[:731] > 0).all() and (br[731:] > 0).all()                      # validação e teste, sem dias zerados
    uf = np.array(extra["series"]["MA"]["prev_todas"]) + np.array(extra["series"]["PI"]["prev_todas"])
    assert np.allclose(uf, br, rtol=1e-3)                                     # Brasil = soma das UFs
    assert 0.8 < g["com_clima"]["fator_calibracao"] < 1.25
    # gravar, carregar e prever como na operação diária
    D.gravar(mods, meta, extra, pasta_modelos=tmp_path / "modelos", pasta_ref=P.ref)
    mods2, meta2 = D.carregar(tmp_path / "modelos")
    base = pd.read_csv(P.ref / "demanda_base.csv", dtype={"cod_ibge": str})
    k = M["dias_todos"].get_loc(pd.Timestamp("2025-06-01"))
    dias = M["dias_todos"][k:k + 10]
    prev = D.prever(mods2, base, m, dias, M["Em"], M["ivc"], M["S"], M["C"], k)
    assert prev["calor"].shape == (10, 40) and (prev["calor"] > 0).all() and (prev["todas"] > prev["calor"]).mean() > 0.9


def test_previsao_no_painel(tmp_path, monkeypatch):
    """Com modelo treinado, o painel diário traz as internações previstas de cada município."""
    import json
    from climasenior.simulacao_br import ClienteSimuladoBrasil
    P0 = B.Pastas(tmp_path / "t", tmp_path / "ts")
    m0 = _municipios_sinteticos(n=30, ncel=6)
    cels = [f"c{k}" for k in range(6)]
    datas = pd.date_range("2013-12-01", "2025-12-31")
    E = _exposicao_sintetica(datas, ncel=6, semente=31)
    sih, _ = _internacoes_sinteticas(m0, E, datas, cels, date(2014, 1, 1), rr_calor=1.4, semente=32)
    M = V.matrizes(E, datas, cels, m0, P0, sih, date(2014, 1, 1), date(2025, 12, 31), log=lambda *a: None)
    mods, meta, extra = D.treinar(M, log=lambda *a: None, fracao=0.5)
    monkeypatch.setattr(D, "DIR_MODELOS", tmp_path / "modelos")
    monkeypatch.setattr(B, "ANOS_CLIMATOLOGIA", [2022, 2023, 2024, 2025])
    base, site = tmp_path / "data", tmp_path / "site"
    P = B.Pastas(base, site)
    cli = ClienteSimuladoBrasil(date(2026, 10, 12))
    B.executar(cli, date(2026, 10, 12), "simulacao", base=base, site=site, pausa=0, verbose=False)   # sem modelo
    assert "dem" not in json.loads((site / "dia" / "2026-10-12.json").read_text(encoding="utf-8"))
    mu = pd.read_csv(P.ref / "municipios_br.csv", dtype={"cod_ibge": str})
    extra["base"] = pd.DataFrame({"cod_ibge": mu["cod_ibge"], "base_todas": 2.0, "base_calor": 0.2})
    D.gravar(mods, meta, extra, pasta_ref=P.ref)
    B.executar(cli, date(2026, 10, 12), "simulacao", base=base, site=site, pausa=0, verbose=False, so_painel=True)
    d = json.loads((site / "dia" / "2026-10-12.json").read_text(encoding="utf-8"))
    assert len(d["dem"]) == len(mu) and all(v is None or v >= 0 for v in d["dem"])
    assert sum(v for v in d["dem"] if v) > sum(v for v in d["demc"] if v) > 0
    meta_site = json.loads((site / "meta.json").read_text(encoding="utf-8"))
    assert meta_site["demanda"]["periodos"]["teste"] == ["2025-01-01", "2025-12-31"]


def test_estavel_com_cidades_muito_grandes(tmp_path):
    """Uma cidade com demanda cem vezes maior que as demais não pode fazer a previsão explodir."""
    P = B.Pastas(tmp_path / "d", tmp_path / "s")
    m = _municipios_sinteticos(n=30, ncel=6)
    m.loc[0, "pop60"] = 2_000_000                                    # "São Paulo"
    cels = [f"c{k}" for k in range(6)]
    datas = pd.date_range("2013-12-01", "2025-12-31")
    E = _exposicao_sintetica(datas, ncel=6, semente=41)
    sih, _ = _internacoes_sinteticas(m, E, datas, cels, date(2014, 1, 1), rr_calor=1.3, semente=42)
    M = V.matrizes(E, datas, cels, m, P, sih, date(2014, 1, 1), date(2025, 12, 31), log=lambda *a: None)
    _, meta, _ = D.treinar(M, log=lambda *a: None, fracao=0.5)
    for g in ("todas", "calor"):
        t = meta["grupos"][g]["com_clima"]["teste"]
        assert 0.9 < t["razao_total"] < 1.1 and t["d2"] > 0.3 and meta["grupos"][g]["com_clima"]["iteracoes"] > 30
