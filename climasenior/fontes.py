# -*- coding: utf-8 -*-
"""
Conectores às fontes públicas usadas pela operação em tempo real.

  * Open-Meteo  — previsão (16 dias) e janela recente do modelo; reanálise ERA5
                  (arquivo histórico) para a climatologia e para os dias já
                  consolidados. Licença CC BY 4.0; uso não comercial sem chave.
                  https://open-meteo.com/en/docs
  * IBGE        — API de localidades (códigos dos municípios) e API de agregados
                  (Censo 2022, tabela 9514: população por idade).
                  https://servicodados.ibge.gov.br/api/docs

Todo acesso à rede passa por um "cliente" com o método get_json(url, params).
Na operação usa-se ClienteHTTP; nos testes e na simulação, um cliente falso
que devolve respostas no mesmo formato. Assim a lógica é testada sem rede.
"""
from __future__ import annotations
import re
import time
import unicodedata
from typing import Iterable

import pandas as pd

OPEN_METEO_PREVISAO = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARQUIVO = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_GEOCODIFICACAO = "https://geocoding-api.open-meteo.com/v1/search"
IBGE_MUNICIPIOS_UF = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
IBGE_AGREGADO_IDADE = ("https://servicodados.ibge.gov.br/api/v3/agregados/9514/periodos/2022/"
                       "variaveis/93")

VARIAVEIS_DIARIAS = ["temperature_2m_max", "temperature_2m_min", "apparent_temperature_max"]


class ErroFonte(RuntimeError):
    """Falha ao obter ou interpretar dados de uma fonte externa."""


