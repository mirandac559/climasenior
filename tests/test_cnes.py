# -*- coding: utf-8 -*-
"""Capacidade de resposta (CNES) com FTP falso e DBF escrito no teste."""
import shutil
import struct
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from climasenior import cnes as CN    # noqa: E402
from climasenior import sih as SIH    # noqa: E402

CAMPOS = [("CNES", 7), ("CODUFMUN", 6), ("TP_UNID", 2), ("VINC_SUS", 1)]


def _dbf(caminho, linhas):
    tam = 1 + sum(t for _, t in CAMPOS)
    cab = struct.pack("<B3BIHH20x", 3, 126, 8, 1, len(linhas), 32 + 32 * len(CAMPOS) + 1, tam)
    desc = b"".join(n.encode().ljust(11, b"\x00") + b"C" + b"\x00" * 4 + bytes([t, 0]) + b"\x00" * 14 for n, t in CAMPOS)
    regs = b"".join(b" " + b"".join(str(l[k]).encode().ljust(t)[:t] for k, (_, t) in enumerate(CAMPOS)) for l in linhas)
    Path(caminho).write_bytes(cab + desc + b"\x0d" + regs + b"\x1a")


def test_competencia_e_contagem(tmp_path):
    nomes = [f"ST{u}2607.dbc" for u in SIH.UFS] + [f"ST{u}2608.dbc" for u in SIH.UFS if u != "SP"] + ["STMA2609.dbc"]
    assert CN.competencia_recente(nomes) == "2607"

    class Fonte:
        def listar(self, p):
            return nomes

        def baixar(self, nome, destino):
            if nome.upper() == "STMA2607.DBC":
                _dbf(destino, [("1", "211130", "02", "1"), ("2", "211130", "01", "1"), ("3", "211130", "05", "1"),
                               ("4", "211130", "02", "0"), ("5", "210005", "32", "1")])
            else:
                _dbf(destino, [])

    m = pd.DataFrame({"cod_ibge": ["2111300", "2100055", "2200400"]})
    cap = CN.coletar(m, fonte=Fonte(), descompactar=shutil.copy, log=lambda *a: None)
    d = cap.set_index("cod_ibge")["estab_atencao_basica"]
    assert d["2111300"] == 2 and d["2100055"] == 1 and d["2200400"] == 0     # hospital (05) e sem SUS ficam fora
    assert (cap["competencia"] == "2026-07").all()
