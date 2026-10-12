# -*- coding: utf-8 -*-
"""
Operação em tempo real do ClimaSênior (v0.4).

A cada execução (diária, no GitHub Actions ou num servidor):
  1. resolve os 13 municípios (códigos IBGE) e lê a população idosa do Censo 2022;
  2. garante a climatologia de referência (ERA5, 2014-2025): P50, P95 e EHF85;
  3. completa a série desde 01/01/2026 com a reanálise ERA5 (dias consolidados);
  4. busca a janela recente e a previsão de 16 dias do modelo e corrige o viés
     do modelo frente ao ERA5 nos dias em que os dois existem;
  5. calcula EHF, severidade e IVC para cada município e dia;
  6. exporta os arquivos do painel em site/data/.

A série é guardada por ano (data/serie/2026.csv, 2027.csv, ...), de modo que a
virada de ano não exige nenhuma intervenção. Se a execução ficar dias parada,
a próxima recupera o intervalo inteiro pelo ERA5.

Uso:
    python -m climasenior.operacional                 # operação real
    python -m climasenior.operacional --simular       # teste sem rede (dados simulados)
    python -m climasenior.operacional --data 2026-10-12
"""
from __future__ import annotations
import argparse
import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import ehf as EHF
from . import fontes as F
from . import __version__

FAIXAS = [(0, 40, "BAIXA"), (40, 60, "MODERADA"), (60, 80, "ALTA"), (80, 101, "MUITO ALTA")]
CONDUTAS = {r: c for _, _, r, _, c in C.FAIXAS_IVC}


def faixa(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    for a, b, r in FAIXAS:
        if a <= v < b:
            return r
    return "MUITO ALTA"


# ----------------------------------------------------------------------------
# Referências (cacheadas em data/ref)
# ----------------------------------------------------------------------------
def _ler_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _gravar_json(p: Path, obj, compacto=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":") if compacto else None,
                     indent=None if compacto else 2, default=str)
    p.write_text(txt, encoding="utf-8")


def municipios(cliente, log) -> list[dict]:
    arq = C.DIR_REF / "municipios.json"
    m = _ler_json(arq)
    if m:
        return m
    log("  resolvendo códigos IBGE dos municípios")
    cods = F.resolver_codigos(cliente, [x["nome"] for x in C.MUNICIPIOS_OPERACIONAIS])
    m = []
    for x in C.MUNICIPIOS_OPERACIONAIS:
        item = dict(x, cod_ibge=cods[x["nome"]])
        try:  # auditoria das coordenadas: não interrompe se a geocodificação falhar
            g = F.geocodificar(cliente, x["nome"])
            if g:
                dist = 111.2 * math.hypot(g[0] - x["lat"], (g[1] - x["lon"]) * math.cos(math.radians(x["lat"])))
                item.update(lat_geocodificada=g[0], lon_geocodificada=g[1], distancia_km=round(dist, 1))
        except F.ErroFonte:
            pass
        m.append(item)
    _gravar_json(arq, m)
    return m


def censo(cliente, muns, log) -> dict:
    arq = C.DIR_REF / "censo2022.json"
    d = _ler_json(arq)
    if d:
        return d
    log("  lendo população por idade (IBGE, Censo 2022)")
    df = F.populacao_por_idade(cliente, [m["cod_ibge"] for m in muns])
    d = {r["cod_ibge"]: {k: r[k] for k in ("populacao", "pop60", "pop80", "prop60", "prop80")}
         for r in df.to_dict(orient="records")}
    _gravar_json(arq, {"fonte": "IBGE, Censo Demográfico 2022, tabela 9514", "municipios": d})
    return {"fonte": "IBGE, Censo Demográfico 2022, tabela 9514", "municipios": d}


def capacidade() -> pd.DataFrame | None:
    """Opcional: data/ref/capacidade.csv com cod_ibge;estab_atencao_basica (CNES)."""
    arq = C.DIR_REF / "capacidade.csv"
    if not arq.exists():
        return None
    df = pd.read_csv(arq, sep=";", dtype={"cod_ibge": str})
    return df if {"cod_ibge", "estab_atencao_basica"} <= set(df.columns) else None


