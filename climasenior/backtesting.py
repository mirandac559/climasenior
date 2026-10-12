# -*- coding: utf-8 -*-
"""
Fase 3 - Backtesting frente a eventos de calor e monitoramento de deriva (drift).

Backtesting: identifica episódios de calor no período de teste (2025) e verifica,
para cada um, se o IVC ultrapassou o limiar de ação com a antecedência prevista
(D-3) em relação ao pico de demanda observado. Reporta sensibilidade (episódios
detectados), falsos alarmes e antecedência média.

Drift: compara a distribuição dos atributos e o desempenho recente com a janela
de treino, sinalizando necessidade de retreinamento.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .config import LIMIAR_TERMICO_LOCAL, HORIZONTE_DIAS
from .atributos import ATRIBUTOS


def identificar_episodios(df: pd.DataFrame, min_dias: int = 3, limiar: float = LIMIAR_TERMICO_LOCAL):
    """Episódios de calor por município: >= min_dias consecutivos acima do limiar."""
    episodios = []
    for cod, g in df.sort_values("data").groupby("cod_ibge"):
        quente = (g["tmax"] > limiar).values
        i = 0
        while i < len(quente):
            if quente[i]:
                j = i
                while j < len(quente) and quente[j]:
                    j += 1
                if j - i >= min_dias:
                    seg = g.iloc[i:j]
                    pico = g.iloc[i:min(j + HORIZONTE_DIAS + 2, len(g))]["atend_idosos"].idxmax()
                    episodios.append(dict(cod_ibge=cod, municipio=g["municipio"].iloc[0],
                                          inicio=seg["data"].iloc[0], fim=seg["data"].iloc[-1],
                                          duracao=j - i, tmax_max=float(seg["tmax"].max()),
                                          data_pico_demanda=g.loc[pico, "data"]))
                i = j
            else:
                i += 1
    return pd.DataFrame(episodios)


def backtesting(ivc_df: pd.DataFrame, limiar_acao: float = 60.0) -> dict:
    """Avalia o IVC contra os episódios reais do período."""
    eps = identificar_episodios(ivc_df)
    if eps.empty:
        return {"n_episodios": 0, "aviso": "nenhum episódio no período"}

    detectados, antecedencias = 0, []
    for _, e in eps.iterrows():
        g = ivc_df[(ivc_df["cod_ibge"] == e["cod_ibge"])]
        janela = g[(g["data"] >= e["inicio"] - pd.Timedelta(days=HORIZONTE_DIAS)) &
                   (g["data"] <= e["data_pico_demanda"])]
        acima = janela[janela["IVC"] >= limiar_acao]
        if not acima.empty:
            detectados += 1
            antecedencias.append((e["data_pico_demanda"] - acima["data"].iloc[0]).days)

    # falsos alarmes: dias com IVC >= limiar fora de qualquer janela de episódio
    em_episodio = pd.Series(False, index=ivc_df.index)
    for _, e in eps.iterrows():
        m = ((ivc_df["cod_ibge"] == e["cod_ibge"]) &
             (ivc_df["data"] >= e["inicio"] - pd.Timedelta(days=HORIZONTE_DIAS)) &
             (ivc_df["data"] <= e["fim"] + pd.Timedelta(days=HORIZONTE_DIAS)))
        em_episodio |= m
    alarmes = (ivc_df["IVC"] >= limiar_acao)
    falsos = int((alarmes & ~em_episodio).sum())
    dias_alarme = int(alarmes.sum())

    return {
        "limiar_acao": limiar_acao,
        "n_episodios": int(len(eps)),
        "episodios_detectados": int(detectados),
        "sensibilidade_episodios": round(detectados / len(eps), 3),
        "antecedencia_media_dias": round(float(np.mean(antecedencias)), 1) if antecedencias else None,
        "dias_com_alarme": dias_alarme,
        "dias_alarme_fora_de_episodio": falsos,
        "taxa_falso_alarme": round(falsos / dias_alarme, 3) if dias_alarme else None,
        "duracao_media_episodios": round(float(eps["duracao"].mean()), 1),
        "episodios": eps.assign(inicio=eps["inicio"].dt.strftime("%Y-%m-%d"),
                                fim=eps["fim"].dt.strftime("%Y-%m-%d"),
                                data_pico_demanda=eps["data_pico_demanda"].dt.strftime("%Y-%m-%d")
                                ).to_dict(orient="records"),
    }


def curva_limiares(ivc_df: pd.DataFrame, limiares=(40, 50, 60, 70, 80)) -> pd.DataFrame:
    """Sensibilidade x falso alarme por limiar: insumo para a pactuação com gestores."""
    linhas = []
    for L in limiares:
        r = backtesting(ivc_df, limiar_acao=L)
        linhas.append(dict(limiar=L, sensibilidade=r.get("sensibilidade_episodios"),
                           taxa_falso_alarme=r.get("taxa_falso_alarme"),
                           antecedencia_media=r.get("antecedencia_media_dias"),
                           dias_com_alarme=r.get("dias_com_alarme")))
    return pd.DataFrame(linhas)


def monitorar_drift(treino: pd.DataFrame, recente: pd.DataFrame, limite_psi: float = 0.2) -> dict:
    """Population Stability Index por atributo. PSI > 0,2 sugere retreinamento."""
    def psi(a, b, bins=10):
        q = np.quantile(a, np.linspace(0, 1, bins + 1)); q[0], q[-1] = -np.inf, np.inf
        pa = np.histogram(a, q)[0] / len(a) + 1e-6
        pb = np.histogram(b, q)[0] / len(b) + 1e-6
        return float(np.sum((pb - pa) * np.log(pb / pa)))
    res = {v: round(psi(treino[v].values, recente[v].values), 3)
           for v in ATRIBUTOS if v in treino and v in recente}
    alerta = [v for v, p in res.items() if p > limite_psi]
    return {"psi": res, "variaveis_com_deriva": alerta,
            "retreinar": len(alerta) > 0, "limite_psi": limite_psi}
