# -*- coding: utf-8 -*-
"""
Operação nacional do ClimaSênior: os 5.570 municípios do Brasil, de 2026 em diante.

Unidade climática: a célula de 0,5° da CPC Global Unified Temperature (NOAA) que
contém a sede municipal; municípios da mesma célula compartilham a exposição.
Unidade do índice: o município (sensibilidade própria, do Censo 2022).

A cada execução:
  1. (uma vez) municípios, sedes e população 60+/80+ do IBGE; climatologia CPC 2014-2025;
  2. dias de 2026 já publicados pela CPC (observação);
  3. previsão de 7 dias e os 7 dias anteriores do modelo, em lotes, para cada célula;
  4. preenchimento de lacunas (dias entre o fim da CPC e a janela recente) com a
     previsão histórica do modelo, dentro de um orçamento de chamadas por execução;
  5. correção do desvio do modelo frente à CPC, EHF, IVC e exportação do painel.

Dias guardados em data/clima/AAAA/AAAA-MM-DD.csv (uma linha por célula), o que
mantém o repositório pequeno e torna a virada de ano automática.

Uso:
    python -m climasenior.brasil                   # operação real
    python -m climasenior.brasil --complemento     # só preenche lacunas (execuções extras)
    python -m climasenior.brasil --simular         # teste sem rede
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import cpc as CPC
from . import ehf as EHF
from . import fontes as F
from . import __version__

UF_CODIGO = {"RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17, "MA": 21, "PI": 22,
             "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27, "SE": 28, "BA": 29, "MG": 31, "ES": 32,
             "RJ": 33, "SP": 35, "PR": 41, "SC": 42, "RS": 43, "MS": 50, "MT": 51, "GO": 52, "DF": 53}
UF_NOME = {"RO": "Rondônia", "AC": "Acre", "AM": "Amazonas", "RR": "Roraima", "PA": "Pará", "AP": "Amapá",
           "TO": "Tocantins", "MA": "Maranhão", "PI": "Piauí", "CE": "Ceará", "RN": "Rio Grande do Norte",
           "PB": "Paraíba", "PE": "Pernambuco", "AL": "Alagoas", "SE": "Sergipe", "BA": "Bahia",
           "MG": "Minas Gerais", "ES": "Espírito Santo", "RJ": "Rio de Janeiro", "SP": "São Paulo",
           "PR": "Paraná", "SC": "Santa Catarina", "RS": "Rio Grande do Sul", "MS": "Mato Grosso do Sul",
           "MT": "Mato Grosso", "GO": "Goiás", "DF": "Distrito Federal"}

ANOS_CLIMATOLOGIA = list(range(2014, 2026))
ORCAMENTO = int(os.environ.get("CLIMASENIOR_ORCAMENTO", "4500"))   # chamadas Open-Meteo por execução
LIMITE_DIARIO = int(os.environ.get("CLIMASENIOR_LIMITE_DIARIO", "9500"))  # abaixo das 10.000 diárias gratuitas
DIAS_PASSADOS = 7
DIAS_FUTUROS = 7
PILOTO = "RM Grande São Luís (piloto)"
PRIORIDADE_FONTE = {"cpc": 0, "modelo": 1}


class Pastas:
    def __init__(self, base: Path, site: Path):
        self.ref, self.clima, self.prev, self.log = base / "ref", base / "clima", base / "previsao", base / "log"
        self.site = site
        for p in (self.ref, self.clima, self.prev, self.log, self.site):
            p.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Utilidades
# =============================================================================
def _ler_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _gravar_json(p: Path, obj, compacto=True):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":") if compacto else None,
                            indent=None if compacto else 2, default=str), encoding="utf-8")


def _r(x, n=1):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def _lista(v, n=1):
    v = np.asarray(v, dtype=float)
    return [None if not np.isfinite(x) else (int(round(x)) if n == 0 else round(float(x), n)) for x in v]


# =============================================================================
# 1. Território e população
# =============================================================================
def territorio(cliente, P: Pastas, log) -> pd.DataFrame:
    arq = P.ref / "municipios_br.csv"
    if arq.exists():
        return pd.read_csv(arq, dtype={"cod_ibge": str, "celula": str})
    log("  municípios do Brasil (IBGE)")
    m = F.municipios_brasil(cliente)
    log(f"    {len(m)} municípios")
    co = F.coordenadas_sedes(cliente)
    m = m.merge(co, on="cod_ibge", how="left")
    sem = m[m["lat"].isna()]
    for i, r in sem.iterrows():                     # sedes fora do conjunto aberto: geocodifica
        try:
            g = F.geocodificar(cliente, r["nome"], UF_NOME[r["uf"]])
        except F.ErroFonte:
            g = None
        if g:
            m.loc[i, ["lat", "lon"]] = g
    if m["lat"].isna().any():
        log(f"    sem coordenadas: {', '.join(m.loc[m['lat'].isna(), 'nome'] + '/' + m.loc[m['lat'].isna(), 'uf'])}")
    log("  população por idade (IBGE, Censo 2022), por UF")
    partes = []
    for uf, g in m.groupby("uf"):        # até 300 municípios por pedido (limite de valores da API)
        cods = sorted(g["cod_ibge"])
        for i in range(0, len(cods), 300):
            partes.append(F.populacao_por_idade(cliente, cods[i:i + 300]))
    cen = pd.concat(partes, ignore_index=True)
    m = m.merge(cen, on="cod_ibge", how="left")
    m["censo_ausente"] = m["populacao"].isna()
    for c in ("prop60", "prop80"):                  # municípios instalados após o Censo: mediana da UF
        m[c] = m[c].fillna(m.groupby("uf")[c].transform("median"))
    for c in ("lat", "lon", "populacao", "pop60", "pop80", "prop60", "prop80"):
        m[c] = pd.to_numeric(m[c], errors="coerce")
    m["celula"] = None
    m.to_csv(arq, index=False)
    contorno = F.contornos_ufs(cliente)
    if contorno:
        _gravar_json(P.ref / "ufs.json", simplificar_contornos(contorno))
    return m


def simplificar_contornos(gj: dict, casas: int = 2) -> dict:
    """Arredonda e reduz os vértices dos contornos das UFs para o painel."""
    def anel(a):
        pts, ult = [], None
        for x, y in a:
            p = (round(x, casas), round(y, casas))
            if p != ult:
                pts.append(p)
                ult = p
        return pts
    out = []
    for f in gj.get("features", []):
        g = f.get("geometry") or {}
        polis = g.get("coordinates", [])
        if g.get("type") == "Polygon":
            polis = [polis]
        out.append({"id": (f.get("properties") or {}).get("codarea"), "aneis": [anel(r) for p in polis for r in p[:1]]})
    return {"ufs": out}


# =============================================================================
# 2. Climatologia (CPC 2014-2025) e células
# =============================================================================
def climatologia(cliente, m: pd.DataFrame, P: Pastas, log) -> tuple[pd.DataFrame, pd.DataFrame]:
    arq = P.ref / "celulas.csv"
    if arq.exists() and m["celula"].notna().any():
        return pd.read_csv(arq, dtype={"celula": str}), m
    log(f"  climatologia CPC {ANOS_CLIMATOLOGIA[0]}-{ANOS_CLIMATOLOGIA[-1]} (grade de 0,5°)")
    ultimo = ANOS_CLIMATOLOGIA[-1]
    d_ref, lats, lons, tx_ref = CPC.baixar_e_ler(cliente, ultimo, "tmax", log)
    valido = np.isfinite(tx_ref).mean(axis=0) >= 0.9
    ok = m["lat"].notna()
    idx = CPC.atribuir_celulas(lats, lons, valido, list(zip(m.loc[ok, "lat"], m.loc[ok, "lon"])))
    m.loc[ok, "celula"] = [CPC.celula_id(lats[i], lons[j]) for i, j in idx]
    unicas = sorted(set(idx))
    cel_ids = [CPC.celula_id(lats[i], lons[j]) for i, j in unicas]
    ii, jj = np.array([u[0] for u in unicas]), np.array([u[1] for u in unicas])
    log(f"    {len(cel_ids)} células com sede municipal")

    datas, tx, tn, falhas = [], [], [], []
    for ano in ANOS_CLIMATOLOGIA:
        try:
            if ano == ultimo:
                d1, a1 = d_ref, tx_ref
            else:
                d1, _, _, a1 = CPC.baixar_e_ler(cliente, ano, "tmax", log)
            d2, _, _, a2 = CPC.baixar_e_ler(cliente, ano, "tmin", log)
        except F.ErroFonte as e:
            log(f"    aviso: CPC {ano} indisponível ({e}); seguindo sem este ano")
            falhas.append(ano)
            continue
        if d1 != d2:
            raise F.ErroFonte(f"CPC {ano}: datas de tmax e tmin não coincidem")
        datas += d1
        tx.append(a1[:, ii, jj])
        tn.append(a2[:, ii, jj])
        if ano == ultimo:                            # dezembro do último ano: aquecimento da aclimatação
            dez = [k for k, d in enumerate(d1) if d.month == 12]
            _gravar_cpc(P, [d1[k] for k in dez], cel_ids, a1[dez][:, ii, jj], a2[dez][:, ii, jj])
    if len(ANOS_CLIMATOLOGIA) - len(falhas) < min(8, len(ANOS_CLIMATOLOGIA)):
        raise F.ErroFonte(f"CPC: só {len(ANOS_CLIMATOLOGIA) - len(falhas)} anos de climatologia; tente de novo mais tarde")
    tx, tn = np.concatenate(tx), np.concatenate(tn)
    tmed = pd.DataFrame((tx + tn) / 2, index=pd.to_datetime(datas), columns=cel_ids)
    tmed = tmed.interpolate(limit=3, limit_area="inside")

    linhas = []
    pontos = m.dropna(subset=["celula"]).groupby("celula")[["lat", "lon"]].mean()
    nmun = m.groupby("celula").size()
    for k, cid in enumerate(cel_ids):
        try:
            c = EHF.climatologia(tmed[cid])
        except ValueError:
            c = {"p50": np.nan, "p90": np.nan, "p95": np.nan, "ehf85": np.nan, "n_dias": 0, "n_ehf_positivo": 0}
        linhas.append({"celula": cid, "lat": lats[ii[k]], "lon": lons[jj[k]],
                       "lat_ponto": round(float(pontos.loc[cid, "lat"]), 4), "lon_ponto": round(float(pontos.loc[cid, "lon"]), 4),
                       "n_municipios": int(nmun.get(cid, 0)), **c})
    cel = pd.DataFrame(linhas)
    falha = cel["ehf85"].isna().sum()
    if falha:
        log(f"    aviso: {falha} células sem EHF85 estimável (série curta)")
    cel.to_csv(arq, index=False)
    m.to_csv(P.ref / "municipios_br.csv", index=False)
    return cel, m


# =============================================================================
# 3. Série diária por célula
# =============================================================================
def _arquivo_dia(P: Pastas, d: date) -> Path:
    return P.clima / str(d.year) / f"{d.isoformat()}.csv"


def gravar_dias(P: Pastas, df: pd.DataFrame):
    """df: data, celula, tmax, tmin, tapmax, fonte. A CPC (observação) prevalece sobre o modelo."""
    if df.empty:
        return
    df = df.dropna(subset=["tmax", "tmin"])
    for d, g in df.groupby(df["data"].dt.date):
        arq = _arquivo_dia(P, d)
        arq.parent.mkdir(parents=True, exist_ok=True)
        novo = g.drop(columns=["data"])
        if arq.exists():
            novo = pd.concat([pd.read_csv(arq, dtype={"celula": str}), novo], ignore_index=True)
        novo["_p"] = novo["fonte"].map(PRIORIDADE_FONTE).fillna(9)
        novo = (novo.sort_values(["celula", "_p"], kind="stable")
                    .drop_duplicates("celula", keep="first").drop(columns="_p"))
        novo[["tmax", "tmin", "tapmax"]] = novo[["tmax", "tmin", "tapmax"]].round(1)
        novo.sort_values("celula")[["celula", "tmax", "tmin", "tapmax", "fonte"]].to_csv(arq, index=False)


def _gravar_cpc(P, datas, cel_ids, tx, tn):
    linhas = []
    for k, d in enumerate(datas):
        linhas.append(pd.DataFrame({"data": pd.Timestamp(d), "celula": cel_ids, "tmax": tx[k],
                                    "tmin": tn[k], "tapmax": np.nan, "fonte": "cpc"}))
    if linhas:
        gravar_dias(P, pd.concat(linhas, ignore_index=True))


def ler_dias(P: Pastas, d0: date, d1: date) -> pd.DataFrame:
    partes = []
    d = d0
    while d <= d1:
        arq = _arquivo_dia(P, d)
        if arq.exists():
            partes.append(pd.read_csv(arq, dtype={"celula": str}).assign(data=pd.Timestamp(d)))
        d += timedelta(days=1)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(
        columns=["celula", "tmax", "tmin", "tapmax", "fonte", "data"])


def cpc_ano_corrente(cliente, cel: pd.DataFrame, P: Pastas, hoje: date, log) -> date | None:
    """Ingere dias publicados pela CPC no ano corrente (e no anterior em janeiro). Devolve o último dia."""
    estado = _ler_json(P.ref / "fontes.json") or {}
    anos = [hoje.year] if hoje.month > 1 else [hoje.year - 1, hoje.year]
    ultimo = estado.get("cpc_ultimo_dia")
    for ano in anos:
        chave = f"cpc_{ano}"
        try:
            mod = cliente.ultima_modificacao(CPC.cliente_url(ano, "tmax"))
        except Exception:  # noqa: BLE001
            mod = None
        if mod is None or mod == estado.get(chave):
            continue
        log(f"  CPC {ano} atualizada ({mod})")
        try:
            d1, lats, lons, tx = CPC.baixar_e_ler(cliente, ano, "tmax", log)
            d2, _, _, tn = CPC.baixar_e_ler(cliente, ano, "tmin", log)
        except Exception as e:  # noqa: BLE001 - arquivo do ano ainda não publicado ou servidor fora
            log(f"    não foi possível ler a CPC {ano}: {e}")
            continue
        if d1 != d2:
            log("    aviso: datas de tmax e tmin diferentes; ignorado")
            continue
        pos_lat = {f"{la:.2f}": i for i, la in enumerate(lats)}
        pos_lon = {f"{lo:.2f}": j for j, lo in enumerate(lons)}
        ii = np.array([pos_lat[c.split("_")[0]] for c in cel["celula"]])
        jj = np.array([pos_lon[c.split("_")[1]] for c in cel["celula"]])
        x, n = tx[:, ii, jj], tn[:, ii, jj]
        tem = np.isfinite(x).mean(axis=1) >= 0.5
        dias = [d for d, t in zip(d1, tem) if t]
        if dias:
            k = [i for i, t in enumerate(tem) if t]
            _gravar_cpc(P, dias, list(cel["celula"]), x[k], n[k])
            ultimo = max(dias).isoformat() if not ultimo else max(ultimo, max(dias).isoformat())
            log(f"    {len(dias)} dias, até {max(dias)}")
        estado[chave] = mod
    estado["cpc_ultimo_dia"] = ultimo
    _gravar_json(P.ref / "fontes.json", estado, compacto=False)
    return date.fromisoformat(ultimo) if ultimo else None


# =============================================================================
# 4. Modelo: previsão, lacunas e desvio
# =============================================================================
def _pontos(cel: pd.DataFrame, m: pd.DataFrame, apenas=None) -> list[dict]:
    peso = m.groupby("celula")["pop60"].sum()
    c = cel.assign(peso=cel["celula"].map(peso).fillna(0)).sort_values("peso", ascending=False)
    if apenas is not None:
        c = c[c["celula"].isin(apenas)]
    return [{"cod_ibge": r.celula, "lat": r.lat_ponto, "lon": r.lon_ponto} for r in c.itertuples()]


def previsao(cliente, cel, m, P: Pastas, hoje: date, orc: list, log, pausa) -> int:
    pts = _pontos(cel, m)
    log(f"  previsão de {DIAS_FUTUROS} dias e {DIAS_PASSADOS} dias anteriores: {len(pts)} células")
    df = F.baixar_lotes(cliente, F.OPEN_METEO_PREVISAO, pts,
                        {"past_days": DIAS_PASSADOS, "forecast_days": DIAS_FUTUROS}, C.FUSO, orc, pausa=pausa, log=log)
    if df.empty:
        return 0
    df = df.rename(columns={"chave": "celula"})
    passado = df[df["data"] < pd.Timestamp(hoje)].assign(fonte="modelo")
    gravar_dias(P, passado)
    fut = df[df["data"] >= pd.Timestamp(hoje)].assign(gerado_em=hoje.isoformat())
    arq = P.prev / "ultima.csv"
    if arq.exists():                                 # células que ficaram sem previsão hoje mantêm a anterior
        ant = pd.read_csv(arq, dtype={"celula": str}, parse_dates=["data"])
        ant = ant[(ant["data"] >= pd.Timestamp(hoje)) & ~ant["celula"].isin(fut["celula"])]
        fut = pd.concat([fut, ant], ignore_index=True)
    fut.sort_values(["celula", "data"]).assign(data=lambda x: x["data"].dt.strftime("%Y-%m-%d")).round(
        {"tmax": 1, "tmin": 1, "tapmax": 1}).to_csv(arq, index=False)
    return df["celula"].nunique()


def faltantes(P: Pastas, cel: pd.DataFrame, d0: date, d1: date):
    """(dias, células, matriz booleana do que falta na série consolidada)."""
    dias = pd.date_range(d0, d1, freq="D")
    cols = pd.Index(list(cel["celula"]))
    arr = np.ones((len(dias), len(cols)), dtype=bool)
    tem = ler_dias(P, d0, d1)
    if not tem.empty:
        tem = tem.dropna(subset=["tmax", "tmin"])
        r, c = dias.get_indexer(tem["data"]), cols.get_indexer(tem["celula"])
        ok = (r >= 0) & (c >= 0)
        arr[r[ok], c[ok]] = False
    return dias, cols, arr


def lacunas_e_vies(cliente, cel, m, P: Pastas, hoje: date, cpc_fim: date | None, orc: list, log, pausa) -> dict:
    inicio = date(C.ANO_INICIO_OPERACIONAL, 1, 1) - timedelta(days=31)
    fim = hoje - timedelta(days=DIAS_PASSADOS + 1)
    vies = pd.read_csv(P.ref / "vies.csv", dtype={"celula": str}) if (P.ref / "vies.csv").exists() else \
        pd.DataFrame(columns=["celula", "vies_tmax", "vies_tmin", "n_dias"])
    sem_vies = set(cel["celula"]) - set(vies["celula"])

    # 4a. desvio: 14 dias centrados no fim da CPC — 7 de sobreposição para o desvio e
    #     7 que já completam a lacuna logo após a observação, com uma só chamada por célula
    if cpc_fim and sem_vies and orc[0] > 0:
        a, b = cpc_fim - timedelta(days=6), min(cpc_fim + timedelta(days=7), max(fim, cpc_fim))
        log(f"  desvio do modelo frente à CPC ({a} a {b}): {len(sem_vies)} células")
        df = F.baixar_lotes(cliente, F.OPEN_METEO_HISTORICO, _pontos(cel, m, sem_vies),
                            {"start_date": a.isoformat(), "end_date": b.isoformat()}, C.FUSO, orc, pausa=pausa, log=log)
        if not df.empty:
            df = df.rename(columns={"chave": "celula"})
            obs = ler_dias(P, a, b)
            obs = obs[obs["fonte"] == "cpc"]
            j = df.merge(obs, on=["data", "celula"], suffixes=("_m", "_o")).dropna(subset=["tmax_m", "tmax_o"])
            novos = (j.assign(dx=j["tmax_m"] - j["tmax_o"], dn=j["tmin_m"] - j["tmin_o"])
                      .groupby("celula").agg(vies_tmax=("dx", "mean"), vies_tmin=("dn", "mean"), n_dias=("dx", "size"))
                      .reset_index())
            novos = novos[novos["n_dias"] >= 5].round(2)
            vies = pd.concat([vies[~vies["celula"].isin(novos["celula"])], novos], ignore_index=True)
            vies.to_csv(P.ref / "vies.csv", index=False)
            gravar_dias(P, df.assign(fonte="modelo"))     # não substitui a CPC; completa células sem ela

    # 4b. lacunas em blocos de 14 dias (1 chamada por célula e bloco)
    pend = 0
    if fim >= inicio:
        dias_f, cols_f, falta = faltantes(P, cel, inicio, fim)
        while orc[0] > 0 and falta.any():
            k0 = int(np.argmax(falta.any(axis=1)))
            d_ini = dias_f[k0].date()
            d_fim = min(d_ini + timedelta(days=13), fim)
            k1 = dias_f.get_loc(pd.Timestamp(d_fim))
            alvo_mask = falta[k0:k1 + 1].any(axis=0)
            alvo = list(cols_f[alvo_mask])
            log(f"  lacunas {d_ini} a {d_fim}: {len(alvo)} células")
            df = F.baixar_lotes(cliente, F.OPEN_METEO_HISTORICO, _pontos(cel, m, alvo),
                                {"start_date": d_ini.isoformat(), "end_date": d_fim.isoformat()},
                                C.FUSO, orc, pausa=pausa, log=log)
            if df.empty:
                break
            df = df.rename(columns={"chave": "celula"}).assign(fonte="modelo")
            gravar_dias(P, df)
            pedidas = set(df["celula"])
            # marca o bloco como tentado (mesmo onde a fonte não tem dado), para nunca repetir em laço
            falta[k0:k1 + 1, [c in pedidas for c in cols_f]] = False
            if len(pedidas) < len(alvo):          # orçamento acabou no meio do bloco
                break
        pend = int(faltantes(P, cel, inicio, fim)[2].sum())
    sem_vies = len(set(cel["celula"]) - set(vies["celula"]))
    _gravar_json(P.ref / "pendencias.json", {"data": hoje.isoformat(), "celula_dias_faltando": pend,
                                              "celulas_sem_vies": sem_vies}, compacto=False)
    return {"pendentes": pend, "sem_vies": sem_vies, "vies": vies}


# =============================================================================
# 5. Indicadores
# =============================================================================
def sensibilidade(m: pd.DataFrame) -> np.ndarray:
    p60, p80 = pd.to_numeric(m["prop60"], errors="coerce"), pd.to_numeric(m["prop80"], errors="coerce")
    q60, q80 = np.nanpercentile(p60, 99), np.nanpercentile(p80, 99)
    return (0.7 * np.clip(p60 / q60, 0, 1) + 0.3 * np.clip(p80 / q80, 0, 1)).to_numpy(dtype=float)


def capacidade(m: pd.DataFrame, P: Pastas) -> np.ndarray | None:
    arq = P.ref / "capacidade.csv"
    if not arq.exists():
        return None
    cap = pd.read_csv(arq, sep=";", dtype={"cod_ibge": str})
    taxa = m["cod_ibge"].map(dict(zip(cap["cod_ibge"], cap["estab_atencao_basica"]))) / m["populacao"] * 1e4
    if taxa.notna().mean() < 0.9:
        return None
    q = np.nanpercentile(taxa, 99)
    return (1 - np.clip(taxa / q, 0, 1)).fillna(0.5).to_numpy()


def calcular(cel: pd.DataFrame, m: pd.DataFrame, vies: pd.DataFrame, P: Pastas, hoje: date) -> dict:
    d0 = date(C.ANO_INICIO_OPERACIONAL, 1, 1) - timedelta(days=31)
    obs = ler_dias(P, d0, hoje - timedelta(days=1))
    prev = pd.DataFrame()
    if (P.prev / "ultima.csv").exists():
        prev = pd.read_csv(P.prev / "ultima.csv", dtype={"celula": str}, parse_dates=["data"])
        prev = prev[prev["data"] >= pd.Timestamp(hoje)].assign(fonte="previsao")
    tudo = pd.concat([obs, prev], ignore_index=True)
    cols = list(cel["celula"])
    ult = tudo["data"].max() if not tudo.empty else pd.Timestamp(hoje)
    dias = pd.date_range(d0, max(ult, pd.Timestamp(hoje)), freq="D")

    def piv(v):
        return tudo.pivot_table(index="data", columns="celula", values=v, aggfunc="first").reindex(index=dias, columns=cols)
    tx, tn, ta = piv("tmax"), piv("tmin"), piv("tapmax")
    fonte = tudo.pivot_table(index="data", columns="celula", values="fonte", aggfunc="first").reindex(index=dias, columns=cols)

    v = vies.set_index("celula").reindex(cols)
    modelo = fonte.isin(["modelo", "previsao"])
    tx = tx - modelo * v["vies_tmax"].fillna(0).to_numpy()
    tn = tn - modelo * v["vies_tmin"].fillna(0).to_numpy()

    t = (tx + tn) / 2
    t3 = (t + t.shift(-1) + t.shift(-2)) / 3
    t30 = t.shift(1).rolling(30, min_periods=24).mean()
    ref = cel.set_index("celula").reindex(cols)
    p50, p95, e85 = ref["p50"].to_numpy(), ref["p95"].to_numpy(), ref["ehf85"].to_numpy()
    sig = t3 - p95
    accl = t3 - t30
    with np.errstate(invalid="ignore"):
        ehf = sig * np.maximum(1.0, accl)
    sev = (ehf / e85).where(ehf > 0, 0.0).where(ehf.notna())
    frac = ((t3 - p50) / (p95 - p50)).clip(0, 1)
    with np.errstate(invalid="ignore"):
        E = (0.5 + 0.5 * np.minimum(sev / 3, 1)).where(ehf > 0, 0.5 * frac).where(ehf.notna())
    quente = (ehf > 0).astype(int)
    consec = _consecutivos(quente)

    w = dict(C.PESOS_IVC)
    S = sensibilidade(m)
    Cc = capacidade(m, P)
    if Cc is None:
        tot = w["exposicao"] + w["sensibilidade"]
        w = {"exposicao": w["exposicao"] / tot, "sensibilidade": w["sensibilidade"] / tot, "capacidade": 0.0}
        Cc = np.zeros(len(m))
    idx = pd.Index(cols).get_indexer(m["celula"])
    Em = E.to_numpy(dtype=float)[:, np.where(idx >= 0, idx, 0)]
    Em[:, idx < 0] = np.nan
    ivc = 100 * (w["exposicao"] * Em + w["sensibilidade"] * np.asarray(S, float) + w["capacidade"] * np.asarray(Cc, float))
    return {"dias": dias, "cols": cols, "tx": tx, "tn": tn, "ta": ta, "t3": t3, "ehf": ehf, "sev": sev, "E": E,
            "consec": consec, "fonte": fonte, "ivc": ivc, "S": S, "C": Cc if w["capacidade"] else None, "pesos": w,
            "idx_cel": idx}


def _consecutivos(q: pd.DataFrame) -> pd.DataFrame:
    a = q.to_numpy()
    out = np.zeros_like(a)
    for k in range(a.shape[0]):
        out[k] = (out[k - 1] + 1) * a[k] if k else a[k]
    return pd.DataFrame(out, index=q.index, columns=q.columns)


# =============================================================================
# 6. Exportação do painel
# =============================================================================
def exportar(r: dict, cel: pd.DataFrame, m: pd.DataFrame, P: Pastas, hoje: date, modo: str,
             avisos: list, extra: dict) -> list[str]:
    site = P.site
    nomes = m["nome"].tolist()
    if modo != "real":   # na simulação, nenhum valor simulado leva o nome de um município real
        nomes = [f"Município fictício {k + 1}" for k in range(len(m))]
    piloto = [c for c, n, u in zip(m["cod_ibge"], m["nome"], m["uf"]) if u == "MA" and n in
              {x["nome"] for x in C.MUNICIPIOS_OPERACIONAIS}]
    _gravar_json(site / "municipios.json", {
        "cod": m["cod_ibge"].tolist(), "nome": nomes, "uf": m["uf"].tolist(),
        "lat": _lista(m["lat"], 3), "lon": _lista(m["lon"], 3), "pop": _lista(m["populacao"], 0),
        "pop60": _lista(m["pop60"], 0), "p60": _lista(m["prop60"], 4), "p80": _lista(m["prop80"], 4),
        "S": _lista(r["S"], 3), "C": _lista(r["C"], 3) if r["C"] is not None else None,
        "cel": [int(i) for i in r["idx_cel"]], "celulas": r["cols"], "regioes": {PILOTO: piloto}})

    dias = r["dias"]
    inicio = pd.Timestamp(date(C.ANO_INICIO_OPERACIONAL, 1, 1))
    tem_ivc = np.isfinite(r["ivc"]).any(axis=1)
    validos = [k for k, d in enumerate(dias) if d >= inicio and tem_ivc[k]]
    cod_f = {"cpc": "o", "modelo": "m", "previsao": "p"}
    lista_dias = []
    (site / "dia").mkdir(parents=True, exist_ok=True)
    for k in validos:
        d = dias[k]
        f = r["fonte"].iloc[k].map(cod_f).fillna("-")
        dom = f.value_counts().index[0] if len(f) else "-"
        _gravar_json(site / "dia" / f"{d:%Y-%m-%d}.json", {
            "d": f"{d:%Y-%m-%d}", "f": dom, "ivc": _lista(r["ivc"][k], 0),
            "tmax": _lista(r["tx"].iloc[k], 1), "sev": _lista(r["sev"].iloc[k], 2),
            "dc": [int(x) for x in r["consec"].iloc[k]]})
        lista_dias.append([f"{d:%Y-%m-%d}", dom])

    for ano in sorted({dias[k].year for k in validos}):
        ks = [k for k in validos if dias[k].year == ano]
        sub = {c: (r[c].iloc[ks] if hasattr(r[c], "iloc") else None) for c in ("tx", "tn", "ta", "t3", "sev", "E", "fonte")}
        ref = cel.set_index("celula")
        for uf, g in m.groupby("uf"):
            cs = sorted({r["cols"][i] for i in g["celula"].pipe(lambda s: pd.Index(r["cols"]).get_indexer(s)) if i >= 0})
            bloco = {}
            for c in cs:
                bloco[c] = {"tmax": _lista(sub["tx"][c], 1), "tmin": _lista(sub["tn"][c], 1),
                            "tap": _lista(sub["ta"][c], 1), "t3": _lista(sub["t3"][c], 2),
                            "sev": _lista(sub["sev"][c], 2), "E": _lista(sub["E"][c], 3),
                            "f": "".join(sub["fonte"][c].map(cod_f).fillna("-")),
                            "p50": _r(ref.loc[c, "p50"], 2), "p95": _r(ref.loc[c, "p95"], 2)}
            _gravar_json(site / "serie" / str(ano) / f"{uf}.json",
                         {"ano": ano, "d": [f"{dias[k]:%Y-%m-%d}" for k in ks], "cel": bloco})

    if (P.ref / "ufs.json").exists():
        (site / "ufs.json").write_text((P.ref / "ufs.json").read_text(encoding="utf-8"), encoding="utf-8")
    vies = extra.get("vies")
    _gravar_json(site / "meta.json", {
        "versao": __version__, "modo": modo, "abrangencia": "Brasil",
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_referencia": hoje.isoformat(), "dias": lista_dias,
        "n_municipios": int(len(m)), "n_celulas": int(len(cel)),
        "ultimo_dia_cpc": extra.get("cpc_fim"), "pesos": r["pesos"], "limiar": C.LIMIAR_ACAO,
        "capacidade_disponivel": r["C"] is not None, "avisos": avisos,
        "pendencias": {"celula_dias_faltando": extra.get("pendentes"), "celulas_sem_vies": extra.get("sem_vies")},
        "vies_modelo": {"tmax_mediana": _r(vies["vies_tmax"].median(), 2) if vies is not None and len(vies) else None,
                        "tmax_p10": _r(vies["vies_tmax"].quantile(.1), 2) if vies is not None and len(vies) else None,
                        "tmax_p90": _r(vies["vies_tmax"].quantile(.9), 2) if vies is not None and len(vies) else None,
                        "celulas": int(len(vies)) if vies is not None else 0},
        "fontes": [
            {"nome": "CPC Global Unified Temperature (NOAA PSL)", "url": "https://psl.noaa.gov/data/gridded/data.cpc.globaltemp.html",
             "uso": "temperatura observada (grade de 0,5°) e climatologia 2014-2025"},
            {"nome": "Open-Meteo (previsão e previsão histórica)", "url": "https://open-meteo.com", "licenca": "CC BY 4.0",
             "uso": "previsão de 7 dias, dias recentes e lacunas da observação"},
            {"nome": "IBGE, Censo Demográfico 2022 (tabela 9514)", "url": "https://sidra.ibge.gov.br/tabela/9514",
             "uso": "população total, 60+ e 80+ por município"},
            {"nome": "IBGE, localidades e malhas", "url": "https://servicodados.ibge.gov.br/api/docs", "uso": "municípios e contornos das UFs"},
            {"nome": "kelvins/municipios-brasileiros", "url": "https://github.com/kelvins/municipios-brasileiros",
             "licenca": "MIT", "uso": "coordenadas das sedes municipais"},
        ],
    })
    return [d for d, _ in lista_dias]


# =============================================================================
# Orquestração
# =============================================================================
def executar(cliente=None, hoje: date | None = None, modo="real", complemento=False, orcamento=None,
             base: Path | None = None, site: Path | None = None, pausa=10.5, verbose=True) -> dict:
    P = Pastas(base or C.DIR_DADOS, site or C.DIR_SITE_DADOS)
    linhas_log = []

    def log(*a):
        s = " ".join(str(x) for x in a)
        linhas_log.append(s)
        if verbose:
            print(s, flush=True)

    cliente = cliente or F.ClienteHTTP()
    hoje = hoje or datetime.now(timezone(timedelta(hours=-3))).date()
    uso = _ler_json(P.ref / "uso_api.json") or {}
    usado = uso.get("chamadas", 0) if uso.get("data") == hoje.isoformat() else 0
    orc = [max(0, min(orcamento if orcamento is not None else ORCAMENTO, LIMITE_DIARIO - usado))]
    orc_inicial = orc[0]
    avisos = []
    log(f"[ClimaSênior {__version__} · Brasil] referência {hoje} | modo {modo} | orçamento {orc[0]} chamadas")
    try:
        if complemento:   # execuções extras: só completam lacunas e desvio; a previsão é da execução diária
            p = _ler_json(P.ref / "pendencias.json")
            if not p or (not p.get("celula_dias_faltando") and not p.get("celulas_sem_vies")):
                log("  nada pendente")
                return {"alterou": False}
        log("[1/5] Território e população")
        m = territorio(cliente, P, log)
        log("[2/5] Climatologia e células")
        cel, m = climatologia(cliente, m, P, log)
        log("[3/5] Observação CPC do ano corrente")
        cpc_fim = cpc_ano_corrente(cliente, cel, P, hoje, log)
        log("[4/5] Modelo: previsão, lacunas e desvio")
        if not complemento:
            n = previsao(cliente, cel, m, P, hoje, orc, log, pausa)
            if n < len(cel):
                avisos.append(f"Previsão de hoje obtida para {n} de {len(cel)} células; as demais usam a previsão anterior")
        info = lacunas_e_vies(cliente, cel, m, P, hoje, cpc_fim, orc, log, pausa)
        pend = _ler_json(P.ref / "pendencias.json")
        pend["previsao_em"] = hoje.isoformat()
        _gravar_json(P.ref / "pendencias.json", pend, compacto=False)
        if info["pendentes"]:
            avisos.append(f"Série ainda incompleta: {info['pendentes']} combinações de célula e dia serão "
                          "completadas nas próximas execuções")
        if info["sem_vies"]:
            avisos.append(f"{info['sem_vies']} células ainda sem correção do desvio do modelo")
        if capacidade(m, P) is None:
            avisos.append("Capacidade de resposta ainda não carregada (CNES): o IVC usa exposição e sensibilidade")
        if m["censo_ausente"].any():
            avisos.append(f"{int(m['censo_ausente'].sum())} municípios instalados após o Censo 2022 usam a mediana da UF")
        log("[5/5] EHF, IVC e painel")
        r = calcular(cel, m, info["vies"], P, hoje)
        dias = exportar(r, cel, m, P, hoje, modo, avisos,
                        {"cpc_fim": cpc_fim.isoformat() if cpc_fim else None, **info})
        k = list(r["dias"]).index(pd.Timestamp(hoje)) if pd.Timestamp(hoje) in r["dias"] else None
        if k is not None:
            v = r["ivc"][k]
            if np.isfinite(v).any():
                log(f"  {len(dias)} dias no painel | hoje: {int(np.nansum(v >= C.LIMIAR_ACAO))} municípios com IVC >= "
                    f"{C.LIMIAR_ACAO}; IVC máximo {np.nanmax(v):.0f}")
        log(f"  chamadas restantes: {orc[0]}")
        return {"alterou": True, "dias": dias, "avisos": avisos, **{k: info[k] for k in ("pendentes", "sem_vies")}}
    except Exception:
        import traceback
        log("ERRO:\n" + traceback.format_exc())
        raise
    finally:
        _gravar_json(P.ref / "uso_api.json", {"data": hoje.isoformat(), "chamadas": usado + (orc_inicial - orc[0])},
                     compacto=False)
        (P.log / "ultima_execucao.log").write_text("\n".join(linhas_log) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Atualiza o ClimaSênior para todo o Brasil")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--complemento", action="store_true", help="só completa lacunas pendentes")
    ap.add_argument("--data")
    ap.add_argument("--orcamento", type=int)
    ap.add_argument("--saida", help="pasta para dados e painel (padrão: data/ e site/data/)")
    a = ap.parse_args()
    hoje = date.fromisoformat(a.data) if a.data else None
    base = site = None
    if a.simular and not a.saida:
        a.saida = str(C.RAIZ / "simulacao_br")
    if a.saida:
        base, site = Path(a.saida) / "data", Path(a.saida) / "site" / "data"
    cliente = None
    if a.simular:
        from .simulacao_br import ClienteSimuladoBrasil
        cliente = ClienteSimuladoBrasil(hoje)
    r = executar(cliente, hoje, "simulacao" if a.simular else "real", a.complemento, a.orcamento, base, site,
                 pausa=0 if a.simular else 10.5)
    if not r.get("alterou"):
        Path(".sem_alteracoes").write_text("1")
    sys.exit(0)


if __name__ == "__main__":
    main()
