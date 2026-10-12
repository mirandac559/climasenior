# -*- coding: utf-8 -*-
"""Capacidade de resposta (cobertura da atenção primária, CNES) com FTP falso e DBF escrito no teste."""
import shutil
import struct
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from climasenior import brasil as B   # noqa: E402
from climasenior import cnes as CN    # noqa: E402
from climasenior import sih as SIH    # noqa: E402

CAMPOS = [("CNES", 7), ("CODUFMUN", 6), ("IDEQUIPE", 10), ("TIPO_EQP", 2), ("DT_DESAT", 6)]


def _dbf(caminho, linhas):
    tam = 1 + sum(t for _, t in CAMPOS)
    cab = struct.pack("<B3BIHH20x", 3, 126, 8, 1, len(linhas), 32 + 32 * len(CAMPOS) + 1, tam)
    desc = b"".join(n.encode().ljust(11, b"\x00") + b"C" + b"\x00" * 4 + bytes([t, 0]) + b"\x00" * 14 for n, t in CAMPOS)
    regs = b"".join(b" " + b"".join(str(l[k]).encode().ljust(t)[:t] for k, (_, t) in enumerate(CAMPOS)) for l in linhas)
    Path(caminho).write_bytes(cab + desc + b"\x0d" + regs + b"\x1a")


def test_cobertura_da_atencao_primaria(tmp_path):
    nomes = [f"EP{u}2607.dbc" for u in SIH.UFS] + [f"EP{u}2608.dbc" for u in SIH.UFS if u != "SP"]
    assert CN.competencia_recente(nomes) == "2607"

    class Fonte:
        def listar(self, p):
            return nomes

        def baixar(self, nome, destino):
            if nome.upper() == "EPMA2607.DBC":
                _dbf(destino, [("1", "211130", "A1", "70", "900001"), ("1", "211130", "A1", "70", "900001"),  # repetida
                               ("2", "211130", "A2", "70", "900001"), ("3", "211130", "A3", "76", "900001"),
                               ("4", "211130", "A4", "70", "202501"),                                          # desativada
                               ("5", "211130", "A5", "71", "900001"),                                          # saúde bucal
                               ("6", "210005", "B1", "70", "900001")])
            else:
                _dbf(destino, [])

    m = pd.DataFrame({"cod_ibge": ["2111300", "2100055", "2200400"], "populacao": [10_000, 2_000, 5_000]})
    cap = CN.coletar(m, fonte=Fonte(), descompactar=shutil.copy, log=lambda *a: None).set_index("cod_ibge")
    assert cap.loc["2111300", "equipes_esf"] == 2 and cap.loc["2111300", "equipes_eap"] == 1
    assert cap.loc["2111300", "cobertura_aps"] == (2 * 3450 + 3000) / 10_000
    assert cap.loc["2100055", "cobertura_aps"] == 1.0 and cap.loc["2200400", "cobertura_aps"] == 0.0
    assert (cap["competencia"] == "2026-07").all()
    # no IVC: 1 - (pessoas acompanháveis por habitante, sem teto) / percentil 99 do país
    P = B.Pastas(tmp_path / "d", tmp_path / "s")
    cap.reset_index().to_csv(P.ref / "capacidade.csv", sep=";", index=False)
    razao = np.array([0.99, 3450 / 2000, 0.0])
    assert np.allclose(B.capacidade(m, P), 1 - np.clip(razao / np.percentile(razao, 99), 0, 1))
    w, _ = B.pesos_ivc(m, P)
    assert w == {"exposicao": 0.60, "sensibilidade": 0.25, "capacidade": 0.15}
