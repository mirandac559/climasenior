# -*- coding: utf-8 -*-
"""
Verificação de coerência dos dados publicados no painel.

Confere, a partir dos arquivos gerados (site/data) e das referências (data/ref, data/clima):
  - cobertura: municípios, células, dias contínuos, previsão no fim;
  - o IVC publicado é igual ao recalculado a partir da temperatura gravada, da climatologia,
    da sensibilidade e da capacidade (amostra de dias e municípios);
  - população 60+ coerente com o Censo 2022; capacidade e sensibilidade entre 0 e 1;
  - internações previstas não negativas e coerentes com a demanda habitual;
  - resultados da validação internamente consistentes (faixas somam 100%, limiares monótonos).

Uso: python -m climasenior.verificar [pasta_do_site_data]
Sai com código 1 se alguma verificação falhar.
"""
from __future__ import annotations
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import brasil as B
from . import config as C


class Relatorio:
    def __init__(self):
        self.itens = []

    def ok(self, cond: bool, texto: str):
        self.itens.append((bool(cond), texto))
        print(("  OK    " if cond else "  FALHA ") + texto, flush=True)

    @property
    def falhas(self):
        return [t for c, t in self.itens if not c]


def verificar(site: Path = C.DIR_SITE_DADOS, base: Path = C.DIR_DADOS, amostra: int = 12) -> Relatorio:
    R = Relatorio()
    site, base = Path(site), Path(base)
    P = B.Pastas(base, site)
    meta = json.loads((site / "meta.json").read_text(encoding="utf-8"))
    mun = json.loads((site / "municipios.json").read_text(encoding="utf-8"))
    m = pd.read_csv(P.ref / "municipios_br.csv", dtype={"cod_ibge": str, "celula": str})
    cel = pd.read_csv(P.ref / "celulas.csv", dtype={"celula": str})
    print("Cobertura")
    R.ok(len(mun["cod"]) == meta["n_municipios"] == len(m), f"{meta['n_municipios']} municípios no painel e na referência")
    R.ok(len(mun["celulas"]) == meta["n_celulas"] == len(cel), f"{meta['n_celulas']} células climáticas")
    R.ok(min(mun["cel"]) >= 0, "todos os municípios têm célula climática")
    dias = [pd.Timestamp(d) for d, _ in meta["dias"]]
    R.ok(all((b - a).days == 1 for a, b in zip(dias, dias[1:])), f"{len(dias)} dias contínuos, de {dias[0].date()} a {dias[-1].date()}")
    R.ok(meta["data_referencia"] in {d for d, _ in meta["dias"]}, f"data de referência {meta['data_referencia']} está no painel")
    fontes = [f for _, f in meta["dias"]]
    R.ok(fontes[-1] == "p" and "o" in fontes, "dias observados no início e previsão no fim")
    R.ok(all((site / "dia" / f"{d.date()}.json").exists() for d in dias), "um arquivo por dia")

    print("População, sensibilidade e capacidade")
    pop60 = np.nansum(np.array(mun["pop60"], dtype=float))
    R.ok(31.5e6 < pop60 < 33.0e6, f"população 60+ total {pop60 / 1e6:.2f} milhões (Censo 2022: 32,1 milhões)")
    S = np.array(mun["S"], dtype=float)
    R.ok(np.nanmin(S) >= 0 and np.nanmax(S) <= 1, "sensibilidade entre 0 e 1")
    if mun.get("C") is not None:
        Cc = np.array(mun["C"], dtype=float)
        R.ok(np.nanmin(Cc) >= 0 and np.nanmax(Cc) <= 1, "capacidade entre 0 e 1")
    w = meta["pesos"]
    R.ok(abs(sum(w.values()) - 1) < 1e-9, f"pesos somam 1 ({w})")

    print("IVC publicado = IVC recalculado")
    rng = np.random.default_rng(1)
    obs = [d for d, f in zip(dias, fontes) if f == "o"]
    escolhidos = sorted(rng.choice(len(obs), min(amostra, len(obs)), replace=False)) if obs else []
    ref = cel.set_index("celula")
    difs = []
    for k in escolhidos:
        d = obs[k].date()
        tx = B.ler_dias(P, d - timedelta(days=31), d + timedelta(days=2))
        if tx.empty:
            continue
        t = ((tx["tmax"] + tx["tmin"]) / 2).groupby([tx["data"], tx["celula"]]).first().unstack()
        vies = pd.read_csv(P.ref / "vies.csv", dtype={"celula": str}).set_index("celula") if (P.ref / "vies.csv").exists() else None
        fonte = tx.pivot_table(index="data", columns="celula", values="fonte", aggfunc="first")
        if vies is not None:
            mod = fonte.isin(["modelo", "previsao"]).reindex(index=t.index, columns=t.columns, fill_value=False)
            vx = vies.reindex(t.columns)
            t = t - mod * ((vx["vies_tmax"] + vx["vies_tmin"]) / 2).fillna(0).to_numpy()
        E = B.exposicao(t, ref.reindex(t.columns))["E"].loc[pd.Timestamp(d)]
        e_mun = E.reindex([mun["celulas"][i] for i in mun["cel"]]).to_numpy()
        Cc = np.array(mun["C"], dtype=float) if mun.get("C") is not None else 0
        ivc = np.round(100 * (w["exposicao"] * e_mun + w["sensibilidade"] * S + w["capacidade"] * Cc))
        pub = np.array(json.loads((site / "dia" / f"{d}.json").read_text(encoding="utf-8"))["ivc"], dtype=float)
        ok = np.isfinite(pub) & np.isfinite(ivc)
        difs.append(np.abs(ivc[ok] - pub[ok]))
    if difs:
        dd = np.concatenate(difs)
        R.ok(len(dd) > 0 and (dd <= 1).mean() > 0.999 and np.mean(dd == 0) > 0.95,
             f"{len(difs)} dias observados x {len(S)} municípios: {np.mean(dd == 0) * 100:.1f}% idênticos, "
             f"diferença máxima {dd.max():.0f}")

    print("Internações previstas")
    hoje = json.loads((site / "dia" / f"{meta['data_referencia']}.json").read_text(encoding="utf-8"))
    if "dem" in hoje:
        dem = np.array(hoje["dem"], dtype=float) / 100
        demc = np.array(hoje["demc"], dtype=float) / 100
        R.ok(np.nanmin(dem) >= 0 and np.nanmin(demc) >= 0, "previsões não negativas")
        R.ok(np.nanmean(demc <= dem + 0.01) > 0.99, "sensíveis ao calor não excedem o total")
        if (P.ref / "demanda_base.csv").exists():
            bse = pd.read_csv(P.ref / "demanda_base.csv", dtype={"cod_ibge": str}).set_index("cod_ibge").reindex(mun["cod"])
            r = np.nansum(dem) / bse["base_todas"].sum()
            R.ok(0.6 < r < 1.6, f"total previsto no dia / demanda habitual = {r:.2f} ({np.nansum(dem):,.0f} internações)".replace(",", "."))
        R.ok(meta.get("demanda") is not None, "metadados do modelo de demanda no painel")
    else:
        R.ok(False, "o painel não traz internações previstas (modelo ausente)")

    vpath = site / "validacao" / "resultados.json"
    print("Validação")
    if vpath.exists():
        v = json.loads(vpath.read_text(encoding="utf-8"))
        br = v["areas"]["BR"]["grupos"]
        soma = sum(f["dias_pct"] for f in br["calor"]["faixas"])
        R.ok(abs(soma - 100) < 0.2, f"faixas somam {soma:.1f}% dos dias")
        lims = br["calor"]["limiares"]
        R.ok(all(a["dias_pct"] >= b["dias_pct"] for a, b in zip(lims, lims[1:])), "dias em alerta diminuem com o limiar")
        a = br["calor"]["alerta"]
        R.ok(a["lo"] <= a["rr"] <= a["hi"], f"razão {a['rr']} dentro do intervalo ({a['lo']} a {a['hi']})")
        R.ok(abs(a["dias_pct"] - sum(f["dias_pct"] for f in br["calor"]["faixas"] if f["faixa"] in ("ALTA", "MUITO ALTA"))) < 0.05,
             "dias em alerta = dias nas faixas ALTA e MUITO ALTA")
        R.ok(v["pesos"] == meta["pesos"], "validação feita com os mesmos pesos do painel")
        R.ok(len(v["areas"]) == 28 and len(v["regioes"]) == 5, "Brasil, 27 UFs e 5 regiões")
        if "demanda" in v:
            for g, x in v["demanda"].items():
                t = x["com_clima"]["teste"]
                R.ok(0.85 < t["razao_total"] < 1.15, f"modelo {g}: observado/previsto em 2025 = {t['razao_total']:.3f}")
                R.ok(t["d2"] >= x["sem_clima"]["teste"]["d2"] - 1e-3, f"modelo {g}: calor não piora o ajuste "
                     f"(D² {t['d2']:.3f} contra {x['sem_clima']['teste']['d2']:.3f})")
    else:
        R.ok(False, "resultados da validação ausentes")
    print(f"\n{len(R.itens) - len(R.falhas)} de {len(R.itens)} verificações OK")
    return R


def main():
    site = Path(sys.argv[1]) if len(sys.argv) > 1 else C.DIR_SITE_DADOS
    R = verificar(site)
    sys.exit(1 if R.falhas else 0)


if __name__ == "__main__":
    main()
