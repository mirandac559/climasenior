# -*- coding: utf-8 -*-
"""
Capacidade de resposta: estabelecimentos de atenção básica vinculados ao SUS por município
(CNES/DataSUS), terceiro componente do IVC (15%).

Fonte: arquivos ST (estabelecimentos), um por UF e mês de competência, em
ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/ST/ST{UF}{AA}{MM}.dbc
Conta-se, para a competência mais recente disponível em todas as UFs, os estabelecimentos
com vínculo SUS dos tipos posto de saúde (01), centro de saúde/unidade básica (02), unidade
mista (15) e unidade móvel fluvial (32). O índice usa a taxa por 10 mil habitantes: quanto
menor a taxa, menor a capacidade e maior a vulnerabilidade.

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

DIR_ST = "/dissemin/publicos/CNES/200508_/Dados/ST"
TIPOS_AB = {"01": "posto de saúde", "02": "centro de saúde/unidade básica", "15": "unidade mista",
            "32": "unidade móvel fluvial"}


def agregar_st(caminho) -> pd.DataFrame:
    col = SIH.ler_dbf(caminho, ["CODUFMUN", "TP_UNID", "VINC_SUS"])
    n = len(col["CODUFMUN"])
    mun = SIH._texto(col["CODUFMUN"], n).str[:6]
    tipo = SIH._texto(col["TP_UNID"], n).str.zfill(2)
    sus = SIH._texto(col["VINC_SUS"], n) if col["VINC_SUS"] is not None else pd.Series("1", index=mun.index)
    ok = tipo.isin(TIPOS_AB) & (sus == "1")
    out = mun[ok].value_counts().rename_axis("mun6").reset_index(name="estab_atencao_basica")
    out["mun6"] = pd.to_numeric(out["mun6"], errors="coerce")
    return out.dropna().astype({"mun6": np.int64})


def competencia_recente(nomes: list[str], ufs=SIH.UFS) -> str:
    """AAMM mais recente com arquivo para todas as UFs."""
    por_uf = {}
    for n in nomes:
        n = n.upper()
        if n.startswith("ST") and n.endswith(".DBC") and len(n) == 12:
            por_uf.setdefault(n[2:4], set()).add(n[4:8])
    comuns = set.intersection(*(por_uf.get(u, set()) for u in ufs))
    if not comuns:
        raise SIH.ErroSIH("nenhuma competência do CNES disponível para todas as UFs")
    return max(comuns, key=lambda aamm: (int(aamm[:2]), int(aamm[2:])))


def coletar(m: pd.DataFrame, fonte=None, descompactar=SIH.descomprimir, log=print) -> pd.DataFrame:
    fonte = fonte or SIH.FTPDataSUS(pasta=DIR_ST)
    nomes = fonte.listar("ST")
    reais = {n.upper(): n for n in nomes}
    aamm = competencia_recente(nomes)
    log(f"CNES: competência {aamm[2:]}/20{aamm[:2]}")
    partes = []
    with tempfile.TemporaryDirectory() as tmp:
        for uf in SIH.UFS:
            nome = f"ST{uf}{aamm}.DBC"
            dbc, dbf = os.path.join(tmp, "a.dbc"), os.path.join(tmp, "a.dbf")
            fonte.baixar(reais.get(nome, nome), dbc)
            descompactar(dbc, dbf)
            partes.append(agregar_st(dbf))
            for p in (dbc, dbf):
                if os.path.exists(p):
                    os.remove(p)
    est = pd.concat(partes).groupby("mun6", as_index=False)["estab_atencao_basica"].sum()
    out = pd.DataFrame({"cod_ibge": m["cod_ibge"].astype(str)})
    out["mun6"] = out["cod_ibge"].str[:6].astype(np.int64)
    out = out.merge(est, on="mun6", how="left").fillna({"estab_atencao_basica": 0})
    out["estab_atencao_basica"] = out["estab_atencao_basica"].astype(int)
    out["competencia"] = f"20{aamm[:2]}-{aamm[2:]}"
    log(f"  {int(out['estab_atencao_basica'].sum())} estabelecimentos em {int((out['estab_atencao_basica'] > 0).sum())} "
        f"de {len(out)} municípios")
    return out[["cod_ibge", "estab_atencao_basica", "competencia"]]


def main():
    ap = argparse.ArgumentParser(description="Capacidade de resposta (CNES) por município")
    ap.add_argument("--saida", default=str(C.DIR_DADOS / "ref" / "capacidade.csv"))
    a = ap.parse_args()
    m = pd.read_csv(C.DIR_DADOS / "ref" / "municipios_br.csv", dtype={"cod_ibge": str})
    cap = coletar(m)
    cap.to_csv(a.saida, sep=";", index=False)
    print(f"gravado em {a.saida}")


if __name__ == "__main__":
    sys.exit(main())
