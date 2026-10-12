# -*- coding: utf-8 -*-
"""
Cliente simulado da operação nacional: devolve respostas no mesmo formato do IBGE,
do conjunto de coordenadas, da CPC (arquivos NetCDF) e do Open-Meteo, com valores
sintéticos determinísticos, para testar a esteira sem rede. Municípios e valores são
fictícios; o painel gerado neste modo traz o aviso de simulação e nomes fictícios.
"""
from __future__ import annotations
import hashlib
import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

from . import config as C
from . import fontes as F

UFS_SIM = {  # caixas aproximadas (lat_min, lat_max, lon_min, lon_max) e nº de municípios fictícios
    "MA": (-8.0, -1.8, -47.0, -42.0, 20), "PI": (-10.0, -3.0, -45.0, -41.0, 15),
    "CE": (-7.5, -3.0, -41.0, -37.6, 15), "RN": (-6.5, -5.0, -38.0, -35.2, 8),
}
UF_COD = {"MA": 21, "PI": 22, "CE": 23, "RN": 24}
CPC_FIM_2026 = date(2026, 9, 4)          # a CPC simulada para em 04/09/2026, como a real parou de atualizar


def _ruido(*chave) -> float:
    h = hashlib.sha256("|".join(map(str, chave)).encode()).digest()
    return (int.from_bytes(h[:4], "big") / 2**32) * 2 - 1


def temperatura(lat: float, lon: float, d: date) -> tuple[float, float]:
    doy = d.timetuple().tm_yday
    base = 31.0 + 0.25 * (-lat - 2) + 1.4 * math.sin(2 * math.pi * (doy - 230) / 365.25)
    base -= 0.8 if lon > -40 else 0.0
    onda = 0.0
    for ini, dur, amp, lat0 in [(date(2026, 9, 25), 5, 2.6, -4), (date(2026, 10, 9), 8, 3.4, -6),
                                (date(2025, 10, 15), 6, 2.5, -5), (date(2024, 11, 2), 5, 2.2, -3)]:
        if ini <= d < ini + timedelta(days=dur):
            onda = amp * math.sin(math.pi * ((d - ini).days + .5) / dur) * math.exp(-((lat - lat0) / 3) ** 2)
    tx = base + 0.03 * (d.year - 2014) + onda + 0.8 * _ruido("x", d, round(lat, 1), round(lon, 1))
    return tx, tx - 7.5 + 0.5 * _ruido("n", d, round(lat, 1))


