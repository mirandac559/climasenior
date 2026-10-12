# -*- coding: utf-8 -*-
"""
Ingestão de dados do ClimaSênior.

Dois modos:
  * REAL  - lê arquivos exportados das fontes públicas (BDMEP/INMET, TabNet/DataSUS,
            SIDRA/IBGE) colocados em data/real/. Ver docs/GUIA_IMPLEMENTACAO.md.
  * DEMO  - gera séries sintéticas com a estrutura estatística esperada, para
            verificar a esteira e alimentar o dashboard sem dados reais.
            Os números do modo DEMO NÃO são resultados científicos.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .config import (DIR_DEMO, DIR_REAL, ANO_INICIO, ANO_FIM, MUNICIPIOS_RM,
                     LIMIAR_TERMICO_LOCAL)

COLUNAS = ["data", "cod_ibge", "municipio", "tmax", "tmin", "umid", "precip",
           "atend_idosos", "prop_idosos", "prev_comorb", "cap_resposta"]


# --------------------------------------------------------------------------
# MODO REAL - conectores de arquivo
# --------------------------------------------------------------------------
def ler_bdmep(caminho) -> pd.DataFrame:
    """Lê CSV do BDMEP (INMET). Aceita o layout padrão de exportação diária."""
    df = pd.read_csv(caminho, sep=";", encoding="latin-1", skiprows=10, decimal=",")
    df.columns = [c.strip().lower() for c in df.columns]
    ren = {}
    for c in df.columns:
        if "data" in c: ren[c] = "data"
        elif "temp" in c and ("max" in c or "máx" in c): ren[c] = "tmax"
        elif "temp" in c and ("min" in c or "mín" in c): ren[c] = "tmin"
        elif "umid" in c and "med" in c: ren[c] = "umid"
        elif "precip" in c: ren[c] = "precip"
    df = df.rename(columns=ren)
    df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    return df[[c for c in ["data", "tmax", "tmin", "umid", "precip"] if c in df.columns]].dropna(subset=["data"])


def ler_tabnet(caminho, coluna_valor="atend_idosos") -> pd.DataFrame:
    """Lê CSV exportado do TabNet (DataSUS) com linhas = dia/mês, coluna = contagem."""
    df = pd.read_csv(caminho, sep=";", encoding="latin-1", skiprows=3)
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns={df.columns[0]: "data", df.columns[1]: coluna_valor})
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df[coluna_valor] = pd.to_numeric(df[coluna_valor], errors="coerce")
    return df.dropna(subset=["data"])


def ler_sidra(caminho) -> pd.DataFrame:
    """Lê CSV do SIDRA (IBGE) com cod_ibge, prop_idosos e, opcionalmente, densidade."""
    df = pd.read_csv(caminho, sep=";", encoding="utf-8")
    df.columns = [c.strip().lower() for c in df.columns]
    df["cod_ibge"] = df["cod_ibge"].astype(str)
    return df


def carregar_real() -> pd.DataFrame:
    """Integra os arquivos de data/real/ em uma base diária unificada."""
    clima = ler_bdmep(DIR_REAL / "bdmep_sao_luis.csv")
    saude = ler_tabnet(DIR_REAL / "tabnet_atend_idosos.csv")
    demo = ler_sidra(DIR_REAL / "sidra_rm_sao_luis.csv")
    base = clima.merge(saude, on="data", how="inner")
    base["cod_ibge"] = "2111300"
    base = base.merge(demo, on="cod_ibge", how="left")
    base["municipio"] = base["cod_ibge"].map(lambda c: MUNICIPIOS_RM.get(c, {}).get("nome", c))
    return base


# --------------------------------------------------------------------------
# MODO DEMO - gerador sintético
# --------------------------------------------------------------------------
def gerar_demo(seed: int = 42, salvar: bool = True) -> pd.DataFrame:
    """Gera base sintética diária para os 13 municípios da RM de São Luís."""
    rng = np.random.default_rng(seed)
    datas = pd.date_range(f"{ANO_INICIO}-01-01", f"{ANO_FIM}-12-31", freq="D")
    n = len(datas)
    doy = datas.dayofyear.values
    tendencia = np.linspace(0, 1.2, n)
    sazonal = 2.5 * np.sin(2 * np.pi * (doy - 300) / 365.25)
    base_tmax = 31.5 + sazonal + tendencia + rng.normal(0, 1.4, n)
    # ondas de calor regionais compartilhadas
    for _ in range(90):
        i = rng.integers(0, n - 10); d = rng.integers(3, 9)
        base_tmax[i:i + d] += rng.uniform(2, 5)

    frames = []
    for cod, info in MUNICIPIOS_RM.items():
        tmax = base_tmax + rng.normal(0, 0.5, n) + (0.8 if info["cap_resposta"] > 0.6 else 0.0)  # ilha de calor urbana
        tmin = tmax - rng.uniform(6, 9, n)
        umid = np.clip(82 - 1.8 * (tmax - 31.5) + rng.normal(0, 5, n), 40, 100)
        precip = np.where(rng.random(n) < 0.35, rng.exponential(8, n), 0.0)
        excesso = np.maximum(0, tmax - LIMIAR_TERMICO_LOCAL)
        escala = 1000 * info["prop_idosos"]              # demanda proporcional à população idosa
        lam = escala * (0.14 + 0.032 * excesso + 0.016 * excesso ** 1.5
                        + 0.02 * (umid > 85) * excesso) * (1.3 - 0.5 * info["cap_resposta"])
        atend = rng.poisson(np.maximum(lam, 0.5))
        frames.append(pd.DataFrame({
            "data": datas, "cod_ibge": cod, "municipio": info["nome"],
            "tmax": tmax.round(1), "tmin": tmin.round(1), "umid": umid.round(1),
            "precip": precip.round(1), "atend_idosos": atend,
            "prop_idosos": info["prop_idosos"], "prev_comorb": info["prev_comorb"],
            "cap_resposta": info["cap_resposta"],
        }))
    df = pd.concat(frames, ignore_index=True)
    if salvar:
        DIR_DEMO.mkdir(parents=True, exist_ok=True)
        df.to_parquet(DIR_DEMO / "base_demo.parquet", index=False)
    return df


def carregar(modo: str = "demo") -> pd.DataFrame:
    if modo == "real":
        return carregar_real()
    f = DIR_DEMO / "base_demo.parquet"
    return pd.read_parquet(f) if f.exists() else gerar_demo()
