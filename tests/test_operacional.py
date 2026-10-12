# -*- coding: utf-8 -*-
"""Testes da operação em tempo real (v0.4). Não usam rede."""
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from climasenior import ehf as EHF                      # noqa: E402
from climasenior import fontes as F                     # noqa: E402
from climasenior import operacional as OP               # noqa: E402
from climasenior.simulacao import ClienteSimulado       # noqa: E402


# --------------------------------------------------------------------- EHF
def test_ehf_calculo_manual():
    # 30 dias a 27 °C, depois 3 dias a 30 °C; P95 = 28 °C
    t = pd.Series([27.0] * 30 + [30.0] * 3 + [27.0] * 2,
                  index=pd.date_range("2026-01-01", periods=35))
    e = EHF.calcular(t, t95=28.0, ehf85=1.5)
    dia = pd.Timestamp("2026-01-31")
    assert e.loc[dia, "t3"] == pytest.approx(30.0)
    assert e.loc[dia, "ehi_sig"] == pytest.approx(2.0)          # 30 - 28
    assert e.loc[dia, "ehi_accl"] == pytest.approx(3.0)         # 30 - 27
    assert e.loc[dia, "ehf"] == pytest.approx(6.0)              # 2 x max(1, 3)
    assert e.loc[dia, "severidade"] == pytest.approx(4.0)       # 6 / 1,5
    assert EHF.classe(4.0) == "extrema" and EHF.classe(0.5) == "baixa intensidade"
    assert np.isnan(e["ehf"].iloc[-1])                          # sem T(i+1), T(i+2)


def test_ehf_sem_calor_e_negativo():
    t = pd.Series([26.0] * 40, index=pd.date_range("2026-01-01", periods=40))
    e = EHF.calcular(t, t95=28.0, ehf85=1.0)
    assert (e["ehf"].dropna() < 0).all()
    assert (e["severidade"].dropna() == 0).all()


# --------------------------------------------------------------------- fontes
def test_open_meteo_uma_e_varias_localidades():
    cli = ClienteSimulado(date(2026, 10, 12))
    locs = [{"cod_ibge": "1", "lat": -2.53, "lon": -44.3}, {"cod_ibge": "2", "lat": -2.9, "lon": -44.2}]
    df = F.baixar_reanalise(cli, locs, "2026-01-01", "2026-01-10", "America/Fortaleza")
    assert set(df["chave"]) == {"1", "2"} and len(df) == 20
    um = F.baixar_reanalise(cli, locs[:1], "2026-01-01", "2026-01-10", "America/Fortaleza")
    assert len(um) == 10 and {"tmax", "tmin", "tapmax"} <= set(um.columns)


def test_open_meteo_erro_explicito():
    class Ruim:
        def get_json(self, url, params=None):
            return {"error": True, "reason": "Parameter 'daily' invalid"}
    with pytest.raises(F.ErroFonte, match="invalid"):
        F.baixar_previsao(Ruim(), [{"cod_ibge": "1", "lat": 0, "lon": 0}], 31, 16, "UTC")


def test_ibge_censo_soma_grupos_e_ignora_idades_simples():
    cli = ClienteSimulado(date(2026, 10, 12))
    df = F.populacao_por_idade(cli, ["9900001", "9900002"])
    assert len(df) == 2
    assert df["prop60"].between(0.05, 0.25).all()
    assert (df["pop80"] < df["pop60"]).all()


def test_ibge_censo_usa_categoria_agregada_quando_existe():
    resp = [{"id": "93", "resultados": [
        {"classificacoes": [{"id": "287", "categoria": {"1": "Total"}}],
         "series": [{"localidade": {"id": "1"}, "serie": {"2022": "1000"}}]},
        {"classificacoes": [{"id": "287", "categoria": {"2": "60 anos ou mais"}}],
         "series": [{"localidade": {"id": "1"}, "serie": {"2022": "150"}}]},
        {"classificacoes": [{"id": "287", "categoria": {"3": "80 anos ou mais"}}],
         "series": [{"localidade": {"id": "1"}, "serie": {"2022": "20"}}]},
        {"classificacoes": [{"id": "2", "categoria": {"9": "Homens"}}, {"id": "287", "categoria": {"2": "60 anos ou mais"}}],
         "series": [{"localidade": {"id": "1"}, "serie": {"2022": "70"}}]},
    ]}]

    class C:
        def get_json(self, url, params=None):
            return resp
    df = F.populacao_por_idade(C(), ["1"])
    assert df.iloc[0]["prop60"] == pytest.approx(0.15) and df.iloc[0]["prop80"] == pytest.approx(0.02)


def test_ibge_codigos_por_nome_sem_acento():
    class C:
        def get_json(self, url, params=None):
            return [{"id": 1, "nome": "São Luís"}, {"id": 2, "nome": "Paço do Lumiar"}]
    assert F.resolver_codigos(C(), ["Sao Luis", "PAÇO DO LUMIAR"]) == {"Sao Luis": "1", "PAÇO DO LUMIAR": "2"}
    with pytest.raises(F.ErroFonte):
        F.resolver_codigos(C(), ["Inexistente"])


