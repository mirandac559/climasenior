# -*- coding: utf-8 -*-
"""Engenharia de atributos: traduz o conhecimento sobre calor e saúde em variáveis."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .config import HORIZONTE_DIAS, LIMIAR_TERMICO_LOCAL

ATRIBUTOS = ["tmax", "tmin", "umid", "ind_calor", "tmax_mm7", "tmax_mm14",
             "anom_termica", "dias_consec_calor", "noites_quentes7",
             "atend_lag1", "atend_mm7", "prop_idosos", "prev_comorb", "cap_resposta"]


def indice_calor(t: np.ndarray, rh: np.ndarray) -> np.ndarray:
    """Índice de calor (Rothfusz, adaptado para °C). Integra temperatura e umidade."""
    hi = (-8.784695 + 1.61139411 * t + 2.338549 * rh - 0.14611605 * t * rh
          - 0.012308094 * t ** 2 - 0.016424828 * rh ** 2
          + 0.002211732 * t ** 2 * rh + 0.00072546 * t * rh ** 2
          - 0.000003582 * t ** 2 * rh ** 2)
    return np.where(t >= 27, hi, t)


def _por_municipio(g: pd.DataFrame) -> pd.DataFrame:
    g = g.sort_values("data").copy()
    g["ind_calor"] = indice_calor(g["tmax"].values, g["umid"].values)
    g["tmax_mm7"] = g["tmax"].rolling(7, min_periods=1).mean()
    g["tmax_mm14"] = g["tmax"].rolling(14, min_periods=1).mean()
    g["anom_termica"] = g["tmax"] - g["tmax_mm14"]          # aclimatação
    quente = (g["tmax"] > LIMIAR_TERMICO_LOCAL).astype(int)
    g["dias_consec_calor"] = quente.groupby((quente == 0).cumsum()).cumsum()
    g["noites_quentes7"] = (g["tmin"] > 25).astype(int).rolling(7, min_periods=1).sum()
    g["atend_lag1"] = g["atend_idosos"].shift(1)
    g["atend_mm7"] = g["atend_idosos"].rolling(7, min_periods=1).mean()
    g["atend_alvo"] = g["atend_idosos"].shift(-HORIZONTE_DIAS)  # alvo em D+3
    return g


def construir(df: pd.DataFrame) -> pd.DataFrame:
    partes = []
    for _, g in df.groupby("cod_ibge", sort=False):
        g = _por_municipio(g).dropna(subset=["atend_lag1", "atend_alvo"])
        # classes de risco por município: terços superiores da demanda futura
        q1, q2 = g["atend_alvo"].quantile([0.70, 0.90])
        g["risco"] = np.select([g["atend_alvo"] >= q2, g["atend_alvo"] >= q1], [2, 1], 0)
        partes.append(g)
    return pd.concat(partes, ignore_index=True)
