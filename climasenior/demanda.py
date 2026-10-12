# -*- coding: utf-8 -*-
"""
Modelo de demanda assistencial (aprendizado de máquina): internações de urgência de
pessoas com 60 anos ou mais esperadas para cada município e dia, dadas a exposição ao
calor do IVC e a demanda habitual do lugar.

Algoritmo: gradient boosting de árvores de decisão com perda de Poisson
(HistGradientBoostingRegressor, scikit-learn), adequado a contagens e a dezenas de milhões
de registros. Dois desfechos: todas as causas clínicas (demanda assistencial) e causas
sensíveis ao calor. O modelo aprende a razão entre as internações do dia e a demanda
habitual do município (exposição da regressão de Poisson): previsto = razão x demanda habitual.
Assim cidades grandes e pequenas ficam na mesma escala e o ajuste é estável.

Variáveis (todas disponíveis no dia da previsão):
  base    demanda habitual: média diária do município nos 365 dias que terminam 180 dias
          antes (o SIH chega com meses de atraso; na operação usa-se o último ano completo)
  E0..E2  componente de exposição do IVC no dia e nos dois anteriores
  X3      maior IVC entre o dia e os dois anteriores (o mesmo critério de alerta do painel)
  mes, dsem, sazonalidade (seno e cosseno do dia do ano)
  S, C    sensibilidade e capacidade de resposta do IVC; log da população 60+; UF

Validação temporal do projeto: treino até 2022, validação em 2023-2024, teste em 2025.
O período de validação também recalibra o nível: a razão observado/previsto em 2023-2024
(as internações crescem com o envelhecimento) multiplica as previsões seguintes.
O mesmo modelo sem as variáveis de calor serve de comparação: a diferença mostra quanto
a informação climática melhora a estimativa.
"""
from __future__ import annotations
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from . import config as C

GRUPOS_MODELO = ["todas", "calor"]
NOMES = {"todas": "Todas as causas clínicas", "calor": "Sensíveis ao calor"}
JANELA_BASE, DEFASAGEM_BASE = 365, 180
TREINO_ATE, VALID = date(2022, 12, 31), (date(2023, 1, 1), date(2024, 12, 31))
TESTE = (date(2025, 1, 1), date(2025, 12, 31))
CLIMA = ["E0", "E1", "E2", "X3"]
VARIAVEIS = ["base", "mes", "dsem", "doy_s", "doy_c", "S", "C", "lpop60", "uf"] + CLIMA
FRACAO_TREINO = 0.35
BASE_MINIMA = 0.02             # demanda habitual mínima (internações/dia) usada como exposição
DIR_MODELOS = C.RAIZ / "modelos"
UF_ORDEM = sorted(["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE",
                   "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"])


def _calendario(dias: pd.DatetimeIndex) -> dict:
    doy = dias.dayofyear.to_numpy()
    return {"mes": dias.month.to_numpy().astype(np.float32), "dsem": dias.weekday.to_numpy().astype(np.float32),
            "doy_s": np.sin(2 * np.pi * doy / 365.25).astype(np.float32),
            "doy_c": np.cos(2 * np.pi * doy / 365.25).astype(np.float32)}


def _municipais(m: pd.DataFrame, S, Cc) -> dict:
    pop60 = pd.to_numeric(m["pop60"], errors="coerce").fillna(0).to_numpy()
    return {"S": np.asarray(S, np.float32), "C": np.asarray(Cc, np.float32),
            "lpop60": np.log1p(pop60).astype(np.float32),
            "uf": m["uf"].map({u: k for k, u in enumerate(UF_ORDEM)}).fillna(-1).to_numpy().astype(np.float32)}


def matriz(ii: np.ndarray, jj: np.ndarray, base: np.ndarray, Em: np.ndarray, X: np.ndarray, cal: dict, mun: dict,
           k_em: int) -> np.ndarray:
    """Linhas (dia ii, município jj). Em é indexado com deslocamento k_em (dias anteriores ao período)."""
    col = {"base": np.log(base[ii, jj] + 0.01),
           "E0": Em[k_em + ii, jj], "E1": Em[k_em + ii - 1, jj], "E2": Em[k_em + ii - 2, jj], "X3": X[ii, jj]}
    for k, v in cal.items():
        col[k] = v[ii]
    for k, v in mun.items():
        col[k] = v[jj]
    return np.column_stack([col[v].astype(np.float32) for v in VARIAVEIS])


