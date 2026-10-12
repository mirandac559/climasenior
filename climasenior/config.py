# -*- coding: utf-8 -*-
"""Configuração central do ClimaSênior."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_DADOS = RAIZ / "data"
DIR_SITE = RAIZ / "site"
DIR_SITE_DADOS = DIR_SITE / "data"

ANO_INICIO_OPERACIONAL = 2026          # primeiro ano exibido no painel diário
FUSO = "America/Sao_Paulo"             # agregação diária do modelo de previsão (horário de Brasília)
LIMIAR_ACAO = 60                       # IVC a partir do qual o protocolo é acionado (pactuável)

# Composição do IVC (projeto, seção 6): exposição, sensibilidade e capacidade de resposta
PESOS_IVC = {"exposicao": 0.60, "sensibilidade": 0.25, "capacidade": 0.15}

# Região Metropolitana da Grande São Luís (território-piloto). Usada só na simulação de testes,
# para que os nomes do piloto apareçam nos dados fictícios.
MUNICIPIOS_PILOTO = [
    {"nome": "São Luís",             "lat": -2.530, "lon": -44.302},
    {"nome": "São José de Ribamar",  "lat": -2.562, "lon": -44.054},
    {"nome": "Paço do Lumiar",       "lat": -2.532, "lon": -44.108},
    {"nome": "Raposa",               "lat": -2.425, "lon": -44.093},
    {"nome": "Alcântara",            "lat": -2.404, "lon": -44.415},
    {"nome": "Axixá",                "lat": -2.838, "lon": -44.058},
    {"nome": "Bacabeira",            "lat": -2.970, "lon": -44.318},
    {"nome": "Cachoeira Grande",     "lat": -2.931, "lon": -44.053},
    {"nome": "Icatu",                "lat": -2.776, "lon": -44.063},
    {"nome": "Morros",               "lat": -2.858, "lon": -44.042},
    {"nome": "Presidente Juscelino", "lat": -2.919, "lon": -44.070},
    {"nome": "Rosário",              "lat": -2.934, "lon": -44.253},
    {"nome": "Santa Rita",           "lat": -3.143, "lon": -44.331},
]