# --------------------------------------------------------------------- série
def _linhas(datas, fonte, tmax):
    return pd.DataFrame({"data": pd.to_datetime(datas), "cod_ibge": "1", "tmax": tmax,
                         "tmin": tmax - 7, "tapmax": tmax + 3, "fonte": fonte})


def test_mesclar_era5_prevalece_e_previsao_e_substituida():
    atual = pd.concat([_linhas(["2026-10-01", "2026-10-02"], "era5", 30.0),
                       _linhas(["2026-10-03", "2026-10-04"], "previsao", 31.0)])
    novo = pd.concat([_linhas(["2026-10-02", "2026-10-03"], "modelo", 35.0),   # 02 é ERA5: não muda
                      _linhas(["2026-10-04"], "era5", 32.0),                    # chega o ERA5 de 04
                      _linhas(["2026-10-05"], "previsao", 33.0)])
    m = OP.mesclar(atual, novo).set_index("data")
    assert m.loc["2026-10-02", "tmax"] == 30.0 and m.loc["2026-10-02", "fonte"] == "era5"
    assert m.loc["2026-10-03", "tmax"] == 35.0 and m.loc["2026-10-03", "fonte"] == "modelo"
    assert m.loc["2026-10-04", "fonte"] == "era5" and m.loc["2026-10-05", "fonte"] == "previsao"
    assert not m.index.duplicated().any()


# --------------------------------------------------------------------- ponta a ponta
@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(OP.C, "DIR_REF", tmp_path / "data/ref")
    monkeypatch.setattr(OP.C, "DIR_SERIE", tmp_path / "data/serie")
    monkeypatch.setattr(OP.C, "DIR_SITE_DADOS", tmp_path / "site/data")
    return tmp_path


def test_operacao_completa_e_virada_de_ano(pasta):
    r1 = OP.executar(ClienteSimulado(date(2026, 10, 12)), hoje=date(2026, 10, 12), modo="simulacao",
                     verbose=False, pausa=0)
    assert r1["anos"] == [2026]
    atual = json.loads((pasta / "site/data/atual.json").read_text(encoding="utf-8"))
    assert len(atual["municipios"]) == 13
    assert all(m["nome"].startswith("Município fictício") for m in atual["municipios"])
    serie = json.loads((pasta / "site/data/serie_2026.json").read_text(encoding="utf-8"))
    s = next(iter(serie["municipios"].values()))
    assert s["d"][0] == "2026-01-01"                       # começa em 2026 (aquecimento fica fora)
    ivc = [v for v in s["ivc"] if v is not None]
    assert min(ivc) >= 0 and max(ivc) <= 100
    assert s["ivc"][-1] is None and s["ivc"][-2] is None    # últimos 2 dias sem janela de 3 dias
    assert set(s["fonte"]) == {"e", "m", "p"}

    # 85 dias sem rodar, atravessando a virada do ano
    r2 = OP.executar(ClienteSimulado(date(2027, 1, 5)), hoje=date(2027, 1, 5), modo="simulacao",
                     verbose=False, pausa=0)
    assert r2["anos"] == [2026, 2027]
    todas = pd.concat([pd.read_csv(f, dtype={"cod_ibge": str}) for f in (pasta / "data/serie").glob("*.csv")])
    assert not todas.duplicated(["data", "cod_ibge"]).any()
    um = pd.to_datetime(todas[todas["cod_ibge"] == todas["cod_ibge"].iloc[0]]["data"]).sort_values()
    assert (um.diff().dt.days.dropna() == 1).all()           # sem lacunas
    meta = json.loads((pasta / "site/data/meta.json").read_text(encoding="utf-8"))
    assert meta["modo"] == "simulacao" and meta["anos"] == [2026, 2027]
    assert meta["capacidade_disponivel"] is False


def test_capacidade_entra_no_indice(pasta):
    OP.executar(ClienteSimulado(date(2026, 10, 12)), hoje=date(2026, 10, 12), modo="simulacao",
                verbose=False, pausa=0)
    muns = json.loads((pasta / "data/ref/municipios.json").read_text(encoding="utf-8"))
    linhas = ["cod_ibge;estab_atencao_basica"] + [f"{m['cod_ibge']};{5 + i}" for i, m in enumerate(muns)]
    (pasta / "data/ref/capacidade.csv").write_text("\n".join(linhas), encoding="utf-8")
    OP.executar(ClienteSimulado(date(2026, 10, 13)), hoje=date(2026, 10, 13), modo="simulacao",
                verbose=False, pausa=0)
    meta = json.loads((pasta / "site/data/meta.json").read_text(encoding="utf-8"))
    assert meta["capacidade_disponivel"] is True and meta["pesos"]["capacidade"] == pytest.approx(0.15)


def test_open_meteo_chave_com_sufixo_do_modelo():
    class C:
        def get_json(self, url, params=None):
            assert params.get("models") == "era5"
            return {"daily": {"time": ["2026-01-01"], "temperature_2m_max_era5": [31.0],
                              "temperature_2m_min_era5": [24.0], "apparent_temperature_max_era5": [35.0]}}
    df = F.baixar_reanalise(C(), [{"cod_ibge": "1", "lat": 0, "lon": 0}], "2026-01-01", "2026-01-01", "UTC")
    assert df.loc[0, "tmax"] == 31.0 and df.loc[0, "tmin"] == 24.0
