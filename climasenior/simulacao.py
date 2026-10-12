# -*- coding: utf-8 -*-
"""
Cliente simulado: devolve respostas no MESMO FORMATO das APIs do Open-Meteo e
do IBGE, com valores sintéticos determinísticos. Serve para testar a operação
de ponta a ponta sem rede. Os códigos de município (99000xx) e todos os valores
são fictícios; o painel gerado neste modo exibe o aviso de simulação.
"""
from __future__ import annotations
import hashlib
import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

from . import config as C
from . import fontes as F


def _ruido(*chave) -> float:
    h = hashlib.sha256("|".join(map(str, chave)).encode()).digest()
    return (int.from_bytes(h[:4], "big") / 2**32) * 2 - 1      # [-1, 1)


class ClienteSimulado:
    def __init__(self, hoje: date | None = None):
        self.hoje = hoje or datetime.now(timezone(timedelta(hours=-3))).date()
        self._cod = {m["nome"]: str(9900001 + i) for i, m in enumerate(C.MUNICIPIOS_OPERACIONAIS)}

    # ------------------------------------------------------------- roteamento
    def get_json(self, url: str, params: dict | None = None):
        p = params or {}
        if url.startswith(F.IBGE_MUNICIPIOS_UF.split("{")[0]):
            return [{"id": int(c), "nome": n} for n, c in self._cod.items()] + [{"id": 9909999, "nome": "Outro Município"}]
        if url == F.IBGE_AGREGADO_IDADE:
            return self._censo(p)
        if url == F.OPEN_METEO_GEOCODIFICACAO:
            m = next(x for x in C.MUNICIPIOS_OPERACIONAIS if x["nome"] == p["name"])
            return {"results": [{"name": m["nome"], "admin1": "Maranhão", "country_code": "BR",
                                 "latitude": m["lat"] + 0.01, "longitude": m["lon"] - 0.01}]}
        if url in (F.OPEN_METEO_ARQUIVO, F.OPEN_METEO_PREVISAO):
            return self._clima(url, p)
        raise F.ErroFonte(f"Simulação: URL não prevista {url}")

    # ------------------------------------------------------------- IBGE
    def _censo(self, p):
        cods = p["localidades"][3:-1].split(",")
        grupos = [f"{a} a {a + 4} anos" for a in range(0, 100, 5)] + ["100 anos ou mais"]
        resultados = []
        base = {}
        for cod in cods:
            i = int(cod) - 9900001
            pop = 1_037_000 if i == 0 else int(20_000 + 15_000 * (1 + _ruido("pop", cod)))
            velho = 0.09 + 0.05 * (1 + _ruido("idade", cod)) / 2          # 9% a 14% com 60+
            pesos = np.array([math.exp(-a / 32) for a in range(0, 105, 5)])
            pesos[12:] *= velho / (pesos[12:].sum() / pesos.sum())
            pesos /= pesos.sum()
            base[cod] = (pop, (pesos * pop).round().astype(int))
        for k, rot in enumerate(["Total"] + grupos + ["60 anos", "61 anos"]):
            series = []
            for cod in cods:
                pop, v = base[cod]
                val = pop if rot == "Total" else (int(v[k - 1]) if k <= len(grupos) else 1234)
                series.append({"localidade": {"id": cod, "nome": cod}, "serie": {"2022": str(val)}})
            resultados.append({"classificacoes": [
                {"id": "2", "nome": "Sexo", "categoria": {"6794": "Total"}},
                {"id": "287", "nome": "Idade", "categoria": {str(1000 + k): rot}}], "series": series})
        return [{"id": "93", "variavel": "População residente", "resultados": resultados}]

    # ------------------------------------------------------------- clima
    def _tmax(self, d: date, lat: float, lon: float) -> float:
        doy = d.timetuple().tm_yday
        sazonal = 31.4 + 1.6 * math.sin(2 * math.pi * (doy - 230) / 365.25)  # pico entre out e dez
        litoral = -0.6 if lon < -44.2 and lat > -2.6 else 0.0
        tendencia = 0.05 * (d.year - 2014)
        onda = 0.0
        for ini, dur, amp in [(date(2026, 9, 18), 5, 2.4), (date(2026, 10, 9), 7, 3.2),
                              (date(2026, 11, 20), 4, 2.0), (date(2027, 1, 3), 4, 1.8)]:
            if ini <= d < ini + timedelta(days=dur):
                onda = amp * math.sin(math.pi * ((d - ini).days + 0.5) / dur)
        return sazonal + litoral + tendencia + onda + 0.9 * _ruido("tx", d, round(lat, 2))

    def _clima(self, url, p):
        lats = [float(x) for x in p["latitude"].split(",")]
        lons = [float(x) for x in p["longitude"].split(",")]
        if url == F.OPEN_METEO_ARQUIVO:
            d0, d1 = date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"])
            limite = self.hoje - timedelta(days=5)
            if d1 > limite:
                d1 = limite
            vies = 0.0
        else:
            d0 = self.hoje - timedelta(days=int(p["past_days"]))
            d1 = self.hoje + timedelta(days=int(p["forecast_days"]) - 1)
            vies = 0.4                                   # o modelo é um pouco mais quente que o ERA5
        dias = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
        objs = []
        for lat, lon in zip(lats, lons):
            tx = [round(self._tmax(d, lat, lon) + vies, 1) for d in dias]
            tn = [round(t - 7.2 + 0.6 * _ruido("tn", d, lat), 1) for t, d in zip(tx, dias)]
            ta = [round(t + 3.5 + 0.8 * _ruido("ta", d, lat), 1) for t, d in zip(tx, dias)]
            objs.append({"latitude": lat, "longitude": lon, "timezone": p.get("timezone"),
                         "daily_units": {"time": "iso8601", "temperature_2m_max": "°C"},
                         "daily": {"time": [d.isoformat() for d in dias], "temperature_2m_max": tx,
                                   "temperature_2m_min": tn, "apparent_temperature_max": ta}})
        return objs[0] if len(objs) == 1 else objs
