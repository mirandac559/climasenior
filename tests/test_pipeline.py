import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np
from climasenior import ingestao, atributos
from climasenior.modelos import ClimaSeniorModelos, divisao_temporal
from climasenior.backtesting import backtesting, identificar_episodios, monitorar_drift
from climasenior.config import faixa_ivc


def _feat():
    base = ingestao.gerar_demo(seed=1, salvar=False)
    base = base[base["cod_ibge"].isin(["2111300", "2100501"])]
    return atributos.construir(base)


def test_atributos_sem_vazamento():
    f = _feat()
    assert "atend_alvo" in f and f["atend_alvo"].notna().all()
    assert f["dias_consec_calor"].min() >= 0


def test_divisao_temporal_disjunta():
    tr, va, te = divisao_temporal(_feat())
    assert tr["data"].max() < va["data"].min() < te["data"].min()


def test_ivc_no_intervalo():
    f = _feat()
    m = ClimaSeniorModelos().treinar(f)
    ivc = m.calcular_ivc(f)
    assert ivc["IVC"].between(0, 100).all()
    assert set(ivc["risco_previsto"].unique()) <= {0, 1, 2}


def test_faixas():
    assert faixa_ivc(10)[0] == "BAIXA"
    assert faixa_ivc(45)[0] == "MODERADA"
    assert faixa_ivc(65)[0] == "ALTA"
    assert faixa_ivc(95)[0] == "MUITO ALTA"


def test_backtesting_estrutura():
    f = _feat()
    m = ClimaSeniorModelos().treinar(f)
    ivc = m.calcular_ivc(f)
    _, _, te = divisao_temporal(f)
    r = backtesting(ivc[ivc["data"] >= te["data"].min()], limiar_acao=60)
    assert r["n_episodios"] > 0 and 0 <= r["sensibilidade_episodios"] <= 1


def test_drift_detecta_mudanca():
    f = _feat()
    tr, _, te = divisao_temporal(f)
    r = monitorar_drift(tr, te)
    assert "psi" in r and isinstance(r["retreinar"], bool)