def climatologia(cliente, muns, log, pausa=2.0) -> dict:
    arq = C.DIR_REF / "climatologia.json"
    d = _ler_json(arq)
    if not d or d.get("modelo") != F.MODELO_REANALISE:   # refaz se a referência veio de outro modelo
        d = {"periodo": [C.CLIMATOLOGIA_INICIO, C.CLIMATOLOGIA_FIM], "modelo": F.MODELO_REANALISE, "municipios": {}}
    faltam = [m for m in muns if m["cod_ibge"] not in d["municipios"]]
    for i, m in enumerate(faltam):
        log(f"  climatologia ERA5 {C.CLIMATOLOGIA_INICIO[:4]}-{C.CLIMATOLOGIA_FIM[:4]}: {m['nome']}")
        df = F.baixar_reanalise(cliente, [m], C.CLIMATOLOGIA_INICIO, C.CLIMATOLOGIA_FIM, C.FUSO)
        d["municipios"][m["cod_ibge"]] = EHF.climatologia(EHF.temperatura_media(df).set_axis(df["data"]))
        _gravar_json(arq, d)          # grava a cada município: retomável se cair no meio
        if pausa and i < len(faltam) - 1:
            time.sleep(pausa)         # respeita o limite de uso gratuito do Open-Meteo
    return d


# ----------------------------------------------------------------------------
# Série diária (particionada por ano)
# ----------------------------------------------------------------------------
COLS = ["data", "cod_ibge", "tmax", "tmin", "tapmax", "fonte"]


def ler_serie(anos=None) -> pd.DataFrame:
    C.DIR_SERIE.mkdir(parents=True, exist_ok=True)
    arqs = sorted(C.DIR_SERIE.glob("*.csv"))
    if anos is not None:
        arqs = [a for a in arqs if int(a.stem) in set(anos)]
    if not arqs:
        return pd.DataFrame(columns=COLS)
    df = pd.concat([pd.read_csv(a, dtype={"cod_ibge": str}, parse_dates=["data"]) for a in arqs],
                   ignore_index=True)
    return df[COLS]


def gravar_serie(df: pd.DataFrame):
    C.DIR_SERIE.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(["data", "cod_ibge"])
    for ano, g in df.groupby(df["data"].dt.year):
        g.assign(data=g["data"].dt.strftime("%Y-%m-%d")).to_csv(C.DIR_SERIE / f"{ano}.csv", index=False)


def mesclar(atual: pd.DataFrame, novo: pd.DataFrame) -> pd.DataFrame:
    """ERA5 substitui qualquer valor; modelo/previsão só substituem o que não é ERA5."""
    a = (atual if not atual.empty else pd.DataFrame(columns=COLS)).set_index(["data", "cod_ibge"])
    n = novo.set_index(["data", "cod_ibge"])[a.columns]
    era5 = n[n["fonte"] == "era5"]
    era5 = era5[~era5.index.duplicated(keep="last")]
    prov = n[n["fonte"] != "era5"]
    prov = prov[~prov.index.duplicated(keep="last") & ~prov.index.isin(era5.index)]
    trava = a.index[a["fonte"] == "era5"]
    prov = prov[~prov.index.isin(trava)]
    a = a[~a.index.isin(era5.index) & ~a.index.isin(prov.index)]
    return pd.concat([a, era5, prov]).reset_index()[COLS]


def vies_modelo(modelo: pd.DataFrame, era5: pd.DataFrame) -> dict:
    """Diferença média (modelo - ERA5) por município nos dias em que ambos existem."""
    j = modelo.merge(era5, on=["data", "cod_ibge"], suffixes=("_m", "_e"))
    out = {}
    for cod, g in j.groupby("cod_ibge"):
        if len(g) >= 7:
            out[cod] = {"tmax": round(float((g["tmax_m"] - g["tmax_e"]).mean()), 2),
                        "tmin": round(float((g["tmin_m"] - g["tmin_e"]).mean()), 2),
                        "n_dias": int(len(g))}
    return out


# ----------------------------------------------------------------------------
# Indicadores
# ----------------------------------------------------------------------------
def componentes_estruturais(muns, cen, cap) -> dict:
    s60 = {m["cod_ibge"]: cen["municipios"][m["cod_ibge"]]["prop60"] for m in muns}
    s80 = {m["cod_ibge"]: cen["municipios"][m["cod_ibge"]]["prop80"] for m in muns}
    mx60, mx80 = max(s60.values()), max(s80.values())
    out = {c: {"S": round(0.7 * s60[c] / mx60 + 0.3 * s80[c] / mx80, 4), "C": None} for c in s60}
    if cap is not None:
        taxa = {}
        for r in cap.itertuples():
            pop = cen["municipios"].get(str(r.cod_ibge), {}).get("populacao")
            if pop:
                taxa[str(r.cod_ibge)] = 1e4 * r.estab_atencao_basica / pop
        if taxa:
            mx = max(taxa.values())
            for c, t in taxa.items():
                if c in out:
                    out[c]["C"] = round(1 - t / mx, 4)
    return out


