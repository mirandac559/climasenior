# -*- coding: utf-8 -*-
"""
Figuras do artigo (Cadernos de Saúde Pública) a partir dos resultados da validação
(data/validacao). Gera, em português e em inglês, PNG a 600 dpi e SVG/EPS vetoriais,
com 17 cm de largura e sem títulos (títulos e legendas vão em arquivo de texto à parte).

    python scripts/figuras_artigo.py --saida figuras_artigo
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
VAL = RAIZ / "data" / "validacao"
CM = 1 / 2.54
LARG = 17 * CM
AZUL, CINZA_E, CINZA_M, CINZA_C = "#1F5FA8", "#3A3A3A", "#7A7A7A", "#AAAAAA"

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Liberation Sans", "Arial", "DejaVu Sans"],
    "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5, "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.6,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42,
})

T = {
    "pt": {
        "dec": ",", "grupos": {"calor": "Sensíveis ao calor", "resp": "Aparelho respiratório",
                               "todas": "Todas as causas clínicas", "circ": "Aparelho circulatório"},
        "faixas": {"MODERADA": "Moderada", "ALTA": "Alta", "MUITO ALTA": "Muito alta"},
        "rt": "Razão de taxas", "pA": "A. Por faixa do IVC (referência: baixa)", "pB": "B. Por defasagem (IVC ≥ 60)",
        "faixa": "Faixa do IVC", "defas": "Defasagem em relação ao dia de alerta (dias)",
        "cs": "Sul, Sudeste e Centro-Oeste", "nn": "Norte e Nordeste", "vazio": "Símbolo vazado: IC95% inclui 1",
        "brasil": "Brasil", "col_rt": "Razão de taxas (IC95%)",
        "eixo3": "Razão de taxas (escala limitada a 0,4–2,0; setas indicam intervalos além dela)",
        "media": "Média móvel de 7 dias", "diario": "Valor diário", "mediana": "Mediana do ano",
        "faixa_alerta": "Dias com ≥ 50% dos idosos em municípios em alerta",
        "y_int": "Internações por dia", "y_al": "Idosos em municípios\nem alerta (%)",
        "meses": ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"],
        "pico": "{v} em {d}/{m}",
    },
    "en": {
        "dec": ".", "grupos": {"calor": "Heat-sensitive causes", "resp": "Respiratory system",
                               "todas": "All clinical causes", "circ": "Circulatory system"},
        "faixas": {"MODERADA": "Moderate", "ALTA": "High", "MUITO ALTA": "Very high"},
        "rt": "Rate ratio", "pA": "A. By CVI band (reference: low)", "pB": "B. By lag (CVI ≥ 60)",
        "faixa": "CVI band", "defas": "Lag relative to the alert day (days)",
        "cs": "South, Southeast and Central-West", "nn": "North and Northeast", "vazio": "Open symbol: 95%CI includes 1",
        "brasil": "Brazil", "col_rt": "Rate ratio (95%CI)",
        "eixo3": "Rate ratio (scale limited to 0.4–2.0; arrows mark intervals beyond it)",
        "media": "7-day moving average", "diario": "Daily value", "mediana": "Annual median",
        "faixa_alerta": "Days with ≥ 50% of older adults in municipalities on alert",
        "y_int": "Admissions per day", "y_al": "Older adults in\nmunicipalities on alert (%)",
        "meses": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "pico": "{v} on {m} {d}",
    },
}
UF_NOME = {
    "pt": {"AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
           "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais",
           "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
           "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia",
           "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
           "TO": "Tocantins"},
}
UF_NOME["en"] = UF_NOME["pt"]
NN = {"AC", "AM", "AP", "PA", "RO", "RR", "TO", "AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"}
ESTILO = {"calor": dict(color=AZUL, marker="o", ls="-", ms=4.2),
          "resp": dict(color=CINZA_E, marker="s", ls="-", ms=3.6),
          "todas": dict(color=CINZA_M, marker="^", ls="--", ms=3.8),
          "circ": dict(color=CINZA_C, marker="D", ls=":", ms=3.4)}


def num(x, nd, lang):
    s = f"{x:.{nd}f}"
    return s.replace(".", ",") if T[lang]["dec"] == "," else s


def salvar(fig, saida: Path, nome: str):
    saida.mkdir(parents=True, exist_ok=True)
    fig.savefig(saida / f"{nome}.png", dpi=600)
    fig.savefig(saida / f"{nome}.svg")
    fig.savefig(saida / f"{nome}.eps")
    plt.close(fig)


# ----------------------------------------------------------------------------- Figura 1
def figura1(lang: str, saida: Path):
    L = {
        "pt": [("Temperatura", ["CPC/NOAA, grade de 0,5°", "Open-Meteo (previsão)"]),
               ("População", ["IBGE, Censo 2022", "pessoas com 60+ e 80+"]),
               ("Atenção primária", ["CNES/DATASUS", "equipes eSF e eAP"]),
               ("Internações", ["SIH/SUS, 2014–2025", "urgência, 60+ anos"]),
               ("Exposição (E), 60%", ["EHF relativo ao clima", "da própria célula"]),
               ("Sensibilidade (S), 25%", ["proporções de 60+", "e de 80+ anos"]),
               ("Capacidade (C), 15%", ["equipes por habitante", "(menos equipes, C maior)"]),
               ("IVC diário por município (0–100)", ["5.571 municípios · observado e previsão de 7 dias · alerta com IVC ≥ 60"]),
               ("Painel e protocolo", ["faixas e condutas por município", "dados abertos (JSON e CSV)"]),
               ("Validação retrospectiva", ["razão de taxas de Mantel-Haenszel", "por faixa, defasagem e UF"]),
               ("Modelo de demanda", ["gradient boosting (Poisson)", "internações previstas por dia"]),
               "operação diária", "IVC histórico + SIH"],
        "en": [("Temperature", ["CPC/NOAA, 0.5° grid", "Open-Meteo (forecast)"]),
               ("Population", ["IBGE, 2022 Census", "people aged 60+ and 80+"]),
               ("Primary care", ["CNES/DATASUS", "eSF and eAP teams"]),
               ("Hospital admissions", ["SIH/SUS, 2014–2025", "emergency, aged 60+"]),
               ("Exposure (E), 60%", ["EHF relative to the", "cell's own climate"]),
               ("Sensitivity (S), 25%", ["shares of people", "aged 60+ and 80+"]),
               ("Capacity (C), 15%", ["teams per inhabitant", "(fewer teams, higher C)"]),
               ("Daily CVI per municipality (0–100)", ["5,571 municipalities · observed and 7-day forecast · alert at CVI ≥ 60"]),
               ("Dashboard and protocol", ["bands and actions by municipality", "open data (JSON and CSV)"]),
               ("Retrospective validation", ["Mantel-Haenszel rate ratios", "by band, lag and state"]),
               ("Demand model", ["gradient boosting (Poisson)", "predicted daily admissions"]),
               "daily operation", "historical CVI + SIH"],
    }[lang]
    fig = plt.figure(figsize=(LARG, 10.6 * CM))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 170)
    ax.set_ylim(0, 106)
    ax.axis("off")

    def caixa(x, y, w, h, nome, linhas, destaque=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.8",
                                    fc="#E8EFF8" if destaque else "white", ec=AZUL if destaque else "#555555",
                                    lw=1.2 if destaque else 0.7))
        ax.text(x + 2.2, y + h - 3.6, nome, fontsize=8, fontweight="bold", va="center", ha="left")
        for k, l in enumerate(linhas):
            ax.text(x + 2.2, y + h - 8.4 - 4.3 * k, l, fontsize=7.2, va="center", ha="left", color="#333333")

    def seta(x0, y0, x1, y1, ponta=True):
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-|>" if ponta else "-", lw=0.8, color="#555555",
                                    shrinkA=0, shrinkB=0, mutation_scale=7))

    w, h, g = 38.5, 15, 4.3
    xs = [2 + i * (w + g) for i in range(4)]
    yA, yB, yC, yD = 88, 64, 41, 4
    for i in range(4):
        caixa(xs[i], yA, w, h, *L[i])
    for i in range(3):
        caixa(xs[i], yB, w, h, *L[4 + i])
        seta(xs[i] + w / 2, yA, xs[i] + w / 2, yB + h)
        seta(xs[i] + w / 2, yB, xs[i] + w / 2, yC + 12)
    wC = xs[2] + w - xs[0]
    caixa(xs[0], yC, wC, 12, *L[7], destaque=True)
    wd = (166 - 2 * g) / 3
    xd = [2 + i * (wd + g) for i in range(3)]
    for i in range(3):
        caixa(xd[i], yD, wd, h, *L[8 + i])
    yb = 27                                    # barramento: IVC histórico + internações
    seta(xd[0] + 14, yC, xd[0] + 14, yD + h)
    seta(xs[2] + 22, yC, xs[2] + 22, yb, ponta=False)
    seta(xs[3] + w / 2, yA, xs[3] + w / 2, yb, ponta=False)
    seta(xs[3] + w / 2, yb, xd[1] + wd / 2, yb, ponta=False)
    seta(xd[1] + wd / 2, yb, xd[1] + wd / 2, yD + h)
    seta(xd[2] + wd / 2, yb, xd[2] + wd / 2, yD + h)
    for xp in (xs[2] + 22, xd[2] + wd / 2):
        ax.plot([xp], [yb], "o", ms=2.2, color="#555555")
    ax.text(xd[0] + 16, (yC + yD + h) / 2 - 1, L[11], fontsize=7, color="#555555", va="center")
    ax.text(xs[2] + 24, yb + 2.4, L[12], fontsize=7, color="#555555", va="bottom")
    salvar(fig, saida, f"Figura1_{lang}" if lang == "pt" else f"Figure1_{lang}")


# ----------------------------------------------------------------------------- Figura 2
def figura2(lang: str, saida: Path, res: dict):
    t = T[lang]
    br = res["areas"]["BR"]["grupos"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(LARG, 7.6 * CM), gridspec_kw={"width_ratios": [1, 1.25], "wspace": 0.28})
    ordem = ["calor", "resp", "todas", "circ"]
    dx = dict(zip(ordem, [-0.24, -0.08, 0.08, 0.24]))
    for g in ordem:
        f = [x for x in br[g]["faixas"] if x["faixa"] != "BAIXA"]
        x = np.arange(len(f)) + dx[g]
        y = np.array([v["rr"] for v in f])
        lo, hi = np.array([v["lo"] for v in f]), np.array([v["hi"] for v in f])
        st = ESTILO[g]
        a1.errorbar(x, y, yerr=[y - lo, hi - y], fmt=st["marker"], color=st["color"], ms=st["ms"], lw=0.9,
                    capsize=0, label=t["grupos"][g])
        d = br[g]["defasagens"]
        L = np.array([v["l"] for v in d])
        y2, lo2, hi2 = (np.array([v[k] for v in d]) for k in ("rr", "lo", "hi"))
        a2.errorbar(L, y2, yerr=[y2 - lo2, hi2 - y2], color=st["color"], marker=st["marker"], ms=st["ms"] - 0.6,
                    ls=st["ls"], lw=1.1, capsize=0, label=t["grupos"][g])
    for a in (a1, a2):
        a.axhline(1, color="#555555", lw=0.7, ls=(0, (4, 3)), zorder=0)
        a.set_ylim(0.9, 1.45)
        a.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: num(v, 1, lang)))
        a.grid(axis="y", color="#E3E3E3", lw=0.5)
        a.set_axisbelow(True)
    a1.set_xticks(range(3), [t["faixas"][k] for k in ("MODERADA", "ALTA", "MUITO ALTA")])
    a1.set_xlim(-0.5, 2.5)
    a1.set_xlabel(t["faixa"])
    a1.set_ylabel(t["rt"])
    a1.set_title(t["pA"], loc="left", fontweight="bold")
    a2.set_xticks(range(8))
    a2.set_xlabel(t["defas"])
    a2.set_title(t["pB"], loc="left", fontweight="bold")
    pm = [v for v in br["calor"]["faixas"] if v["faixa"] == "MUITO ALTA"][0]
    a1.annotate(num(pm["rr"], 2, lang), (2 - 0.24, pm["rr"]), xytext=(-6, 0), textcoords="offset points",
                ha="right", va="center", fontsize=7.5, fontweight="bold")
    pk = max(br["calor"]["defasagens"], key=lambda v: v["rr"])
    a2.annotate(num(pk["rr"], 2, lang), (pk["l"], pk["hi"]), xytext=(0, 4), textcoords="offset points",
                ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    h, lab = a2.get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.01), handlelength=2.6)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.92, bottom=0.27)
    salvar(fig, saida, f"Figura2_{lang}" if lang == "pt" else f"Figure2_{lang}")


# ----------------------------------------------------------------------------- Figura 3
def figura3(lang: str, saida: Path, res: dict):
    t = T[lang]
    linhas = []
    for uf, a in res["areas"].items():
        if uf == "BR":
            continue
        al = a["grupos"]["calor"]["alerta"]
        linhas.append((uf, al["rr"], al["lo"], al["hi"]))
    df = pd.DataFrame(linhas, columns=["uf", "rr", "lo", "hi"]).sort_values("rr", ascending=True).reset_index(drop=True)
    br = res["areas"]["BR"]["grupos"]["calor"]["alerta"]
    fig = plt.figure(figsize=(LARG, 13.4 * CM))
    ax = fig.add_axes([0.25, 0.13, 0.5, 0.83])
    lo_v, hi_v = 0.4, 2.0
    for i, r in df.iterrows():
        cor = CINZA_M if r["uf"] in NN else AZUL
        sig = r["lo"] > 1 or r["hi"] < 1
        a, b = max(r["lo"], lo_v), min(r["hi"], hi_v)
        ax.plot([a, b], [i, i], color=cor, lw=1.1, solid_capstyle="butt", zorder=2)
        if r["lo"] < lo_v:
            ax.plot([lo_v], [i], marker="<", color=cor, ms=4, zorder=3)
        if r["hi"] > hi_v:
            ax.plot([hi_v], [i], marker=">", color=cor, ms=4, zorder=3)
        ax.plot([r["rr"]], [i], "o", ms=4.6, mfc=cor if sig else "white", mec=cor, mew=1.1, zorder=4)
        ax.text(hi_v + 0.06, i, f"{num(r['rr'], 2, lang)} ({num(r['lo'], 2, lang)}–{num(r['hi'], 2, lang)})",
                va="center", ha="left", fontsize=7.3, transform=ax.transData, clip_on=False)
    ax.set_yticks(range(len(df)), [UF_NOME[lang][u] for u in df["uf"]])
    ax.axvline(1, color="#555555", lw=0.7, zorder=1)
    ax.axvline(br["rr"], color=AZUL, lw=0.8, ls=(0, (4, 3)), zorder=1)
    ax.text(br["rr"] + 0.02, len(df) - 0.2, f"{t['brasil']} {num(br['rr'], 2, lang)}", ha="left", va="bottom", fontsize=7.3,
            color=AZUL, fontweight="bold")
    ax.text(hi_v + 0.06, len(df) - 0.2, t["col_rt"], ha="left", va="bottom", fontsize=7.3, fontweight="bold",
            clip_on=False)
    ax.set_xlim(lo_v, hi_v)
    ax.set_ylim(-0.7, len(df) + 0.6)
    ax.set_xticks([0.5, 1, 1.5, 2], [num(v, 1, lang) for v in (0.5, 1, 1.5, 2)])
    ax.set_xlabel(t["eixo3"], fontsize=7.3)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#E3E3E3", lw=0.5)
    ax.set_axisbelow(True)
    from matplotlib.lines import Line2D
    leg = [Line2D([], [], marker="o", ls="", color=AZUL, ms=4.6, label=t["cs"]),
           Line2D([], [], marker="o", ls="", color=CINZA_M, ms=4.6, label=t["nn"]),
           Line2D([], [], marker="o", ls="", mfc="white", mec="#555555", ms=4.6, label=t["vazio"])]
    fig.legend(handles=leg, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.005))
    salvar(fig, saida, f"Figura3_{lang}" if lang == "pt" else f"Figure3_{lang}")


# ----------------------------------------------------------------------------- Figura S1
def figura_s1(lang: str, saida: Path):
    t = T[lang]
    s = json.loads((VAL / "serie" / "SP.json").read_text(encoding="utf-8"))
    d0 = pd.Timestamp(s["d0"])
    dias = pd.date_range(d0, periods=len(s["calor"]))
    df = pd.DataFrame({"c": s["calor"], "a": s["alerta_pop"]}, index=dias).loc["2023"]
    mm = df["c"].rolling(7, center=True, min_periods=4).mean()
    med = float(df["c"].median())
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(LARG, 9.4 * CM), sharex=True,
                                 gridspec_kw={"height_ratios": [3.2, 1], "hspace": 0.12})
    em = df["a"] >= 50
    blocos, ini = [], None
    for d, v in em.items():
        if v and ini is None:
            ini = d
        if not v and ini is not None:
            blocos.append((ini, prev))
            ini = None
        prev = d
    if ini is not None:
        blocos.append((ini, prev))
    for a in (a1, a2):
        for b0, b1 in blocos:
            a.axvspan(b0 - pd.Timedelta(hours=12), b1 + pd.Timedelta(hours=12), color="#E2E2E2", lw=0, zorder=0)
    a1.plot(df.index, df["c"], "o", ms=1.6, color=CINZA_C, label=t["diario"], zorder=2)
    a1.plot(mm.index, mm, color=AZUL, lw=1.4, label=t["media"], zorder=3)
    a1.axhline(med, color="#555555", lw=0.7, ls=(0, (4, 3)), label=f"{t['mediana']} ({med:.0f})", zorder=1)
    ip = mm.idxmax()
    a1.plot([ip], [mm.max()], "o", ms=3.5, color=AZUL, zorder=4)
    mes = t["meses"][ip.month - 1]
    a1.annotate(t["pico"].format(v=f"{mm.max():.0f}", d=ip.day, m=mes), (ip, mm.max()), xytext=(-6, 2),
                textcoords="offset points", ha="right", va="center", fontsize=7.5, fontweight="bold")
    a1.set_ylabel(t["y_int"])
    a1.set_ylim(100, 300)
    a1.grid(axis="y", color="#E3E3E3", lw=0.5)
    from matplotlib.patches import Patch
    h, lab = a1.get_legend_handles_labels()
    h.append(Patch(fc="#E2E2E2", ec="none"))
    lab.append(t["faixa_alerta"])
    a1.legend(h, lab, loc="upper left", ncol=2, frameon=False, fontsize=7)
    a2.fill_between(df.index, 0, df["a"], color=CINZA_M, lw=0, step="mid")
    a2.set_ylim(0, 100)
    a2.set_yticks([0, 50, 100])
    a2.set_ylabel(t["y_al"], fontsize=7)
    a2.grid(axis="y", color="#E3E3E3", lw=0.5)
    a2.set_axisbelow(True)
    ticks = pd.date_range("2023-01-01", "2023-12-01", freq="MS")
    a2.set_xticks(ticks, t["meses"])
    a2.set_xlim(pd.Timestamp("2022-12-28"), pd.Timestamp("2024-01-03"))
    fig.subplots_adjust(left=0.1, right=0.99, top=0.98, bottom=0.08)
    salvar(fig, saida, f"FiguraS1_{lang}" if lang == "pt" else f"FigureS1_{lang}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="figuras_artigo")
    a = ap.parse_args()
    res = json.loads((VAL / "resultados.json").read_text(encoding="utf-8"))
    for lang in ("pt", "en"):
        out = Path(a.saida) / lang
        figura1(lang, out)
        figura2(lang, out, res)
        figura3(lang, out, res)
        figura_s1(lang, out)
        print("figuras em", out)


if __name__ == "__main__":
    main()