def _modelo():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(loss="poisson", learning_rate=0.06, max_iter=800, max_leaf_nodes=48,
                                         min_samples_leaf=500, l2_regularization=1.0, early_stopping=True,
                                         validation_fraction=0.1, n_iter_no_change=30, random_state=0)


def _metricas(y, p, dia, uf, X3, calib=True) -> dict:
    from sklearn.metrics import f1_score, precision_score, recall_score, accuracy_score
    y, p = y.astype(np.float64), np.clip(p.astype(np.float64), 1e-9, None)
    dev = 2 * np.mean(np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / p), 0) - (y - p))
    ym = y.mean()
    dev0 = 2 * np.mean(np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / ym), 0) - (y - ym))
    out = {"mae": float(np.mean(np.abs(y - p))), "rmse": float(np.sqrt(np.mean((y - p) ** 2))),
           "desvio_poisson": float(dev), "d2": float(1 - dev / dev0), "razao_total": float(y.sum() / p.sum())}
    # agregado por UF e dia: a escala em que se planeja a resposta
    nuf = int(uf.max()) + 1
    chave = dia * nuf + uf
    yo, po = np.bincount(chave, y), np.bincount(chave, p)
    ok = np.bincount(chave) > 0
    yo, po = yo[ok], po[ok]
    u = (np.flatnonzero(ok) % nuf)
    out["uf_dia"] = {"mae": float(np.mean(np.abs(yo - po))), "rmse": float(np.sqrt(np.mean((yo - po) ** 2))),
                     "mape": float(np.mean(np.abs(yo - po)[yo > 0] / yo[yo > 0]) * 100),
                     "r": float(np.corrcoef(yo, po)[0, 1])}
    # dias de demanda alta (acima do percentil 90 de cada UF): o modelo os antecipa?
    alto_o, alto_p = np.zeros(len(yo), bool), np.zeros(len(yo), bool)
    for k in np.unique(u):
        s = u == k
        alto_o[s] = yo[s] > np.percentile(yo[s], 90)
        alto_p[s] = po[s] > np.percentile(po[s], 90)
    out["dias_altos"] = {"acuracia": float(accuracy_score(alto_o, alto_p)), "precisao": float(precision_score(alto_o, alto_p, zero_division=0)),
                         "sensibilidade": float(recall_score(alto_o, alto_p, zero_division=0)),
                         "f1": float(f1_score(alto_o, alto_p, zero_division=0))}
    al = X3 >= C.LIMIAR_ACAO
    out["alerta_razao"] = float(y[al].sum() / p[al].sum()) if al.any() else None
    if calib:
        q = np.quantile(p, np.linspace(0, 1, 11))
        b = np.clip(np.searchsorted(q, p, side="right") - 1, 0, 9)
        out["calibracao"] = [[float(p[b == k].mean()), float(y[b == k].mean())] for k in range(10) if (b == k).any()]
    return out


