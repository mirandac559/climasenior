# -*- coding: utf-8 -*-
"""
Internações hospitalares do SUS (SIH/DataSUS) para a validação retrospectiva do IVC.

Fonte: arquivos RD (AIH reduzida), um por UF e mês de competência, em
ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RD{UF}{AA}{MM}.dbc
(DBC = DBF comprimido). Cada arquivo é baixado, descomprimido, reduzido a contagens
diárias por município de residência e descartado; nada nominal é guardado.

Contagem: internações (AIH tipo 1, sem as de continuação e longa permanência) de
pessoas com 60 anos ou mais, em caráter de urgência (as eletivas não respondem ao
calor do dia), por município de residência e data de internação, em quatro grupos de
diagnóstico principal (CID-10):

  calor   sensíveis ao calor, segundo Bobb et al. (JAMA, 2014): distúrbios de volume e
          hidroeletrolíticos (E86-E87), insuficiência renal aguda ou não especificada
          (N17, N19), infecção urinária (N39.0), septicemia (A40-A41) e efeitos do calor
          (T67, X30)
  circ    doenças do aparelho circulatório (I00-I99)
  resp    doenças do aparelho respiratório (J00-J99)
  todas   todas as causas clínicas (exclui lesões e causas externas, S00-T98 e V01-Y98,
          exceto T67 e X30; gravidez, O00-O99; e fatores de contato, Z00-Z99)
"""
from __future__ import annotations
import ftplib
import io
import json
import os
import struct
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

FTP_HOST = "ftp.datasus.gov.br"
DIR_RD = "/dissemin/publicos/SIHSUS/200801_/Dados"
UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI",
       "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
GRUPOS = ["calor", "circ", "resp", "todas"]
NOMES_GRUPOS = {
    "calor": "Sensíveis ao calor",
    "circ": "Aparelho circulatório",
    "resp": "Aparelho respiratório",
    "todas": "Todas as causas clínicas",
}
CIDS_GRUPOS = {
    "calor": "E86–E87, N17, N19, N39.0, A40–A41, T67, X30",
    "circ": "I00–I99",
    "resp": "J00–J99",
    "todas": "todas, exceto S00–T98 e V01–Y98 (salvo T67 e X30), O00–O99 e Z00–Z99",
}
COLUNAS = ["IDENT", "MUNIC_RES", "DT_INTER", "DIAG_PRINC", "COD_IDADE", "IDADE", "NASC", "CAR_INT"]


class ErroSIH(Exception):
    pass


