# -*- coding: utf-8 -*-
"""
Capacidade de resposta: cobertura da atenção primária por equipes de Saúde da Família e de
Atenção Primária (CNES/DataSUS), terceiro componente do IVC (15%).

As equipes de Saúde da Família fazem a busca ativa e o cuidado domiciliar de idosos que o
protocolo de resposta prevê; onde a cobertura é baixa, a capacidade de resposta ao calor é menor.

Fonte: arquivos EP (equipes), um por UF e mês de competência, em
ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/EP/EP{UF}{AA}{MM}.dbc
Para a competência mais recente disponível em todas as UFs, contam-se as equipes ativas
(sem data de desativação) de Saúde da Família (tipo 70) e de Atenção Primária (tipo 76).
Cobertura estimada, como no indicador do Ministério da Saúde: (eSF x 3.450 + eAP x 3.000)
pessoas / população, limitada a 100% na coluna cobertura_aps. No IVC usa-se a mesma razão sem
o teto, relativa ao percentil 99 do país (ver brasil.capacidade): componente = 1 - razão relativa.

Uso: python -m climasenior.cnes          (grava data/ref/capacidade.csv)
"""
from __future__ import annotations
import argparse
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import sih as SIH

DIR_CNES = "/dissemin/publicos/CNES/200508_/Dados"
TIPOS = {"70": ("esf", 3450), "76": ("eap", 3000)}
ATIVA = {"", "900001", "000000"}


def agregar_ep(caminho) -> pd.DataFrame:
    col = SIH.ler_dbf(caminho, ["CODUFMUN", "TIPO_EQP", "DT_DESAT", "IDEQUIPE"])
    n = len(col["CODUFMUN"])
    df = pd.DataFrame({"mun6": SIH._texto(col["CODUFMUN"], n).str[:6], "tipo": SIH._texto(col["TIPO_EQP"], n).str.zfill(2),
                       "desat": SIH._texto(col["DT_DESAT"], n), "id": SIH._texto(col["IDEQUIPE"], n)})
    df = df[df["tipo"].isin(TIPOS) & df["desat"].isin(ATIVA)]
    df = df.drop_duplicates(["mun6", "tipo", "id"]) if df["id"].ne("").any() else df
    out = df.pivot_table(index="mun6", columns="tipo", values="desat", aggfunc="size", fill_value=0)
    out = out.reindex(columns=list(TIPOS), fill_value=0).rename(columns={k: f"equipes_{v[0]}" for k, v in TIPOS.items()})
    out.index = pd.to_numeric(out.index, errors="coerce")
    return out[out.index.notna()].rename_axis("mun6").reset_index().astype(np.int64)


def competencia_recente(nomes: list[str], grupo: str = "EP", ufs=SIH.UFS) -> str:
    """AAMM mais recente com arquivo para todas as UFs."""
    por_uf, k = {}, len(grupo)
    for n in nomes:
        n = n.upper()
        if n.startswith(grupo) and n.endswith(".DBC") and len(n) == k + 10:
            por_uf.setdefault(n[k:k + 2], set()).add(n[k + 2:k + 6])
    comuns = set.intersection(*(por_uf.get(u, set()) for u in ufs))
    if not comuns:
        raise SIH.ErroSIH(f"nenhuma competência do CNES ({grupo}) disponível para todas as UFs")
    return max(comuns, key=lambda aamm: (int(aamm[:2]), int(aamm[2:])))


def coletar(m: pd.DataFrame, fonte=None, descompactar=SIH.descomprimir, log=print) -> pd.DataFrame:
    fonte = fonte or SIH.FTPDataSUS(pasta=f"{DIR_CNES}/EP")
    nomes = fonte.listar("EP")
    reais = {n.upper(): n for n in nomes}
    aamm = competencia_recente(nomes)
    log(f"CNES equipes: competência {aamm[2:]}/20{aamm[:2]}")
    partes = []
    with tempfile.TemporaryDirectory() as tmp:
        for uf in SIH.UFS:
            nome = f"EP{uf}{aamm}.DBC"
            dbc, dbf = os.path.join(tmp, "a.dbc"), os.path.join(tmp, "a.dbf")
            fonte.baixar(reais.get(nome, nome), dbc)
            descompactar(dbc, dbf)
            partes.append(agregar_ep(dbf))
            for p in (dbc, dbf):
                if os.path.exists(p):
                    os.remove(p)
    eq = pd.concat(partes).groupby("mun6", as_index=False).sum()
    out = pd.DataFrame({"cod_ibge": m["cod_ibge"].astype(str), "populacao": pd.to_numeric(m["populacao"], errors="coerce")})
    out["mun6"] = out["cod_ibge"].str[:6].astype(np.int64)
    out = out.merge(eq, on="mun6", how="left")
    cols = [f"equipes_{v[0]}" for v in TIPOS.values()]
    out[cols] = out[cols].fillna(0).astype(int)
    pessoas = sum(out[f"equipes_{v[0]}"] * v[1] for v in TIPOS.values())
    out["cobertura_aps"] = (pessoas / out["populacao"]).clip(upper=1).round(4)
    out["competencia"] = f"20{aamm[:2]}-{aamm[2:]}"
    log(f"  {int(out['equipes_esf'].sum())} equipes de Saúde da Família e {int(out['equipes_eap'].sum())} de Atenção "
        f"Primária; cobertura mediana {out['cobertura_aps'].median() * 100:.0f}%")
    return out[["cod_ibge"] + cols + ["cobertura_aps", "competencia"]]


def explorar(grupo: str, uf: str):
    """Mostra colunas e valores frequentes de um arquivo do CNES (diagnóstico do layout)."""
    fonte = SIH.FTPDataSUS(pasta=f"{DIR_CNES}/{grupo}")
    nomes = fonte.listar(grupo)
    aamm = max((n.upper()[len(grupo) + 2:len(grupo) + 6] for n in nomes if n.upper().startswith(grupo + uf)),
               key=lambda x: (int(x[:2]), int(x[2:])))
    with tempfile.TemporaryDirectory() as tmp:
        dbc, dbf = os.path.join(tmp, "a.dbc"), os.path.join(tmp, "a.dbf")
        nome = f"{grupo}{uf}{aamm}.dbc"
        fonte.baixar(nome, dbc)
        SIH.descomprimir(dbc, dbf)
        col = SIH.ler_dbf(dbf)
    linhas = [f"{nome}: {len(next(iter(col.values())))} registros; colunas: {', '.join(col)}"]
    for c, v in col.items():
        vc = pd.Series(v).str.decode("latin1").str.strip().value_counts()
        if 1 < len(vc) <= 60:
            linhas.append(f"{c}: " + "; ".join(f"{k}={n}" for k, n in vc.head(25).items()))
    texto = "\n".join(linhas)
    print(texto)
    from .validacao import aviso_actions
    aviso_actions(f"CNES {grupo} {uf}", texto)


def main():
    ap = argparse.ArgumentParser(description="Capacidade de resposta (CNES) por município")
    ap.add_argument("--saida", default=str(C.DIR_DADOS / "ref" / "capacidade.csv"))
    ap.add_argument("--explorar", help="ex.: EP:MA mostra o layout do arquivo de equipes do Maranhão")
    a = ap.parse_args()
    if a.explorar:
        g, uf = a.explorar.split(":")
        return explorar(g, uf)
    m = pd.read_csv(C.DIR_DADOS / "ref" / "municipios_br.csv", dtype={"cod_ibge": str})
    cap = coletar(m)
    cap.to_csv(a.saida, sep=";", index=False)
    print(f"gravado em {a.saida}")


if __name__ == "__main__":
    sys.exit(main())