class ClienteSimuladoBrasil:
    simulado = True

    def __init__(self, hoje: date | None = None):
        self.hoje = hoje or datetime.now(timezone(timedelta(hours=-3))).date()
        self.muns = []
        rm = {m["nome"]: m for m in C.MUNICIPIOS_PILOTO}
        k = 0
        for uf, (a, b, c, d, n) in UFS_SIM.items():
            nomes = list(rm) if uf == "MA" else []
            for i in range(n + len(nomes)):
                k += 1
                if i < len(nomes):
                    lat, lon, nome = rm[nomes[i]]["lat"], rm[nomes[i]]["lon"], nomes[i]
                else:
                    lat = a + (b - a) * (0.5 + 0.5 * _ruido("la", uf, i))
                    lon = c + (d - c) * (0.5 + 0.5 * _ruido("lo", uf, i))
                    nome = f"Fictício {uf} {i}"
                self.muns.append({"id": UF_COD[uf] * 100000 + k, "nome": nome, "uf": uf,
                                  "lat": round(lat, 4), "lon": round(lon, 4)})

    # --------------------------------------------------------------- HTTP
    def get_json(self, url, params=None):
        p = params or {}
        if url == F.IBGE_MUNICIPIOS_BR:
            out = []
            for j, m in enumerate(self.muns):
                uf = {"id": UF_COD[m["uf"]], "sigla": m["uf"], "nome": m["uf"]}
                if j % 5 == 0:   # alguns municípios só trazem a UF pela região imediata
                    out.append({"id": m["id"], "nome": m["nome"], "microrregiao": None,
                                "regiao-imediata": {"regiao-intermediaria": {"UF": uf}}})
                else:
                    out.append({"id": m["id"], "nome": m["nome"], "microrregiao": {"mesorregiao": {"UF": uf}}})
            return out
        if url == F.IBGE_AGREGADO_IDADE:
            pedidos = set(p["localidades"][3:-1].split(","))
            muns = [m for m in self.muns if str(m["id"]) in pedidos]
            grupos = ["Total"] + [f"{a} a {a + 4} anos" for a in range(0, 100, 5)] + ["100 anos ou mais"]
            res = []
            for g, rot in enumerate(grupos):
                series = []
                for m in muns:
                    pop = int(8000 + 60000 * (0.5 + 0.5 * _ruido("p", m["id"])))
                    velho = 0.08 + 0.08 * (0.5 + 0.5 * _ruido("v", m["id"]))
                    pesos = np.array([math.exp(-a / 30) for a in range(0, 105, 5)])
                    pesos[12:] *= velho / (pesos[12:].sum() / pesos.sum())
                    pesos /= pesos.sum()
                    v = pop if rot == "Total" else int(round(pesos[g - 1] * pop))
                    series.append({"localidade": {"id": str(m["id"])}, "serie": {"2022": str(v)}})
                res.append({"classificacoes": [{"id": "287", "categoria": {str(g): rot}}], "series": series})
            return [{"id": "93", "resultados": res}]
        if url == F.IBGE_MALHA_BR:
            feats = []
            for uf, (a, b, c, d, _) in UFS_SIM.items():
                feats.append({"type": "Feature", "properties": {"codarea": str(UF_COD[uf])},
                              "geometry": {"type": "Polygon", "coordinates": [[[c, a], [d, a], [d, b], [c, b], [c, a]]]}})
            return {"type": "FeatureCollection", "features": feats}
        if url == F.OPEN_METEO_GEOCODIFICACAO:
            m = next((x for x in self.muns if x["nome"] == p["name"]), None)
            from .brasil import UF_NOME
            return {"results": [{"name": m["nome"], "admin1": UF_NOME[m["uf"]], "latitude": m["lat"],
                                 "longitude": m["lon"]}]} if m else {}
        if url in (F.OPEN_METEO_PREVISAO, F.OPEN_METEO_HISTORICO):
            return self._clima(url, p)
        raise F.ErroFonte(f"Simulação: URL não prevista {url}")

    def get_text(self, url):
        assert url == F.COORDENADAS_MUNICIPIOS
        linhas = ["codigo_ibge,nome,latitude,longitude,capital,codigo_uf,siafi_id,ddd,fuso_horario"]
        for j, m in enumerate(self.muns):
            if j == 7:      # um município ausente do conjunto de coordenadas
                continue
            linhas.append(f"{m['id']},{m['nome']},{m['lat']},{m['lon']},0,{UF_COD[m['uf']]},0,98,America/Fortaleza")
        return "\n".join(linhas)

    def ultima_modificacao(self, url):
        return "Sat, 05 Sep 2026 09:40:00 GMT" if "2026" in url else "Thu, 02 Jan 2025 09:30:00 GMT"

    # --------------------------------------------------------------- CPC (NetCDF)
    def baixar(self, url, destino):
        import netCDF4
        var, ano = url.rsplit("/", 1)[1].split(".")[:2]
        ano = int(ano)
        d0 = date(ano, 1, 1)
        d1 = min(date(ano, 12, 31), CPC_FIM_2026 if ano == 2026 else date(ano, 12, 31), self.hoje - timedelta(days=2))
        if d1 < d0:
            raise F.ErroFonte(f"Simulação: CPC {ano} ainda não existe")
        dias = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
        lats = np.arange(-0.25, -12.0, -0.5)
        lons = np.arange(360 - 49.75, 360 - 33.0, 0.5)
        arr = np.full((len(dias), len(lats), len(lons)), np.nan, dtype="float32")
        for i, la in enumerate(lats):
            for j, lo in enumerate(lons):
                lo180 = lo - 360
                if lo180 > -35.0 or (la > -2.4 and lo180 > -44.0):   # "oceano": sem dado
                    continue
                for k, d in enumerate(dias):
                    tx, tn = temperatura(la, lo180, d)
                    arr[k, i, j] = tx if var == "tmax" else tn
        with netCDF4.Dataset(destino, "w") as nc:
            nc.createDimension("time", None)
            nc.createDimension("lat", len(lats))
            nc.createDimension("lon", len(lons))
            t = nc.createVariable("time", "f8", ("time",))
            t.units = "hours since 1900-01-01 00:00:00"
            t[:] = [(datetime(d.year, d.month, d.day) - datetime(1900, 1, 1)).total_seconds() / 3600 for d in dias]
            nc.createVariable("lat", "f4", ("lat",))[:] = lats
            nc.createVariable("lon", "f4", ("lon",))[:] = lons
            v = nc.createVariable(var, "f4", ("time", "lat", "lon"), fill_value=-9.96921e36)
            v[:] = np.ma.masked_invalid(arr)

    # --------------------------------------------------------------- Open-Meteo
    def _clima(self, url, p):
        lats = [float(x) for x in p["latitude"].split(",")]
        lons = [float(x) for x in p["longitude"].split(",")]
        if url == F.OPEN_METEO_HISTORICO:
            d0, d1 = date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"])
        else:
            d0 = self.hoje - timedelta(days=int(p["past_days"]))
            d1 = self.hoje + timedelta(days=int(p["forecast_days"]) - 1)
        dias = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
        objs = []
        for la, lo in zip(lats, lons):
            tx, tn = zip(*[temperatura(la, lo, d) for d in dias])
            objs.append({"latitude": la, "longitude": lo, "daily": {
                "time": [d.isoformat() for d in dias],
                "temperature_2m_max": [round(x + 0.5, 1) for x in tx],     # modelo 0,5 °C mais quente
                "temperature_2m_min": [round(x - 0.3, 1) for x in tn],
                "apparent_temperature_max": [round(x + 4.0, 1) for x in tx]}})
        return objs[0] if len(objs) == 1 else objs