# =============================================================================
# DBF: leitura direta das colunas necessárias (sem carregar o arquivo em objetos)
# =============================================================================
def ler_dbf(caminho, colunas=None) -> dict[str, np.ndarray]:
    """Devolve {coluna: array de bytes} só com os registros não apagados."""
    with open(caminho, "rb") as f:
        cab = f.read(32)
        nreg, tam_cab, tam_reg = struct.unpack("<IHH", cab[4:12])
        campos, pos = [], 1
        while True:
            d = f.read(32)
            if not d or d[0] == 0x0D:
                break
            nome = d[:11].split(b"\x00")[0].decode("latin1").strip().upper()
            tam = d[16] if d[11:12] != b"C" else d[16] + 256 * d[17]
            campos.append((nome, pos, tam))
            pos += tam
    if pos != tam_reg:
        raise ErroSIH(f"{caminho}: tamanho de registro inconsistente ({pos} != {tam_reg})")
    tamanho = os.path.getsize(caminho)
    nreg = min(nreg, max(0, (tamanho - tam_cab) // tam_reg))
    bruto = np.memmap(caminho, dtype=np.uint8, mode="r", offset=tam_cab, shape=(nreg * tam_reg,)).reshape(nreg, tam_reg)
    vivos = bruto[:, 0] != ord("*")
    nomes = {n for n, _, _ in campos}
    out = {}
    for nome, ini, tam in campos:
        if colunas is not None and nome not in colunas:
            continue
        out[nome] = np.ascontiguousarray(bruto[vivos, ini:ini + tam]).view(f"S{tam}").ravel()
    for c in (colunas or []):
        if c not in nomes:
            out[c] = None
    del bruto
    return out


def _texto(a: np.ndarray | None, n: int) -> pd.Series:
    if a is None:
        return pd.Series([""] * n, dtype=object)
    return pd.Series(a).str.decode("latin1").str.strip()


# =============================================================================
# Classificação e agregação
# =============================================================================
def classificar(diag: pd.Series) -> dict[str, np.ndarray]:
    d = diag.str.upper().str.replace(".", "", regex=False).str.ljust(4)
    c3, letra = d.str[:3], d.str[:1]
    num = pd.to_numeric(d.str[1:3], errors="coerce")
    calor_direto = c3.isin(["T67", "X30"])
    calor = (c3.isin(["E86", "E87", "N17", "N19", "A40", "A41"]) | (d.str[:4] == "N390") | calor_direto)
    externas = letra.isin(["S", "T", "V", "W", "X", "Y"]) & ~calor_direto
    todas = ~externas & ~letra.isin(["O", "Z"]) & (letra.str.match(r"[A-Z]") & num.notna())
    return {"calor": calor.to_numpy(), "circ": (letra == "I").to_numpy(), "resp": (letra == "J").to_numpy(),
            "todas": todas.to_numpy()}


def idade_anos(cod: pd.Series, idade: pd.Series, nasc: pd.Series, dt_inter: pd.Series) -> np.ndarray:
    i = pd.to_numeric(idade, errors="coerce")
    anos = np.where(cod == "4", i, np.where(cod == "5", i + 100, np.where(cod.isin(["2", "3"]), 0, np.nan)))
    # sem código de idade: calcula pela data de nascimento
    falta = np.isnan(anos)
    if falta.any():
        n = pd.to_datetime(nasc[falta], format="%Y%m%d", errors="coerce")
        t = pd.to_datetime(dt_inter[falta], format="%Y%m%d", errors="coerce")
        anos[falta] = ((t - n).dt.days / 365.25).to_numpy()
    return anos


def agregar_dbf(caminho, idade_min: int = 60) -> tuple[pd.DataFrame, dict]:
    """Contagens diárias por município de residência (6 dígitos) para os quatro grupos."""
    col = ler_dbf(caminho, COLUNAS)
    n = len(col["DT_INTER"]) if col.get("DT_INTER") is not None else 0
    info = {"registros": int(n)}
    if n == 0:
        return pd.DataFrame(columns=["mun6", "data"] + GRUPOS), info
    ident = _texto(col["IDENT"], n)
    car = _texto(col["CAR_INT"], n)
    dt = _texto(col["DT_INTER"], n)
    cod = _texto(col["COD_IDADE"], n)
    anos = idade_anos(cod, _texto(col["IDADE"], n), _texto(col["NASC"], n), dt)
    car_num = pd.to_numeric(car, errors="coerce")
    urgente = (car_num != 1) if col["CAR_INT"] is not None else pd.Series(True, index=car.index)
    manter = ((ident == "1") | (col["IDENT"] is None)) & urgente & (anos >= idade_min)
    info["aih_tipo1"] = int((ident == "1").sum())
    info["idosos_urgencia"] = int(manter.sum())
    if not manter.any():
        return pd.DataFrame(columns=["mun6", "data"] + GRUPOS), info
    mun = pd.to_numeric(_texto(col["MUNIC_RES"], n)[manter].str[:6], errors="coerce")
    data = pd.to_numeric(dt[manter], errors="coerce")
    g = classificar(_texto(col["DIAG_PRINC"], n)[manter].reset_index(drop=True))
    df = pd.DataFrame({"mun6": mun.to_numpy(), "data": data.to_numpy(), **{k: v.astype(np.int32) for k, v in g.items()}})
    df = df.dropna(subset=["mun6", "data"])
    df = df[(df["data"] >= 19000101) & (df["data"] <= 21001231)]
    df[["mun6", "data"]] = df[["mun6", "data"]].astype(np.int64)
    out = df.groupby(["mun6", "data"], as_index=False)[GRUPOS].sum()
    return out, info


# =============================================================================
# Download (FTP do DataSUS)
# =============================================================================
class FTPDataSUS:
    def __init__(self, host=FTP_HOST, pasta=DIR_RD, timeout=120):
        self.host, self.pasta, self.timeout = host, pasta, timeout
        self.ftp = None

    def _conectar(self):
        if self.ftp is not None:
            try:
                self.ftp.voidcmd("NOOP")
                return self.ftp
            except Exception:  # noqa: BLE001
                self.ftp = None
        ftp = ftplib.FTP(self.host, timeout=self.timeout)
        ftp.login()
        ftp.set_pasv(True)
        ftp.cwd(self.pasta)
        self.ftp = ftp
        return ftp

    def listar(self, prefixo="RD") -> list[str]:
        for k in range(5):
            try:
                return sorted(n.rsplit("/", 1)[-1] for n in self._conectar().nlst() if n.rsplit("/", 1)[-1].upper().startswith(prefixo))
            except Exception:  # noqa: BLE001
                self.ftp = None
                time.sleep(10 * (k + 1))
        raise ErroSIH("não foi possível listar o FTP do DataSUS")

    def baixar(self, nome: str, destino: str):
        ultimo = None
        for k in range(5):
            try:
                with open(destino, "wb") as f:
                    self._conectar().retrbinary(f"RETR {nome}", f.write, blocksize=1 << 20)
                return
            except ftplib.error_perm as e:
                if str(e).startswith("550"):
                    raise ErroSIH(f"{nome}: não existe no FTP") from e
                ultimo = e
            except Exception as e:  # noqa: BLE001
                ultimo = e
            self.ftp = None
            time.sleep(15 * (k + 1))
        raise ErroSIH(f"{nome}: falha no download ({ultimo})")


def descomprimir(dbc: str, dbf: str):
    import pyreaddbc
    pyreaddbc.dbc2dbf(dbc, dbf)


def coletar(ano: int, saida: Path, ufs=None, meses=None, fonte=None, descompactar=descomprimir, log=print) -> dict:
    """Baixa e agrega todos os RD de um ano de competência. Grava sih_{ano}.parquet e o manifesto."""
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    fonte = fonte or FTPDataSUS()
    ufs = ufs or UFS
    meses = meses or list(range(1, 13))
    nomes_reais = {n.upper(): n for n in fonte.listar("RD")}
    alvo = [f"RD{u}{ano % 100:02d}{m:02d}.DBC" for u in ufs for m in meses]
    alvo = [a for a in alvo if a in nomes_reais]
    log(f"SIH {ano}: {len(alvo)} arquivos de {len(ufs)} UFs")
    partes, manifesto = [], {"ano_competencia": ano, "arquivos": {}, "falhas": {}}
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        for k, nome in enumerate(alvo, 1):
            dbc, dbf = os.path.join(tmp, "a.dbc"), os.path.join(tmp, "a.dbf")
            try:
                fonte.baixar(nomes_reais.get(nome, nome), dbc)
                tam = os.path.getsize(dbc)
                descompactar(dbc, dbf)
                df, info = agregar_dbf(dbf)
                info["bytes"] = tam
                partes.append(df)
                manifesto["arquivos"][nome] = info
            except Exception as e:  # noqa: BLE001
                manifesto["falhas"][nome] = str(e)[:200]
                log(f"  falha em {nome}: {e}")
            finally:
                for p in (dbc, dbf):
                    if os.path.exists(p):
                        os.remove(p)
            if k % 25 == 0 or k == len(alvo):
                log(f"  {k}/{len(alvo)} arquivos · {time.time() - t0:.0f} s")
    if partes:
        tudo = pd.concat(partes, ignore_index=True).groupby(["mun6", "data"], as_index=False)[GRUPOS].sum()
    else:
        tudo = pd.DataFrame(columns=["mun6", "data"] + GRUPOS)
    tudo[GRUPOS] = tudo[GRUPOS].astype(np.int32)
    tudo.to_parquet(saida / f"sih_{ano}.parquet", index=False)
    manifesto["internacoes_60_urgencia"] = int(sum(v.get("idosos_urgencia", 0) for v in manifesto["arquivos"].values()))
    manifesto["registros"] = int(sum(v.get("registros", 0) for v in manifesto["arquivos"].values()))
    (saida / f"manifesto_{ano}.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"SIH {ano}: {manifesto['registros']} AIH lidas, {manifesto['internacoes_60_urgencia']} de 60+ em urgência, "
        f"{len(manifesto['falhas'])} falhas")
    return manifesto