def treinar(M: dict, log=print, fracao: float = FRACAO_TREINO, semente: int = 7) -> tuple[dict, dict, dict]:
    """
    M: matrizes da validação (validacao.matrizes). Devolve (modelos, metadados, previsões por área
    no período de validação e teste para o painel).
    """
    t0 = time.time()
    rng = np.random.default_rng(semente)
    m, dias, Em, X, Y, k0 = M["m"], M["dias"], M["Em"], M["X"], M["Y"], M["k0"]
    nd, nm = len(dias), len(m)
    i_ini = JANELA_BASE + DEFASAGEM_BASE
    cal, mun = _calendario(dias), _municipais(m, M["S"], M["C"])

    def bloco(d0, d1):
        a = max(dias.get_indexer([pd.Timestamp(d0)])[0], i_ini)
        b = dias.get_indexer([pd.Timestamp(d1)])[0]
        return a, b

    a_tr, b_tr = bloco(dias[0].date(), TREINO_ATE)
    a_va, b_va = bloco(*VALID)
    a_te, b_te = bloco(*TESTE)
    if min(a_tr, b_tr, a_va, b_va, a_te, b_te) < 0 or b_tr <= a_tr:
        raise ValueError("período insuficiente para a divisão temporal treino/validação/teste")

    def linhas(a, b, frac=1.0):
        n = (b - a + 1) * nm
        idx = np.arange(n) if frac >= 1 else np.sort(rng.choice(n, int(n * frac), replace=False))
        return a + idx // nm, idx % nm

    conj = {"treino": linhas(a_tr, b_tr, fracao), "validacao": linhas(a_va, b_va), "teste": linhas(a_te, b_te)}
    modelos, meta, prev = {}, {"grupos": {}}, {}
    uf_cod = mun["uf"].astype(int)
    for g in GRUPOS_MODELO:
        cs = np.vstack([np.zeros((1, nm)), np.cumsum(Y[g], axis=0, dtype=np.float64)])
        base = np.full((nd, nm), np.nan, dtype=np.float32)
        i = np.arange(i_ini, nd)
        base[i] = ((cs[i - DEFASAGEM_BASE] - cs[i - DEFASAGEM_BASE - JANELA_BASE]) / JANELA_BASE).astype(np.float32)
        Xs = {k: matriz(ii, jj, base, Em, X, cal, mun, k0) for k, (ii, jj) in conj.items()}
        ys = {k: Y[g][ii, jj] for k, (ii, jj) in conj.items()}
        ex = {k: np.maximum(np.nan_to_num(base[ii, jj], nan=BASE_MINIMA), BASE_MINIMA) for k, (ii, jj) in conj.items()}
        res = {}
        for nome, cols in (("com_clima", VARIAVEIS), ("sem_clima", [v for v in VARIAVEIS if v not in CLIMA])):
            sel = [VARIAVEIS.index(c) for c in cols]
            est = _modelo().set_params(categorical_features=[cols.index("uf")])
            est.fit(Xs["treino"][:, sel], ys["treino"] / ex["treino"], sample_weight=ex["treino"])
            fator = float(ys["validacao"].sum() / (est.predict(Xs["validacao"][:, sel]) * ex["validacao"]).sum())
            r = {"iteracoes": int(est.n_iter_), "fator_calibracao": fator}
            for k in ("validacao", "teste"):
                ii, jj = conj[k]
                p = est.predict(Xs[k][:, sel]) * ex[k] * fator
                r[k] = _metricas(ys[k], p, ii, uf_cod[jj], Xs[k][:, VARIAVEIS.index("X3")], calib=(nome == "com_clima"))
                if nome == "com_clima":
                    prev.setdefault(g, {})[k] = (ii, jj, p)
            res[nome] = r
            if nome == "com_clima":
                modelos[g] = (est, fator)
            log(f"  demanda {g} {nome}: {r['iteracoes']} iterações; teste D²={r['teste']['d2']:.3f} "
                f"MAE UF-dia={r['teste']['uf_dia']['mae']:.2f} F1={r['teste']['dias_altos']['f1']:.2f} "
                f"({time.time() - t0:.0f} s)")
        meta["grupos"][g] = {"nome": NOMES[g], **res}
    # demanda habitual para a operação: último ano completo
    a_base = len(dias) - JANELA_BASE
    base_oper = pd.DataFrame({"cod_ibge": m["cod_ibge"].astype(str)})
    for g in GRUPOS_MODELO:
        base_oper[f"base_{g}"] = Y[g][a_base:].mean(0).round(4)
    meta.update({
        "versao": __version__, "treinado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algoritmo": "gradient boosting de árvores com perda de Poisson e a demanda habitual como exposição "
                     "(scikit-learn HistGradientBoostingRegressor)",
        "variaveis": VARIAVEIS, "variaveis_clima": CLIMA,
        "periodos": {"treino": [dias[a_tr].date().isoformat(), dias[b_tr].date().isoformat()],
                     "validacao": [dias[a_va].date().isoformat(), dias[b_va].date().isoformat()],
                     "teste": [dias[a_te].date().isoformat(), dias[b_te].date().isoformat()]},
        "fracao_treino": fracao, "linhas_treino": int(len(conj["treino"][0])),
        "base_operacional": [dias[a_base].date().isoformat(), dias[-1].date().isoformat()],
    })
    # previsões agregadas por área (Brasil e UFs) para o painel
    series = {}
    d_va = dias[a_va]
    n_prev = b_te - a_va + 1
    for g, partes in prev.items():
        for k, (ii, jj, p) in partes.items():
            pos = ii - a_va
            arr_br = series.setdefault("BR", {}).setdefault(f"prev_{g}", np.zeros(n_prev))
            arr_br += np.bincount(pos, p, minlength=n_prev)
            for u in np.unique(uf_cod[jj]):
                s = uf_cod[jj] == u
                arr = series.setdefault(UF_ORDEM[u], {}).setdefault(f"prev_{g}", np.zeros(n_prev))
                arr += np.bincount(pos[s], p[s], minlength=n_prev)
    for a, v in series.items():
        for k in list(v):
            v[k] = np.round(v[k], 1).tolist()
        v["prev_d0"] = d_va.date().isoformat()
    log(f"  modelos de demanda prontos ({time.time() - t0:.0f} s)")
    return modelos, meta, {"base": base_oper, "series": series}


