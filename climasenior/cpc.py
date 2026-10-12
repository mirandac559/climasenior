# -*- coding: utf-8 -*-
"""
Leitura da CPC Global Unified Temperature (NOAA PSL): temperatura máxima e mínima
diárias observadas, grade de 0,5°, 1979 em diante, um arquivo NetCDF por ano e
variável (tmax.AAAA.nc, tmin.AAAA.nc). https://psl.noaa.gov/data/gridded/data.cpc.globaltemp.html

Usada para a climatologia de referência de todo o país (2014-2025) e para os dias
de 2026 já disponíveis. Só a região do Brasil é guardada.
"""
from __future__ import annotations
import os
import tempfile
from datetime import date, timedelta

import numpy as np

# Caixa que contém o território brasileiro (com folga de meio grau)
LAT_MIN, LAT_MAX = -34.25, 5.75
LON_MIN, LON_MAX = -74.25, -32.25


def ler_recorte(caminho: str, var: str):
    """Devolve (datas, lats, lons, matriz[dia, lat, lon]) com NaN onde não há dado."""
    import netCDF4
    with netCDF4.Dataset(caminho) as nc:
        lat = np.asarray(nc.variables["lat"][:], dtype=float)
        lon = np.asarray(nc.variables["lon"][:], dtype=float)
        lon180 = np.where(lon > 180, lon - 360, lon)
        il = np.where((lat >= LAT_MIN) & (lat <= LAT_MAX))[0]
        jl = np.where((lon180 >= LON_MIN) & (lon180 <= LON_MAX))[0]
        t = nc.variables["time"]
        datas = [date(d.year, d.month, d.day) for d in
                 netCDF4.num2date(t[:], t.units, getattr(t, "calendar", "standard"))]
        bruto = nc.variables[var][:, il.min():il.max() + 1, jl.min():jl.max() + 1]
        arr = np.ma.filled(np.ma.masked_invalid(bruto).astype("float32"), np.nan)
    arr[(arr < -60) | (arr > 60)] = np.nan
    return datas, lat[il.min():il.max() + 1], lon180[jl.min():jl.max() + 1], arr


def baixar_e_ler(cliente, ano: int, var: str, log=None):
    url = cliente_url(ano, var)
    with tempfile.TemporaryDirectory() as tmp:
        destino = os.path.join(tmp, f"{var}.{ano}.nc")
        if log:
            log(f"    CPC {var} {ano}")
        cliente.baixar(url, destino)
        return ler_recorte(destino, var)


def cliente_url(ano: int, var: str) -> str:
    from .fontes import CPC_ARQUIVO
    return CPC_ARQUIVO.format(var=var, ano=ano)


def celula_id(lat: float, lon: float) -> str:
    return f"{lat:.2f}_{lon:.2f}"


def atribuir_celulas(lats, lons, valido: np.ndarray, pontos: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """
    Para cada sede (lat, lon), o índice (i, j) da célula válida mais próxima.
    Sedes no litoral costumam cair em células sem dado (a CPC cobre só o continente);
    nesses casos procura a célula válida mais próxima num raio crescente.
    """
    lats, lons = np.asarray(lats), np.asarray(lons)
    vi, vj = np.where(valido)
    vlat, vlon = lats[vi], lons[vj]
    out = []
    for la, lo in pontos:
        d2 = (vlat - la) ** 2 + ((vlon - lo) * np.cos(np.radians(la))) ** 2
        k = int(np.argmin(d2))
        out.append((int(vi[k]), int(vj[k])))
    return out


def dias_do_ano(ano: int) -> list[date]:
    d0 = date(ano, 1, 1)
    return [d0 + timedelta(days=i) for i in range((date(ano + 1, 1, 1) - d0).days)]
