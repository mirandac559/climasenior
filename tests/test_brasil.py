# -*- coding: utf-8 -*-
"""Testes da operação nacional (sem rede; CPC, IBGE e Open-Meteo simulados)."""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from climasenior import brasil as B                          # noqa: E402
from climasenior.simulacao_br import ClienteSimuladoBrasil   # noqa: E402


@pytest.fixture
def pastas(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "ANOS_CLIMATOLOGIA", [2024, 2025])     # climatologia curta: teste rápido
    return tmp_path / "data", tmp_path / "site"


def _rodar(pastas, hoje, **kw):
    base, site = pastas
    return B.executar(ClienteSimuladoBrasil(hoje), hoje, "simulacao", base=base, site=site, pausa=0,
                      verbose=False, **kw)


def test_ponta_a_ponta(pastas):
    r = _rodar(pastas, date(2026, 10, 12))
    base, site = pastas
    meta = json.loads((site / "meta.json").read_text(encoding="utf-8"))
    assert meta["ultimo_dia_cpc"] == "2026-09-04"
    assert meta["pendencias"] == {"celula_dias_faltando": 0, "celulas_sem_vies": 0}
    assert 0.3 < meta["vies_modelo"]["tmax_mediana"] < 0.8          # o modelo simulado é 0,5 °C mais quente
    assert meta["dias"][0][0] == "2026-01-01" and meta["dias"][-1][0] == "2026-10-16"
    assert {f for _, f in meta["dias"]} == {"o", "m", "p"}
    mu = json.loads((site / "municipios.json").read_text(encoding="utf-8"))
    assert len(mu["cod"]) == 71 and min(mu["cel"]) >= 0              # inclui o município geocodificado
    assert all(n.startswith("Município fictício") for n in mu["nome"])
    assert len(mu["regioes"]["RM Grande São Luís (piloto)"]) == 13
    d = json.loads((site / "dia" / "2026-10-12.json").read_text(encoding="utf-8"))
    assert len(d["ivc"]) == 71 and all(0 <= v <= 100 for v in d["ivc"] if v is not None)
    assert len(d["tmax"]) == len(mu["celulas"])
    for uf in ("MA", "PI", "CE", "RN"):
        assert (site / "serie" / "2026" / f"{uf}.json").exists()
    uso = json.loads((base / "ref" / "uso_api.json").read_text(encoding="utf-8"))
    assert uso["chamadas"] > 0 and r["pendentes"] == 0


def test_orcamento_curto_completa_depois(pastas):
    r1 = _rodar(pastas, date(2026, 10, 12), orcamento=80)
    assert r1["pendentes"] > 0 or r1["sem_vies"] > 0
    r2 = _rodar(pastas, date(2026, 10, 12), complemento=True, orcamento=4000)
    assert r2["pendentes"] == 0 and r2["sem_vies"] == 0
    r3 = _rodar(pastas, date(2026, 10, 12), complemento=True)
    assert r3["alterou"] is False                                    # nada mais a fazer


def test_virada_de_ano_e_cpc_nova(pastas):
    _rodar(pastas, date(2026, 10, 12))
    r = _rodar(pastas, date(2027, 1, 5))
    base, site = pastas
    meta = json.loads((site / "meta.json").read_text(encoding="utf-8"))
    assert meta["ultimo_dia_cpc"] == "2027-01-03"
    assert (site / "serie" / "2027").exists() and (site / "dia" / "2027-01-05.json").exists()
    assert r["pendentes"] == 0
    dias = sorted(p.stem for p in (base / "clima" / "2026").glob("*.csv"))
    assert dias[0] == "2026-01-01" and dias[-1] == "2026-12-31" and len(dias) == 365


def test_cpc_prevalece_sobre_modelo(tmp_path):
    P = B.Pastas(tmp_path / "d", tmp_path / "s")
    t = pd.Timestamp("2026-03-01")
    B.gravar_dias(P, pd.DataFrame({"data": [t], "celula": ["a"], "tmax": [30.0], "tmin": [22.0], "tapmax": [None], "fonte": ["cpc"]}))
    B.gravar_dias(P, pd.DataFrame({"data": [t, t], "celula": ["a", "b"], "tmax": [33.0, 31.0], "tmin": [23.0, 21.0],
                                   "tapmax": [36.0, 35.0], "fonte": ["modelo", "modelo"]}))
    d = pd.read_csv(tmp_path / "d" / "clima" / "2026" / "2026-03-01.csv").set_index("celula")
    assert d.loc["a", "fonte"] == "cpc" and d.loc["a", "tmax"] == 30.0 and d.loc["b", "fonte"] == "modelo"


def test_painel_usa_campos_exportados():
    html = (Path(__file__).resolve().parent.parent / "site/index.html").read_text(encoding="utf-8")
    for campo in ("meta.json", "municipios.json", "ufs.json", "dia/${d}.json", "serie/${chave}.json",
                  "ultimo_dia_cpc", "n_celulas", "vies_modelo", "pendencias", "regioes", "celulas"):
        assert campo in html, campo


def test_vies_atualiza_com_a_janela_recente(tmp_path):
    P = B.Pastas(tmp_path / "d", tmp_path / "s")
    dias = pd.date_range("2026-10-05", periods=5)
    obs = pd.DataFrame({"data": dias, "celula": "a", "tmax": 30.0, "tmin": 22.0, "tapmax": None, "fonte": "cpc"})
    B.gravar_dias(P, obs)
    pd.DataFrame({"celula": ["a"], "vies_tmax": [1.0], "vies_tmin": [0.0], "n_dias": [7]}).to_csv(P.ref / "vies.csv", index=False)
    mod = obs.assign(tmax=32.0, tmin=21.0, fonte="modelo")
    B.atualizar_vies(P, mod)
    v = pd.read_csv(P.ref / "vies.csv").set_index("celula")
    assert v.loc["a", "vies_tmax"] == pytest.approx(0.7 * 1.0 + 0.3 * 2.0)
    assert v.loc["a", "vies_tmin"] == pytest.approx(0.3 * -1.0) and v.loc["a", "n_dias"] == 12
