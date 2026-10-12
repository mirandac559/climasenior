# -*- coding: utf-8 -*-
"""
API do ClimaSênior (FastAPI).

Execução:  uvicorn api.main:app --reload --port 8000
Docs:      http://localhost:8000/docs
"""
from __future__ import annotations
import json
from datetime import date
from typing import Optional
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from climasenior.config import DIR_MODELOS, MUNICIPIOS_RM, FAIXAS_IVC, faixa_ivc
from climasenior import __version__

app = FastAPI(title="ClimaSênior API", version=__version__,
              description="Índice de Vulnerabilidade Climática para a saúde da população idosa.")

_IVC: Optional[pd.DataFrame] = None
_RESUMO: Optional[dict] = None


def _carregar(versao: str = "v1"):
    global _IVC, _RESUMO
    f = DIR_MODELOS / f"ivc_{versao}.parquet"
    if not f.exists():
        raise HTTPException(503, "Modelo não treinado. Execute: python -m climasenior.pipeline")
    _IVC = pd.read_parquet(f)
    _RESUMO = json.load(open(DIR_MODELOS / f"resumo_{versao}.json", encoding="utf-8"))


def _ivc() -> pd.DataFrame:
    if _IVC is None:
        _carregar()
    return _IVC


class Registro(BaseModel):
    data: date
    cod_ibge: str
    municipio: str
    tmax: float
    ind_calor: float
    dias_consec_calor: int
    demanda_prevista_d3: float
    risco_previsto: int
    IVC: float
    faixa: str
    cor: str
    conduta: str


def _fmt(r) -> dict:
    rot, cor, cond = faixa_ivc(r["IVC"])
    return dict(data=r["data"].date(), cod_ibge=r["cod_ibge"], municipio=r["municipio"],
                tmax=float(r["tmax"]), ind_calor=float(round(r["ind_calor"], 1)),
                dias_consec_calor=int(r["dias_consec_calor"]),
                demanda_prevista_d3=float(r["demanda_prevista_d3"]),
                risco_previsto=int(r["risco_previsto"]), IVC=float(r["IVC"]),
                faixa=rot, cor=cor, conduta=cond)


@app.get("/saude", tags=["sistema"])
def saude():
    """Verificação de disponibilidade e metadados do modelo carregado."""
    _ivc()
    return {"status": "ok", "versao_api": __version__, "modo": _RESUMO.get("modo"),
            "modelo": _RESUMO.get("versao"), "aviso": _RESUMO.get("_aviso"),
            "lstm_disponivel": _RESUMO["metricas"].get("lstm_disponivel")}


@app.get("/municipios", tags=["território"])
def municipios():
    return [dict(cod_ibge=k, **v) for k, v in MUNICIPIOS_RM.items()]


@app.get("/faixas", tags=["protocolo"])
def faixas():
    """Faixas do IVC e protocolo de resposta graduada."""
    return [dict(de=a, ate=b, faixa=r, cor=c, conduta=d) for a, b, r, c, d in FAIXAS_IVC]


@app.get("/ivc/atual", response_model=list[Registro], tags=["ivc"])
def ivc_atual(data_ref: Optional[date] = Query(None, description="Padrão: última data disponível")):
    """IVC de todos os municípios em uma data (painel de situação)."""
    df = _ivc()
    d = pd.Timestamp(data_ref) if data_ref else df["data"].max()
    sel = df[df["data"] == d]
    if sel.empty:
        raise HTTPException(404, f"Sem dados para {d.date()}")
    return [_fmt(r) for _, r in sel.iterrows()]


@app.get("/ivc/historico/{cod_ibge}", response_model=list[Registro], tags=["ivc"])
def ivc_historico(cod_ibge: str, inicio: Optional[date] = None, fim: Optional[date] = None):
    """Série temporal do IVC para um município."""
    df = _ivc()
    sel = df[df["cod_ibge"] == cod_ibge]
    if sel.empty:
        raise HTTPException(404, "Município não encontrado")
    if inicio: sel = sel[sel["data"] >= pd.Timestamp(inicio)]
    if fim:    sel = sel[sel["data"] <= pd.Timestamp(fim)]
    return [_fmt(r) for _, r in sel.sort_values("data").iterrows()]


@app.get("/ivc/alertas", tags=["ivc"])
def alertas(limiar: float = Query(60.0, ge=0, le=100), data_ref: Optional[date] = None):
    """Municípios acima do limiar de ação na data (ordenados por IVC)."""
    df = _ivc()
    d = pd.Timestamp(data_ref) if data_ref else df["data"].max()
    sel = df[(df["data"] == d) & (df["IVC"] >= limiar)].sort_values("IVC", ascending=False)
    return {"data": d.date(), "limiar": limiar, "n": int(len(sel)),
            "municipios": [_fmt(r) for _, r in sel.iterrows()]}


@app.get("/validacao", tags=["fase 3"])
def validacao():
    """Métricas, backtesting 2025, curva de limiares e monitor de deriva."""
    _ivc()
    return {k: _RESUMO[k] for k in ("metricas", "backtesting_2025", "curva_limiares", "drift", "_aviso")}