def gravar(modelos: dict, meta: dict, extra: dict, pasta_modelos: Path | None = None, pasta_ref: Path | None = None):
    import joblib
    pasta_modelos = Path(pasta_modelos or DIR_MODELOS)
    pasta_modelos.mkdir(parents=True, exist_ok=True)
    for g, (est, fator) in modelos.items():
        joblib.dump({"modelo": est, "fator": fator, "variaveis": VARIAVEIS, "versao": meta["versao"]},
                    pasta_modelos / f"demanda_{g}.joblib", compress=3)
    (pasta_modelos / "demanda.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    pasta_ref = Path(pasta_ref or (C.DIR_DADOS / "ref"))
    extra["base"].to_csv(pasta_ref / "demanda_base.csv", index=False)


def carregar(pasta_modelos: Path | None = None):
    """Modelos e metadados; None se não houver modelo treinado ou o scikit-learn não estiver instalado."""
    pasta_modelos = Path(pasta_modelos or DIR_MODELOS)
    try:
        import joblib
        meta = json.loads((Path(pasta_modelos) / "demanda.json").read_text(encoding="utf-8"))
        mods = {g: joblib.load(Path(pasta_modelos) / f"demanda_{g}.joblib") for g in GRUPOS_MODELO}
        return mods, meta
    except Exception:  # noqa: BLE001
        return None


def prever(mods: dict, base: pd.DataFrame, m: pd.DataFrame, dias: pd.DatetimeIndex, Em: np.ndarray, ivc: np.ndarray,
           S, Cc, k_em: int) -> dict:
    """
    Previsão operacional para os dias 'dias' (linhas k_em.. de Em e ivc). Em e ivc: dia x município,
    com pelo menos 2 dias antes do primeiro dia previsto.
    """
    nd, nm = len(dias), len(m)
    X = ivc[k_em:k_em + nd].copy()
    for L in (1, 2):
        X = np.fmax(X, ivc[k_em - L:k_em + nd - L])
    cal, mun = _calendario(dias), _municipais(m, S, Cc)
    b = base.set_index("cod_ibge").reindex(m["cod_ibge"].astype(str))
    out = {}
    ii, jj = np.repeat(np.arange(nd), nm), np.tile(np.arange(nm), nd)
    for g, d in mods.items():
        bm = b[f"base_{g}"].to_numpy(dtype=np.float32)
        bg = np.broadcast_to(bm, (nd, nm))
        Xm = matriz(ii, jj, bg, Em, X, cal, mun, k_em)
        expo = np.maximum(np.nan_to_num(bm, nan=BASE_MINIMA), BASE_MINIMA)
        out[g] = (d["modelo"].predict(Xm[:, [VARIAVEIS.index(v) for v in d["variaveis"]]]).reshape(nd, nm)
                  * expo[None, :] * d.get("fator", 1.0))
    return out
