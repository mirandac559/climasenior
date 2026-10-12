# -*- coding: utf-8 -*-
"""
Validação retrospectiva do IVC (Fase 3): o índice de 2014 a 2025, recalculado para os
5.571 municípios exatamente como na operação diária, comparado com as internações de
pessoas com 60 anos ou mais no SIH/DataSUS.

Desenho: série temporal estratificada no tempo (equivalente ao caso-cruzado
estratificado no tempo; Janes et al., 2005). Cada dia de um município é comparado só
com dias do mesmo município, ano, mês e dia da semana, o que controla sazonalidade,
tendência, tamanho e perfil da população e qualquer característica fixa do lugar.

Exposição principal: o dia d está "em alerta" quando o IVC do próprio dia ou de um dos
dois dias anteriores atingiu o limiar (o IVC do dia t mede a onda de calor de t a t+2,
de modo que um alerta emitido para t cobre os três dias). A faixa do dia é a maior das
três. Análises de sensibilidade: defasagem a defasagem (IVC de d-L, L = 0 a 7) e
limiares de 40 a 80.

Medidas:
  - razão de taxas de Mantel-Haenszel (internações por dia, dias em alerta x demais dias
    do mesmo estrato), com intervalo de 95% por bootstrap de municípios (500 réplicas),
    que respeita a autocorrelação dos dias de um mesmo lugar;
  - internações a mais nos dias de alerta: observadas menos esperadas, com a taxa
    esperada tirada dos dias sem alerta do mesmo estrato.

Uso (GitHub Actions; o DataSUS e a NOAA não são acessíveis em todo ambiente):
    python -m climasenior.validacao sih --ano 2024 --saida sih          # um ano de competência
    python -m climasenior.validacao analisar --sih sih                  # exposição + análise
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import brasil as B
from . import config as C
from . import cpc as CPC
from . import fontes as F
from . import sih as SIH
from . import __version__

INICIO, FIM = date(2014, 1, 1), date(2025, 12, 31)
ANOS_EXPOSICAO = list(range(2013, 2026))          # 2013: aquecimento da aclimatação (30 dias)
JANELA = 3
LIMIAR = C.LIMIAR_ACAO
LIMIARES = [40, 50, 60, 70, 80]
DEFASAGENS = list(range(0, 8))
FAIXAS = [("BAIXA", 0, 40), ("MODERADA", 40, 60), ("ALTA", 60, 80), ("MUITO ALTA", 80, 1000)]
N_BOOT = 500
REGIOES = {"Norte": ["RO", "AC", "AM", "RR", "PA", "AP", "TO"],
           "Nordeste": ["MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA"],
           "Sudeste": ["MG", "ES", "RJ", "SP"], "Sul": ["PR", "SC", "RS"], "Centro-Oeste": ["MS", "MT", "GO", "DF"]}


# =============================================================================
# 1. Exposição histórica (CPC observada, 2013-2025)
# =============================================================================
def exposicao_historica(cliente, P: B.Pastas, cel: pd.DataFrame, cache: Path | None = None, anos=None, log=print):
    """Devolve (datas, células, E[dia, célula]) com o componente de exposição diário."""
    anos = list(anos or ANOS_EXPOSICAO)
    if cache and Path(cache).exists():
        z = np.load(cache, allow_pickle=False)
        cels = [str(c) for c in z["celulas"]]
        if cels == list(cel["celula"]) and int(z["ano0"]) <= anos[0] and int(z["ano1"]) >= anos[-1]:
            log(f"  exposição em cache ({cache})")
            return pd.to_datetime(z["datas"].astype("datetime64[D]")), cels, z["E"].astype(np.float32)
    ids = list(cel["celula"])
    datas, tx, tn = [], [], []
    for ano in anos:
        t0 = time.time()
        d1, lats, lons, a1 = CPC.baixar_e_ler(cliente, ano, "tmax", log)
        d2, _, _, a2 = CPC.baixar_e_ler(cliente, ano, "tmin", log)
        if d1 != d2:
            raise F.ErroFonte(f"CPC {ano}: datas de tmax e tmin não coincidem")
        pos_lat = {f"{la:.2f}": i for i, la in enumerate(lats)}
        pos_lon = {f"{lo:.2f}": j for j, lo in enumerate(lons)}
        ii = np.array([pos_lat[c.split("_")[0]] for c in ids])
        jj = np.array([pos_lon[c.split("_")[1]] for c in ids])
        datas += list(d1)
        tx.append(a1[:, ii, jj])
        tn.append(a2[:, ii, jj])
        log(f"    {ano}: {len(d1)} dias ({time.time() - t0:.0f} s)")
    t = pd.DataFrame((np.concatenate(tx) + np.concatenate(tn)) / 2, index=pd.to_datetime(datas), columns=ids)
    # dois primeiros dias do ano seguinte (fecham a janela de 3 dias de 30 e 31/12), se já gravados
    seguinte = B.ler_dias(P, date(anos[-1] + 1, 1, 1), date(anos[-1] + 1, 1, 2))
    if not seguinte.empty:
        extra = seguinte.assign(t=(seguinte["tmax"] + seguinte["tmin"]) / 2).pivot_table(
            index="data", columns="celula", values="t").reindex(columns=ids)
        t = pd.concat([t, extra])
    t = t[~t.index.duplicated()].sort_index().interpolate(limit=3, limit_area="inside")
    E = B.exposicao(t, cel.set_index("celula").reindex(ids))["E"].to_numpy(dtype=np.float32)
    if cache:
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, datas=t.index.values.astype("datetime64[D]"), celulas=np.array(ids),
                            E=E.astype(np.float16), ano0=anos[0], ano1=anos[-1])
    return t.index, ids, E


# =============================================================================
# 2. Internações
# =============================================================================
def ler_internacoes(pasta: Path) -> tuple[pd.DataFrame, dict]:
    partes, manifestos = [], []
    for arq in sorted(Path(pasta).rglob("sih_*.parquet")):
        partes.append(pd.read_parquet(arq))
    for arq in sorted(Path(pasta).rglob("manifesto_*.json")):
        manifestos.append(json.loads(arq.read_text(encoding="utf-8")))
    if not partes:
        raise SIH.ErroSIH(f"nenhum arquivo do SIH em {pasta}")
    df = pd.concat(partes, ignore_index=True).groupby(["mun6", "data"], as_index=False)[SIH.GRUPOS].sum()
    resumo = {"anos_competencia": sorted(m["ano_competencia"] for m in manifestos),
              "arquivos_lidos": int(sum(len(m["arquivos"]) for m in manifestos)),
              "arquivos_com_falha": int(sum(len(m["falhas"]) for m in manifestos)),
              "falhas": {k: v for m in manifestos for k, v in m["falhas"].items()},
              "aih_lidas": int(sum(m.get("registros", 0) for m in manifestos))}
    return df, resumo


# =============================================================================
# 3. Estimação
# =============================================================================
class Estratos:
    """Soma, dentro de cada estrato (ano x mês x dia da semana), colunas de uma matriz dia x município."""

    def __init__(self, dias: pd.DatetimeIndex):
        s = (dias.year - dias.year.min()) * 84 + (dias.month - 1) * 7 + dias.weekday
        self.ordem = np.argsort(s.to_numpy(), kind="stable")
        ss = s.to_numpy()[self.ordem]
        self.inicios = np.r_[0, np.flatnonzero(np.diff(ss)) + 1]

    def soma(self, A: np.ndarray) -> np.ndarray:
        return np.add.reduceat(A[self.ordem], self.inicios, axis=0).astype(np.float64)


def por_municipio(est: Estratos, Y: np.ndarray, expo: np.ndarray, ref: np.ndarray) -> dict:
    """Termos de Mantel-Haenszel e de excesso somados por município."""
    a = est.soma(np.where(expo, Y, 0))
    b = est.soma(np.where(ref, Y, 0))
    t1, t0 = est.soma(expo.astype(np.int32)), est.soma(ref.astype(np.int32))
    T = t1 + t0
    with np.errstate(invalid="ignore", divide="ignore"):
        num = np.where(T > 0, a * t0 / T, 0).sum(0)
        den = np.where(T > 0, b * t1 / T, 0).sum(0)
        ambos = (t1 > 0) & (t0 > 0)
        O = np.where(ambos, a, 0).sum(0)
        Ee = np.where(ambos, t1 * b / np.where(t0 > 0, t0, 1), 0).sum(0)
    return {"num": num, "den": den, "O": O, "E": Ee, "a_total": a.sum(0), "t1": t1.sum(0), "T": T.sum(0)}


def resumir(pm: dict, idx: np.ndarray, boot: np.ndarray, anos: float) -> dict:
    num, den = pm["num"][idx], pm["den"][idx]
    sd = den.sum()
    if sd <= 0:
        return {"rr": None, "lo": None, "hi": None}
    rr = num.sum() / sd
    bn, bd = num[boot].sum(1), den[boot].sum(1)
    ok = bd > 0
    lo, hi = (np.percentile(bn[ok] / bd[ok], [2.5, 97.5]) if ok.sum() > 20 else (np.nan, np.nan))
    O, E = pm["O"][idx].sum(), pm["E"][idx].sum()
    T = pm["T"][idx].sum()
    return {"rr": B._r(rr, 3), "lo": B._r(lo, 3), "hi": B._r(hi, 3),
            "observadas": int(round(O)), "esperadas": B._r(E, 1),
            "excesso": B._r(O - E, 0), "excesso_ano": B._r((O - E) / anos, 0),
            "pct": B._r((O / E - 1) * 100, 1) if E > 0 else None,
            "dias_pct": B._r(pm["t1"][idx].sum() / T * 100, 2) if T > 0 else None,
            "internacoes_em_alerta": int(round(pm["a_total"][idx].sum()))}


def analisar(E_cel: np.ndarray, datas: pd.DatetimeIndex, cels: list[str], m: pd.DataFrame, P: B.Pastas,
             sih: pd.DataFrame, resumo_sih: dict, inicio: date = INICIO, fim: date = FIM, ufs=None,
             n_boot: int = N_BOOT, log=print) -> tuple[dict, dict]:
    t0 = time.time()
    rng = np.random.default_rng(20261012)
    m = m.reset_index(drop=True)
    cel_idx = pd.Index(cels).get_indexer(m["celula"].astype(str))
    w, _ = B.pesos_ivc(m, P)
    S = B.sensibilidade(m).astype(np.float32)
    # IVC diário por município (mesma fórmula, pesos e arredondamento do painel)
    Em = E_cel[:, np.where(cel_idx >= 0, cel_idx, 0)].astype(np.float32)
    Em[:, cel_idx < 0] = np.nan
    ivc = np.round(100 * (w["exposicao"] * Em + w["sensibilidade"] * S[None, :]))
    del Em
    dias_todos = pd.DatetimeIndex(datas)
    k0, k1 = dias_todos.get_loc(pd.Timestamp(inicio)), dias_todos.get_loc(pd.Timestamp(fim))
    dias = dias_todos[k0:k1 + 1]
    nd, nm = len(dias), len(m)
    anos = nd / 365.25

    def defasado(L):
        return ivc[k0 - L:k1 + 1 - L]

    X = defasado(0).copy()
    for L in range(1, JANELA):
        X = np.fmax(X, defasado(L))
    valido = np.isfinite(X)
    log(f"  IVC: {nd} dias x {nm} municípios; {valido.mean() * 100:.1f}% com dado ({time.time() - t0:.0f} s)")

    # internações: matriz dia x município por grupo
    cod6 = m["cod_ibge"].astype(str).str[:6].astype(np.int64)
    col = pd.Series(np.arange(nm), index=cod6.to_numpy())
    col = col[~col.index.duplicated()]
    d = pd.to_datetime(sih["data"].astype(str), format="%Y%m%d", errors="coerce")
    ri = dias.get_indexer(d)
    ci = col.reindex(sih["mun6"].to_numpy()).to_numpy()
    no_periodo = ri >= 0
    casou = no_periodo & ~np.isnan(ci)
    fora_mun = {g: int(sih.loc[no_periodo & np.isnan(ci), g].sum()) for g in SIH.GRUPOS}
    Y = {}
    for g in SIH.GRUPOS:
        A = np.zeros((nd, nm), dtype=np.int32)
        A[ri[casou], ci[casou].astype(int)] = sih.loc[casou, g].to_numpy()
        Y[g] = A
    sel = np.ones(nm, dtype=bool) if not ufs else m["uf"].isin(ufs).to_numpy()
    log(f"  internações 60+ (urgência) no período: " +
        ", ".join(f"{g} {int(Y[g][:, sel].sum()):,}".replace(",", ".") for g in SIH.GRUPOS) +
        f" | sem município correspondente: {fora_mun['todas']:,}".replace(",", "."))

    est = Estratos(dias)
    comparacoes = {"alerta": (valido & (X >= LIMIAR), valido & (X < LIMIAR))}
    for nome, lo, hi in FAIXAS[1:]:
        comparacoes[f"faixa:{nome}"] = (valido & (X >= lo) & (X < hi), valido & (X < FAIXAS[0][2]))
    for L in DEFASAGENS:
        Z = defasado(L)
        comparacoes[f"lag:{L}"] = (np.isfinite(Z) & (Z >= LIMIAR), np.isfinite(Z) & (Z < LIMIAR))
    for k in LIMIARES:
        if k != LIMIAR:
            comparacoes[f"lim:{k}"] = (valido & (X >= k), valido & (X < k))

    pm = {g: {} for g in SIH.GRUPOS}
    for c, (ex, rf) in comparacoes.items():
        for g in SIH.GRUPOS:
            pm[g][c] = por_municipio(est, Y[g], ex, rf)
    dias_faixa = {nome: ((X >= lo) & (X < hi) & valido).sum(0) for nome, lo, hi in FAIXAS}
    log(f"  estimativas por município prontas ({time.time() - t0:.0f} s)")

    # áreas: Brasil, UFs e regiões
    areas = {"BR": np.flatnonzero(sel)}
    for uf in sorted(m["uf"].unique()):
        ix = np.flatnonzero(sel & (m["uf"] == uf).to_numpy())
        if len(ix):
            areas[uf] = ix
    regioes = {r: np.flatnonzero(sel & m["uf"].isin(u).to_numpy()) for r, u in REGIOES.items()}
    regioes = {r: ix for r, ix in regioes.items() if len(ix)}

    def bloco(ix):
        boot = rng.integers(0, len(ix), (n_boot, len(ix)))        # posições dentro da área
        validos_area = valido[:, ix].sum()
        out = {"n_municipios": int(len(ix)), "pop60": int(np.nansum(m.loc[ix, "pop60"])), "grupos": {}}
        for g in SIH.GRUPOS:
            r = {"total": int(Y[g][:, ix][valido[:, ix]].sum())}
            r["alerta"] = resumir(pm[g]["alerta"], ix, boot, anos)
            r["faixas"] = [{"faixa": "BAIXA", "rr": 1.0, "lo": None, "hi": None,
                            "dias_pct": B._r(dias_faixa["BAIXA"][ix].sum() / validos_area * 100, 2)}]
            for nome, _, _ in FAIXAS[1:]:
                s = resumir(pm[g][f"faixa:{nome}"], ix, boot, anos)
                r["faixas"].append({"faixa": nome, "rr": s["rr"], "lo": s["lo"], "hi": s["hi"],
                                    "dias_pct": B._r(dias_faixa[nome][ix].sum() / validos_area * 100, 2),
                                    "excesso_ano": s.get("excesso_ano")})
            r["defasagens"] = []
            for L in DEFASAGENS:
                s = resumir(pm[g][f"lag:{L}"], ix, boot, anos)
                r["defasagens"].append({"l": L, "rr": s["rr"], "lo": s["lo"], "hi": s["hi"]})
            r["limiares"] = []
            for k in LIMIARES:
                s = r["alerta"] if k == LIMIAR else resumir(pm[g][f"lim:{k}"], ix, boot, anos)
                r["limiares"].append({"k": k, **{c: s.get(c) for c in ("rr", "lo", "hi", "dias_pct", "excesso_ano", "pct",
                                                                         "internacoes_em_alerta")}})
            out["grupos"][g] = r
        return out

    res_areas = {a: bloco(ix) for a, ix in areas.items()}
    res_regioes = {r: bloco(ix) for r, ix in regioes.items()}
    log(f"  áreas e bootstrap prontos ({time.time() - t0:.0f} s)")

    # séries diárias por área (internações sensíveis ao calor e de todas as causas; % de 60+ em alerta)
    pop60 = pd.to_numeric(m["pop60"], errors="coerce").fillna(0).to_numpy(dtype=np.float64)
    em_alerta = (valido & (X >= LIMIAR)).astype(np.float32)
    series = {}
    for a, ix in areas.items():
        pv = (valido[:, ix] * pop60[ix]).sum(1)
        pa = (em_alerta[:, ix] * pop60[ix]).sum(1)
        series[a] = {"d0": inicio.isoformat(),
                     "calor": Y["calor"][:, ix].sum(1).astype(int).tolist(),
                     "todas": Y["todas"][:, ix].sum(1).astype(int).tolist(),
                     "alerta_pop": np.round(np.where(pv > 0, pa / np.where(pv > 0, pv, 1) * 100, 0), 1).tolist()}

    resultado = {
        "versao": __version__, "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "periodo": [inicio.isoformat(), fim.isoformat()], "piloto": bool(ufs),
        "ufs": sorted(ufs) if ufs else None, "limiar": LIMIAR, "janela_alerta": JANELA,
        "pesos": w, "n_boot": n_boot,
        "grupos": {g: {"nome": SIH.NOMES_GRUPOS[g], "cid": SIH.CIDS_GRUPOS[g]} for g in SIH.GRUPOS},
        "faixas": [[n, lo, min(hi, 100)] for n, lo, hi in FAIXAS],
        "sih": {**resumo_sih, "sem_municipio": fora_mun},
        "areas": res_areas, "regioes": res_regioes,
        "metodo": {
            "desenho": "série temporal estratificada no tempo: cada dia é comparado com dias do mesmo município, ano, "
                       "mês e dia da semana",
            "exposicao": f"dia em alerta: IVC do dia ou de um dos {JANELA - 1} dias anteriores >= {LIMIAR}",
            "desfecho": "internações de urgência de pessoas com 60 anos ou mais (AIH tipo 1), por município de "
                        "residência e data de internação",
            "medida": "razão de taxas de Mantel-Haenszel; IC 95% por bootstrap de municípios; excesso = observadas - "
                      "esperadas pela taxa dos dias sem alerta do mesmo estrato",
            "referencias": ["Nairn J, Fawcett R. Int J Environ Res Public Health 2015;12:227-253",
                            "Bobb JF et al. JAMA 2014;312(24):2659-2667",
                            "Janes H, Sheppard L, Lumley T. Epidemiology 2005;16(6):717-726"],
        },
    }
    log(f"  concluído em {time.time() - t0:.0f} s")
    return resultado, series


def gravar(resultado: dict, series: dict, P: B.Pastas):
    P.validacao.mkdir(parents=True, exist_ok=True)
    B._gravar_json(P.validacao / "resultados.json", resultado)
    for a, s in series.items():
        B._gravar_json(P.validacao / "serie" / f"{a}.json", s)


def texto_resumo(res: dict) -> str:
    br = res["areas"].get("BR", {}).get("grupos", {})
    linhas = []
    for g, r in br.items():
        a = r["alerta"]
        linhas.append(f"{res['grupos'][g]['nome']}: {r['total']:,} internações; dias em alerta {a.get('dias_pct')}%; "
                      f"RR {a.get('rr')} ({a.get('lo')}-{a.get('hi')}); excesso/ano {a.get('excesso_ano')}".replace(",", "."))
        linhas.append("   faixas: " + "; ".join(f"{f['faixa']} {f['rr']} ({f['lo']}-{f['hi']})" for f in r["faixas"]))
        linhas.append("   defasagens: " + "; ".join(f"L{f['l']} {f['rr']}" for f in r["defasagens"]))
    return "\n".join(linhas)


# =============================================================================
# CLI
# =============================================================================
def main():
    ap = argparse.ArgumentParser(description="Validação retrospectiva do IVC com o SIH/DataSUS")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("sih", help="baixa e agrega um ano de competência do SIH")
    a1.add_argument("--ano", type=int, required=True)
    a1.add_argument("--ufs")
    a1.add_argument("--meses")
    a1.add_argument("--saida", default="sih")
    a2 = sub.add_parser("analisar", help="recalcula o IVC 2014-2025 e compara com as internações")
    a2.add_argument("--sih", default="sih")
    a2.add_argument("--cache", default="cache_validacao/exposicao.npz")
    a2.add_argument("--ufs")
    a2.add_argument("--anos", help="ex.: 2024 ou 2023-2024 (piloto)")
    a2.add_argument("--nao-gravar", action="store_true")
    a2.add_argument("--saida", help="pasta dos resultados (padrão: data/validacao; no piloto, data/validacao_piloto)")
    a2.add_argument("--n-boot", type=int, default=N_BOOT)
    a = ap.parse_args()
    if a.cmd == "sih":
        man = SIH.coletar(a.ano, Path(a.saida), ufs=a.ufs.split(",") if a.ufs else None,
                          meses=[int(x) for x in a.meses.split(",")] if a.meses else None)
        aviso_actions(f"SIH {a.ano}", f"{len(man['arquivos'])} arquivos lidos, {len(man['falhas'])} com falha; "
                      f"{man['registros']} AIH; {man['internacoes_60_urgencia']} internações de 60+ em urgência\n"
                      + "\n".join(f"falha {k}: {v}" for k, v in list(man["falhas"].items())[:20]))
        return
    P = B.Pastas(C.DIR_DADOS, C.DIR_SITE_DADOS)
    m = pd.read_csv(P.ref / "municipios_br.csv", dtype={"cod_ibge": str, "celula": str})
    cel = pd.read_csv(P.ref / "celulas.csv", dtype={"celula": str})
    inicio, fim = INICIO, FIM
    anos_exp = ANOS_EXPOSICAO
    if a.anos:
        y0, y1 = (int(x) for x in (a.anos.split("-") if "-" in a.anos else (a.anos, a.anos)))
        inicio, fim = date(y0, 1, 1), date(y1, 12, 31)
    print("[1/3] Exposição diária (CPC)", flush=True)
    datas, cels, E = exposicao_historica(F.ClienteHTTP(), P, cel, cache=Path(a.cache), anos=anos_exp,
                                         log=lambda *x: print(*x, flush=True))
    print("[2/3] Internações (SIH)", flush=True)
    sih, resumo = ler_internacoes(Path(a.sih))
    print(f"  {len(sih):,} combinações município-dia; {resumo['arquivos_lidos']} arquivos, "
          f"{resumo['arquivos_com_falha']} com falha".replace(",", "."), flush=True)
    print("[3/3] Análise", flush=True)
    res, series = analisar(E, datas, cels, m, P, sih, resumo, inicio, fim,
                           ufs=a.ufs.split(",") if a.ufs else None, n_boot=a.n_boot,
                           log=lambda *x: print(*x, flush=True))
    resumo_txt = texto_resumo(res)
    print(resumo_txt, flush=True)
    aviso_actions(f"Validação {'piloto ' + a.ufs + ' ' + (a.anos or '') if a.ufs else 'Brasil'}", resumo_txt)
    if not a.nao_gravar:
        if a.saida or a.ufs:
            P.validacao = Path(a.saida) if a.saida else C.DIR_DADOS / "validacao_piloto"
        gravar(res, series, P)
        (P.validacao / "resumo.txt").write_text(resumo_txt + "\n", encoding="utf-8")
        print(f"gravado em {P.validacao}", flush=True)


def aviso_actions(titulo: str, texto: str):
    """No GitHub Actions, publica o resumo como anotação (legível pela API, sem baixar o registro)."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    blocos, atual = [], ""
    for linha in texto.splitlines():
        if len(atual) + len(linha) > 3500:
            blocos.append(atual); atual = ""
        atual += linha + "\n"
    blocos.append(atual)
    for k, b in enumerate(blocos[:9]):
        print(f"::notice title={titulo} ({k + 1})::" + b.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A"),
              flush=True)


if __name__ == "__main__":
    sys.exit(main())
