# -*- coding: utf-8 -*-
"""
Fator de Excesso de Calor (EHF — Excess Heat Factor).

Nairn, J. R.; Fawcett, R. J. B. The Excess Heat Factor: a metric for heatwave
intensity and its use in classifying heatwave severity. International Journal
of Environmental Research and Public Health, v. 12, n. 1, p. 227-253, 2015.

Para cada dia i, com T a temperatura média diária:
    T3(i)     = média de T(i), T(i+1), T(i+2)             (janela de 3 dias à frente)
    EHIsig(i) = T3(i) - T95                               (excesso sobre o percentil 95 local)
    EHIaccl(i)= T3(i) - média de T(i-30) ... T(i-1)       (aclimatação aos últimos 30 dias)
    EHF(i)    = EHIsig(i) * max(1, EHIaccl(i))            (°C²)
    severidade= EHF / EHF85, com EHF85 o percentil 85 dos EHF positivos no período de referência

Classes: EHF <= 0 sem onda de calor; 0 < sev < 1 baixa intensidade; 1 <= sev < 3 severa; sev >= 3 extrema.

A métrica incorpora as duas coisas que o projeto identificou como mais
informativas: a persistência (média de três dias) e o desvio em relação ao
que a população vinha experimentando (aclimatação). Aqui T = (Tmáx + Tmín)/2,
calculada da mesma forma na referência e na operação.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def temperatura_media(df: pd.DataFrame) -> pd.Series:
    return (df["tmax"] + df["tmin"]) / 2.0


def calcular(t: pd.Series, t95: float, ehf85: float | None = None) -> pd.DataFrame:
    """t: série diária contínua (índice de datas, sem lacunas) de temperatura média."""
    t = t.astype(float)
    t3 = (t + t.shift(-1) + t.shift(-2)) / 3.0
    t30 = t.shift(1).rolling(30, min_periods=30).mean()
    sig = t3 - t95
    accl = t3 - t30
    ehf = sig * np.maximum(1.0, accl)
    out = pd.DataFrame({"t3": t3, "ehi_sig": sig, "ehi_accl": accl, "ehf": ehf}, index=t.index)
    if ehf85:
        out["severidade"] = np.where(out["ehf"] > 0, out["ehf"] / ehf85, 0.0)
        out.loc[out["ehf"].isna(), "severidade"] = np.nan
    return out


def climatologia(t: pd.Series) -> dict:
    """Percentis de referência e EHF85 a partir de uma série longa (CPC, 2014-2025)."""
    t = t.astype(float).dropna()
    p50, p90, p95 = (float(np.percentile(t, q)) for q in (50, 90, 95))
    e = calcular(t, p95)["ehf"]
    pos = e[e > 0].dropna()
    if len(pos) < 20:
        raise ValueError("Poucos dias com EHF positivo na referência para estimar o EHF85")
    return {"p50": round(p50, 3), "p90": round(p90, 3), "p95": round(p95, 3),
            "ehf85": round(float(np.percentile(pos, 85)), 4), "n_dias": int(len(t)),
            "n_ehf_positivo": int(len(pos))}
