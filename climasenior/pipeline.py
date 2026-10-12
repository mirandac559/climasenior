# -*- coding: utf-8 -*-
"""Orquestra a esteira completa: ingestão -> atributos -> treino -> IVC -> backtesting."""
from __future__ import annotations
import json
from .config import DIR_MODELOS
from . import ingestao, atributos
from .modelos import ClimaSeniorModelos, divisao_temporal
from .backtesting import backtesting, curva_limiares, monitorar_drift


def executar(modo: str = "demo", versao: str = "v1", verbose: bool = True) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    log(f"[1/5] Ingestão (modo={modo})")
    base = ingestao.carregar(modo)
    log(f"      {len(base):,} registros | {base['cod_ibge'].nunique()} municípios | "
        f"{base['data'].min():%Y-%m-%d} a {base['data'].max():%Y-%m-%d}")

    log("[2/5] Engenharia de atributos")
    feat = atributos.construir(base)

    log("[3/5] Treino com divisão temporal")
    m = ClimaSeniorModelos().treinar(feat)
    log(f"      LSTM disponível: {m.metricas['lstm_disponivel']} | "
        f"F1 macro (teste 2025): {m.metricas['teste_2025']['risco_f1_macro']}")

    log("[4/5] Cálculo do IVC")
    ivc = m.calcular_ivc(feat)

    log("[5/5] Backtesting e monitoramento de deriva (Fase 3)")
    tr, _, te = divisao_temporal(feat)
    ivc_te = ivc[ivc["data"] >= te["data"].min()]
    bt = backtesting(ivc_te, limiar_acao=60.0)
    curva = curva_limiares(ivc_te)
    drift = monitorar_drift(tr, te)

    m.salvar(versao)
    ivc.to_parquet(DIR_MODELOS / f"ivc_{versao}.parquet", index=False)
    resumo = {"modo": modo, "versao": versao, "metricas": m.metricas,
              "backtesting_2025": {k: v for k, v in bt.items() if k != "episodios"},
              "curva_limiares": curva.to_dict(orient="records"), "drift": drift,
              "_aviso": ("Modo DEMO: dados sintéticos; valores não constituem resultados "
                         "científicos." if modo == "demo" else "Modo REAL")}
    with open(DIR_MODELOS / f"resumo_{versao}.json", "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2, default=str)
    log(f"      episódios detectados: {bt['episodios_detectados']}/{bt['n_episodios']} | "
        f"antecedência média: {bt['antecedencia_media_dias']} d | retreinar: {drift['retreinar']}")
    return resumo


if __name__ == "__main__":
    import sys
    executar(modo=sys.argv[1] if len(sys.argv) > 1 else "demo")