def calcular(serie: pd.DataFrame, clim: dict, vies: dict, estr: dict) -> pd.DataFrame:
    w = dict(C.PESOS_IVC)
    usa_cap = all(v["C"] is not None for v in estr.values())
    if not usa_cap:  # sem dados de capacidade: redistribui o peso, e o painel informa
        tot = w["exposicao"] + w["sensibilidade"]
        w = {"exposicao": w["exposicao"] / tot, "sensibilidade": w["sensibilidade"] / tot, "capacidade": 0.0}
    partes = []
    for cod, g in serie.groupby("cod_ibge"):
        g = g.sort_values("data").set_index("data")
        g = g.reindex(pd.date_range(g.index.min(), g.index.max(), freq="D"))
        g["cod_ibge"] = cod
        b = vies.get(cod)
        if b:
            m = g["fonte"].isin(["modelo", "previsao"])
            g.loc[m, "tmax"] -= b["tmax"]
            g.loc[m, "tmin"] -= b["tmin"]
        ref = clim["municipios"][cod]
        t = EHF.temperatura_media(g)
        e = EHF.calcular(t, ref["p95"], ref["ehf85"])
        g = g.join(e)
        frac = ((g["t3"] - ref["p50"]) / (ref["p95"] - ref["p50"])).clip(0, 1)
        expo = np.where(g["ehf"] > 0, 0.5 + 0.5 * np.minimum(g["severidade"] / 3, 1), 0.5 * frac)
        expo = np.where(g["ehf"].isna(), np.nan, expo)
        S, Cc = estr[cod]["S"], (estr[cod]["C"] or 0.0)
        g["E"] = expo
        g["ivc"] = 100 * (w["exposicao"] * g["E"] + w["sensibilidade"] * S + w["capacidade"] * Cc)
        partes.append(g.reset_index().rename(columns={"index": "data"}))
    out = pd.concat(partes, ignore_index=True)
    out.attrs["pesos"] = w
    out.attrs["capacidade_disponivel"] = usa_cap
    return out