class ClienteHTTP:
    """Cliente real, com tentativas e espera progressiva."""

    def __init__(self, tentativas: int = 4, espera: float = 2.0, timeout: int = 60):
        import requests
        self._s = requests.Session()
        self._s.headers["User-Agent"] = "ClimaSenior/0.4 (pesquisa em saude publica; Itau Viver Mais/Portal do Envelhecimento)"
        self.tentativas, self.espera, self.timeout = tentativas, espera, timeout

    def get_json(self, url: str, params: dict | None = None):
        ultimo = None
        for n in range(self.tentativas):
            try:
                r = self._s.get(url, params=params, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    raise ErroFonte(f"HTTP {r.status_code} em {url}")
                r.raise_for_status()
                return r.json()
            except Exception as e:  # noqa: BLE001 - rede é imprevisível; tenta de novo
                ultimo = e
                time.sleep(self.espera * (2 ** n))
        raise ErroFonte(f"Falha após {self.tentativas} tentativas: {url} ({ultimo})")


# ----------------------------------------------------------------------------
# Open-Meteo
# ----------------------------------------------------------------------------
def _lista(resp) -> list:
    """Uma localidade -> objeto; várias -> lista. Normaliza para lista."""
    if isinstance(resp, dict):
        if resp.get("error"):
            raise ErroFonte(f"Open-Meteo: {resp.get('reason')}")
        return [resp]
    return list(resp)


def _diario_para_df(obj: dict, chave: str) -> pd.DataFrame:
    d = obj.get("daily")
    if not d or "time" not in d:
        raise ErroFonte("Resposta do Open-Meteo sem bloco 'daily'")
    df = pd.DataFrame({"data": pd.to_datetime(d["time"])})
    for v in VARIAVEIS_DIARIAS:
        # com um modelo explícito a chave pode vir com sufixo (ex.: temperature_2m_max_era5)
        chave_v = v if v in d else next((k for k in d if k.startswith(v + "_")), None)
        df[v] = pd.to_numeric(pd.Series(d[chave_v] if chave_v else [None] * len(df)), errors="coerce")
    df.insert(0, "chave", chave)
    return df.rename(columns={"temperature_2m_max": "tmax", "temperature_2m_min": "tmin",
                              "apparent_temperature_max": "tapmax"})


def _parametros_base(locais: list[dict], fuso: str) -> dict:
    return {"latitude": ",".join(f"{m['lat']:.4f}" for m in locais),
            "longitude": ",".join(f"{m['lon']:.4f}" for m in locais),
            "daily": ",".join(VARIAVEIS_DIARIAS), "timezone": fuso}


MODELO_REANALISE = "era5"   # ERA5 puro: sem ele, o arquivo completa os dias recentes com o modelo operacional


def baixar_reanalise(cliente, locais: list[dict], inicio: str, fim: str, fuso: str) -> pd.DataFrame:
    """ERA5 (arquivo histórico do Open-Meteo) para várias localidades. Dias ainda sem ERA5 vêm nulos."""
    p = _parametros_base(locais, fuso) | {"start_date": inicio, "end_date": fim, "models": MODELO_REANALISE}
    objs = _lista(cliente.get_json(OPEN_METEO_ARQUIVO, p))
    if len(objs) != len(locais):
        raise ErroFonte(f"ERA5: esperadas {len(locais)} localidades, recebidas {len(objs)}")
    return pd.concat([_diario_para_df(o, m["cod_ibge"]) for o, m in zip(objs, locais)],
                     ignore_index=True)


def baixar_previsao(cliente, locais: list[dict], dias_passados: int, dias_previsao: int,
                    fuso: str) -> pd.DataFrame:
    """Modelo de previsão: janela recente (dias_passados) + previsão (dias_previsao)."""
    p = _parametros_base(locais, fuso) | {"past_days": dias_passados, "forecast_days": dias_previsao}
    objs = _lista(cliente.get_json(OPEN_METEO_PREVISAO, p))
    if len(objs) != len(locais):
        raise ErroFonte(f"Previsão: esperadas {len(locais)} localidades, recebidas {len(objs)}")
    return pd.concat([_diario_para_df(o, m["cod_ibge"]) for o, m in zip(objs, locais)],
                     ignore_index=True)


def geocodificar(cliente, nome: str, uf_nome: str = "Maranhão") -> tuple[float, float] | None:
    """Coordenadas da sede pelo serviço de geocodificação do Open-Meteo (auditoria)."""
    r = cliente.get_json(OPEN_METEO_GEOCODIFICACAO,
                         {"name": nome, "count": 10, "language": "pt", "countryCode": "BR"})
    for res in (r or {}).get("results", []) or []:
        if _norm(res.get("admin1", "")) == _norm(uf_nome) and _norm(res.get("name", "")) == _norm(nome):
            return float(res["latitude"]), float(res["longitude"])
    return None


# ----------------------------------------------------------------------------
# IBGE
# ----------------------------------------------------------------------------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def resolver_codigos(cliente, nomes: Iterable[str], uf: int = 21) -> dict[str, str]:
    """Nome -> código IBGE de 7 dígitos, pela API de localidades (UF 21 = Maranhão)."""
    lista = cliente.get_json(IBGE_MUNICIPIOS_UF.format(uf=uf))
    por_nome = {_norm(m["nome"]): str(m["id"]) for m in lista}
    saida, faltam = {}, []
    for n in nomes:
        c = por_nome.get(_norm(n))
        (saida.__setitem__(n, c) if c else faltam.append(n))
    if faltam:
        raise ErroFonte(f"IBGE: municípios não encontrados: {faltam}")
    return saida


_FAIXA = re.compile(r"^(\d+) a (\d+) anos$")
_MAIS = re.compile(r"^(\d+) anos ou mais$")


def populacao_por_idade(cliente, codigos: list[str]) -> pd.DataFrame:
    """
    Censo 2022 (tabela 9514): população total, 60+ e 80+ por município.
    Usa os rótulos das categorias de idade (não os códigos), somando grupos
    quinquenais quando a categoria agregada não existir; confere a soma.
    """
    p = {"localidades": f"N6[{','.join(codigos)}]", "classificacao": "287[all]"}
    resp = cliente.get_json(IBGE_AGREGADO_IDADE, p)
    linhas = []  # (cod, rotulo, valor)
    for var in resp:
        for res in var.get("resultados", []):
            rotulo = None
            for cl in res.get("classificacoes", []):
                cat = list(cl.get("categoria", {}).values())
                if str(cl.get("id")) == "287" and cat:
                    rotulo = cat[0].strip()
                elif cat and _norm(cat[0]) != "total":
                    rotulo = None  # recorte que não é o total (ex.: só homens): ignora
                    break
            if rotulo is None:
                continue
            for s in res.get("series", []):
                v = list(s.get("serie", {}).values())[0]
                if v not in (None, "", "-", "..."):
                    linhas.append((str(s["localidade"]["id"]), rotulo, float(v)))
    if not linhas:
        raise ErroFonte("IBGE: resposta da tabela 9514 sem séries utilizáveis")
    df = pd.DataFrame(linhas, columns=["cod_ibge", "rotulo", "valor"])

    def _somar(g: pd.DataFrame, a_partir: int) -> float:
        r = dict(zip(g["rotulo"], g["valor"]))
        if f"{a_partir} anos ou mais" in r:
            return r[f"{a_partir} anos ou mais"]
        tot = 0.0
        for rot, v in r.items():
            m = _FAIXA.match(rot)
            if m and int(m.group(2)) - int(m.group(1)) == 4 and int(m.group(1)) >= a_partir:
                tot += v
            m2 = _MAIS.match(rot)
            if m2 and int(m2.group(1)) >= 100:
                tot += v
        return tot

    saida = []
    for cod, g in df.groupby("cod_ibge"):
        total = g.loc[g["rotulo"].map(_norm) == "total", "valor"]
        if total.empty:
            raise ErroFonte(f"IBGE: sem total para {cod}")
        total = float(total.iloc[0])
        p60, p80 = _somar(g, 60), _somar(g, 80)
        prop60 = p60 / total
        if not 0.03 < prop60 < 0.40 or p80 > p60:
            raise ErroFonte(f"IBGE: proporções implausíveis para {cod} (60+={prop60:.3f})")
        saida.append({"cod_ibge": cod, "populacao": int(total), "pop60": int(p60),
                      "pop80": int(p80), "prop60": round(prop60, 4), "prop80": round(p80 / total, 4)})
    return pd.DataFrame(saida)