# ----------------------------------------------------------------------------
# Exportação para o painel
# ----------------------------------------------------------------------------
def _r(x, n=1):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def exportar(ind: pd.DataFrame, muns, cen, estr, clim, vies, hoje: date, modo: str, avisos: list):
    C.DIR_SITE_DADOS.mkdir(parents=True, exist_ok=True)
    nome = {m["cod_ibge"]: m["nome"] for m in muns}
    if modo != "real":   # na simulação, nomes fictícios: nenhum alerta simulado leva o nome de um município real
        nome = {m["cod_ibge"]: f"Município fictício {chr(65 + i)}" for i, m in enumerate(muns)}
    ind = ind[ind["data"].dt.year >= C.ANO_INICIO_OPERACIONAL].copy()
    cod_fonte = {"era5": "e", "modelo": "m", "previsao": "p"}

    anos = sorted(ind["data"].dt.year.unique().tolist())
    for ano in anos:
        g_ano = ind[ind["data"].dt.year == ano]
        bloco = {}
        for cod, g in g_ano.groupby("cod_ibge"):
            g = g.sort_values("data")
            bloco[cod] = {
                "d": g["data"].dt.strftime("%Y-%m-%d").tolist(),
                "tmax": [_r(v) for v in g["tmax"]], "tmin": [_r(v) for v in g["tmin"]],
                "tapmax": [_r(v) for v in g["tapmax"]], "t3": [_r(v, 2) for v in g["t3"]],
                "ehf": [_r(v, 2) for v in g["ehf"]], "sev": [_r(v, 2) for v in g["severidade"]],
                "ivc": [_r(v, 0) for v in g["ivc"]],
                "fonte": [cod_fonte.get(f, "-") for f in g["fonte"].fillna("-")],
            }
        _gravar_json(C.DIR_SITE_DADOS / f"serie_{ano}.json", {"ano": ano, "municipios": bloco}, compacto=True)

    h0 = pd.Timestamp(hoje)
    janela = ind[(ind["data"] >= h0 - pd.Timedelta(days=7)) & (ind["data"] <= h0 + pd.Timedelta(days=C.DIAS_PREVISAO))]
    linhas = []
    for cod, g in janela.groupby("cod_ibge"):
        g = g.sort_values("data")
        dias = [{"d": r.data.strftime("%Y-%m-%d"), "ivc": _r(r.ivc, 0), "faixa": faixa(r.ivc),
                 "sev": _r(r.severidade, 2), "classe": EHF.classe(r.severidade),
                 "tmax": _r(r.tmax), "tmin": _r(r.tmin), "tapmax": _r(r.tapmax),
                 "fonte": r.fonte if isinstance(r.fonte, str) else None} for r in g.itertuples()]
        prox = [x for x in dias if h0 <= pd.Timestamp(x["d"]) <= h0 + pd.Timedelta(days=C.HORIZONTE_ALERTA)
                and x["ivc"] is not None]
        pico = max(prox, key=lambda x: x["ivc"]) if prox else None
        c = cen["municipios"][cod]
        linhas.append({
            "cod_ibge": cod, "nome": nome[cod], "populacao": c["populacao"], "pop60": c["pop60"],
            "prop60": c["prop60"], "prop80": c["prop80"], "S": estr[cod]["S"], "C": estr[cod]["C"],
            "ivc_max_horizonte": pico["ivc"] if pico else None, "dia_pico": pico["d"] if pico else None,
            "faixa_pico": pico["faixa"] if pico else None,
            "alerta": bool(pico and pico["ivc"] >= C.LIMIAR_ACAO),
            "conduta": CONDUTAS.get(pico["faixa"]) if pico else None,
            "climatologia": clim["municipios"][cod], "dias": dias,
        })
    linhas.sort(key=lambda x: -(x["ivc_max_horizonte"] or -1))
    _gravar_json(C.DIR_SITE_DADOS / "atual.json",
                 {"data_referencia": hoje.isoformat(), "limiar": C.LIMIAR_ACAO,
                  "horizonte_alerta": C.HORIZONTE_ALERTA, "municipios": linhas}, compacto=True)

    era5 = ind.loc[ind["fonte"] == "era5", "data"]
    _gravar_json(C.DIR_SITE_DADOS / "meta.json", {
        "versao": __version__, "modo": modo,
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_referencia": hoje.isoformat(), "anos": anos,
        "ultima_data_era5": era5.max().strftime("%Y-%m-%d") if not era5.empty else None,
        "ultima_data_previsao": ind["data"].max().strftime("%Y-%m-%d"),
        "climatologia": {"periodo": clim["periodo"], "fonte": "ERA5 (Copernicus/ECMWF) via Open-Meteo"},
        "pesos": ind.attrs.get("pesos"), "capacidade_disponivel": ind.attrs.get("capacidade_disponivel"),
        "limiar": C.LIMIAR_ACAO, "vies_modelo": vies, "avisos": avisos,
        "fontes": [
            {"nome": "Open-Meteo (previsão e reanálise ERA5)", "url": "https://open-meteo.com",
             "licenca": "CC BY 4.0", "uso": "temperatura máxima, mínima e aparente; climatologia 2014-2025"},
            {"nome": "IBGE, Censo Demográfico 2022 (tabela 9514)", "url": "https://sidra.ibge.gov.br/tabela/9514",
             "uso": "população total, 60+ e 80+ por município"},
            {"nome": "IBGE, API de localidades", "url": "https://servicodados.ibge.gov.br/api/docs/localidades",
             "uso": "códigos dos municípios"},
        ],
        "metodo": {"exposicao": "Fator de Excesso de Calor (Nairn e Fawcett, 2015)",
                   "sensibilidade": "0,7 x proporção 60+ + 0,3 x proporção 80+, relativas ao máximo da RM",
                   "capacidade": "estabelecimentos de atenção básica por 10 mil habitantes (CNES), quando disponível"},
    })
    return anos


# ----------------------------------------------------------------------------
# Orquestração
# ----------------------------------------------------------------------------
def executar(cliente=None, hoje: date | None = None, modo: str = "real", verbose=True, pausa=2.0) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    cliente = cliente or F.ClienteHTTP()
    hoje = hoje or datetime.now(timezone(timedelta(hours=-3))).date()
    avisos = []
    log(f"[ClimaSênior {__version__}] referência {hoje} | modo {modo}")

    log("[1/6] Território e população")
    muns = municipios(cliente, log)
    for m in muns:
        if m.get("distancia_km", 0) > 15:
            avisos.append(f"Coordenada de {m['nome']} difere {m['distancia_km']} km da geocodificação")
    cen = censo(cliente, muns, log)
    cap = capacidade()
    if cap is None:
        avisos.append("Capacidade de resposta ainda não carregada (CNES): o IVC usa exposição e sensibilidade")

    log("[2/6] Climatologia de referência")
    clim = climatologia(cliente, muns, log, pausa=pausa)

    log("[3/6] Reanálise ERA5 (dias consolidados)")
    serie = ler_serie()
    inicio_min = date(C.ANO_INICIO_OPERACIONAL, 1, 1) - timedelta(days=31)   # aquecimento da aclimatação
    era5_ok = serie.loc[serie["fonte"] == "era5", "data"]
    inicio = max(inicio_min, (era5_ok.max().date() + timedelta(days=1)) if not era5_ok.empty else inicio_min)
    fim_era5 = hoje - timedelta(days=C.DEFASAGEM_ERA5)
    novos = []
    d0 = inicio
    while d0 <= fim_era5:                      # um pedido por ano, no máximo
        d1 = min(date(d0.year, 12, 31), fim_era5)
        log(f"  ERA5 {d0} a {d1}")
        df = F.baixar_reanalise(cliente, muns, d0.isoformat(), d1.isoformat(), C.FUSO)
        novos.append(df.dropna(subset=["tmax", "tmin"]).assign(fonte="era5"))
        d0 = d1 + timedelta(days=1)

    log("[4/6] Modelo: janela recente e previsão de 16 dias")
    prev = F.baixar_previsao(cliente, muns, C.DIAS_PASSADOS_MODELO, C.DIAS_PREVISAO, C.FUSO)
    prev = prev.dropna(subset=["tmax", "tmin"])
    prev["fonte"] = np.where(prev["data"] < pd.Timestamp(hoje), "modelo", "previsao")

    for df in novos + [prev]:
        df.rename(columns={"chave": "cod_ibge"}, inplace=True)
    serie = mesclar(serie, pd.concat(novos + [prev], ignore_index=True)) if novos else mesclar(serie, prev)
    gravar_serie(serie)

    era5_tudo = serie[serie["fonte"] == "era5"]
    vies = vies_modelo(prev, era5_tudo)
    if not vies:
        avisos.append("Sem sobreposição suficiente para corrigir o viés do modelo nesta execução")
    _gravar_json(C.DIR_REF / "vies_modelo.json", {"data": hoje.isoformat(), "vies": vies})

    log("[5/6] EHF e IVC")
    estr = componentes_estruturais(muns, cen, cap)
    ind = calcular(serie, clim, vies, estr)

    log("[6/6] Exportação do painel")
    anos = exportar(ind, muns, cen, estr, clim, vies, hoje, modo, avisos)
    alertas = [m["nome"] for m in json.loads((C.DIR_SITE_DADOS / "atual.json").read_text(encoding="utf-8"))["municipios"] if m["alerta"]]
    log(f"  anos no painel: {anos} | municípios em alerta (D+0 a D+{C.HORIZONTE_ALERTA}): {alertas or 'nenhum'}")
    for a in avisos:
        log(f"  aviso: {a}")
    return {"anos": anos, "alertas": alertas, "avisos": avisos}


def main():
    ap = argparse.ArgumentParser(description="Atualiza os dados e o painel do ClimaSênior")
    ap.add_argument("--simular", action="store_true", help="usa dados simulados (sem rede)")
    ap.add_argument("--data", help="data de referência AAAA-MM-DD (padrão: hoje em São Luís)")
    ap.add_argument("--saida", help="pasta alternativa para dados e painel (padrão: data/ e site/data/)")
    a = ap.parse_args()
    hoje = date.fromisoformat(a.data) if a.data else None
    if a.simular and not a.saida:
        a.saida = str(C.RAIZ / "simulacao")          # nunca mistura simulação com dados reais
    if a.saida:
        redirecionar(Path(a.saida))
    if a.simular:
        from .simulacao import ClienteSimulado
        executar(ClienteSimulado(hoje), hoje=hoje, modo="simulacao", pausa=0)
    else:
        executar(hoje=hoje)


def redirecionar(base: Path):
    """Aponta dados e saída do painel para outra pasta (simulação e testes)."""
    C.DIR_REF, C.DIR_SERIE, C.DIR_SITE_DADOS = base / "data/ref", base / "data/serie", base / "site/data"


if __name__ == "__main__":
    main()
