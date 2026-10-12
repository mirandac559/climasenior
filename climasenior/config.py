# -*- coding: utf-8 -*-
"""Configuração central do ClimaSênior."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_DADOS = RAIZ / "data"
DIR_DEMO = DIR_DADOS / "demo"
DIR_REAL = DIR_DADOS / "real"
DIR_MODELOS = RAIZ / "modelos"
DIR_MODELOS.mkdir(exist_ok=True)

# Janela histórica e divisão temporal (sem vazamento entre períodos)
ANO_INICIO = 2014
ANO_FIM = 2025
TREINO_ATE = "2022-12-31"
VALIDACAO_DE, VALIDACAO_ATE = "2023-01-01", "2024-12-31"
TESTE_DE = "2025-01-01"

# Horizonte preditivo (dias) e limiar térmico local de referência (°C)
HORIZONTE_DIAS = 3
LIMIAR_TERMICO_LOCAL = 33.0

# Faixas do IVC (0-100) e protocolo de resposta graduada
FAIXAS_IVC = [
    (0,  40, "BAIXA",      "#7FB539", "Monitoramento de rotina; ações educativas permanentes"),
    (40, 60, "MODERADA",   "#EAB126", "Comunicação preventiva a idosos e cuidadores; checagem de insumos de hidratação"),
    (60, 80, "ALTA",       "#E07B2A", "Reforço de equipes na atenção básica; busca ativa de idosos em isolamento; articulação com assistência social e defesa civil"),
    (80, 101, "MUITO ALTA", "#CF3F38", "Ativação de pontos de apoio com hidratação e climatização; contato dirigido a idosos com comorbidades; preparação de retaguarda hospitalar"),
]

# Pesos da composição do IVC (pactuáveis com gestores na Fase 3)
PESO_EXPOSICAO = 0.60
PESO_SENSIBILIDADE = 0.25
PESO_CAPACIDADE = 0.15

# Território-piloto: Região Metropolitana de São Luís (MA)
# lat/lon aproximados das sedes; prop_idosos e capacidade são valores de DEMONSTRAÇÃO
# a serem substituídos pelos dados reais do IBGE (Censo 2022) e CNES.
MUNICIPIOS_RM = {
    "2111300": dict(nome="São Luís",             lat=-2.530, lon=-44.302, prop_idosos=0.118, prev_comorb=0.58, cap_resposta=0.72),
    "2111201": dict(nome="São José de Ribamar",  lat=-2.562, lon=-44.054, prop_idosos=0.094, prev_comorb=0.55, cap_resposta=0.55),
    "2107506": dict(nome="Paço do Lumiar",       lat=-2.516, lon=-44.106, prop_idosos=0.089, prev_comorb=0.54, cap_resposta=0.52),
    "2109452": dict(nome="Raposa",               lat=-2.425, lon=-44.093, prop_idosos=0.078, prev_comorb=0.53, cap_resposta=0.40),
    "2100501": dict(nome="Alcântara",            lat=-2.404, lon=-44.415, prop_idosos=0.132, prev_comorb=0.60, cap_resposta=0.35),
    "2101202": dict(nome="Axixá",                lat=-2.838, lon=-44.058, prop_idosos=0.112, prev_comorb=0.57, cap_resposta=0.38),
    "2101350": dict(nome="Bacabeira",            lat=-2.970, lon=-44.318, prop_idosos=0.095, prev_comorb=0.55, cap_resposta=0.42),
    "2102309": dict(nome="Cachoeira Grande",     lat=-2.931, lon=-44.053, prop_idosos=0.108, prev_comorb=0.56, cap_resposta=0.33),
    "2105005": dict(nome="Icatu",                lat=-2.776, lon=-44.063, prop_idosos=0.114, prev_comorb=0.58, cap_resposta=0.36),
    "2107100": dict(nome="Morros",               lat=-2.858, lon=-44.042, prop_idosos=0.117, prev_comorb=0.57, cap_resposta=0.37),
    "2109106": dict(nome="Presidente Juscelino", lat=-2.919, lon=-44.070, prop_idosos=0.121, prev_comorb=0.59, cap_resposta=0.34),
    "2109700": dict(nome="Rosário",              lat=-2.934, lon=-44.253, prop_idosos=0.103, prev_comorb=0.56, cap_resposta=0.45),
    "2110302": dict(nome="Santa Rita",           lat=-3.143, lon=-44.331, prop_idosos=0.099, prev_comorb=0.55, cap_resposta=0.41),
}


def faixa_ivc(valor: float):
    """Retorna (rotulo, cor, conduta) para um valor do IVC."""
    for ini, fim, rot, cor, conduta in FAIXAS_IVC:
        if ini <= valor < fim:
            return rot, cor, conduta
    return FAIXAS_IVC[-1][2], FAIXAS_IVC[-1][3], FAIXAS_IVC[-1][4]


# ======================================================================
# OPERAÇÃO EM TEMPO REAL (v0.4) — dados reais de 2026 em diante
# ======================================================================
# Os valores de MUNICIPIOS_RM acima são de DEMONSTRAÇÃO (v0.3) e NÃO são
# usados pela operação real. A operação usa a lista abaixo; os códigos IBGE
# são resolvidos na API de localidades do IBGE na primeira execução e os
# indicadores demográficos vêm do Censo 2022 (tabela 9514).

ANO_INICIO_OPERACIONAL = 2026          # primeiro ano exibido na plataforma
CLIMATOLOGIA_INICIO = "2014-01-01"     # período de referência (ERA5), o mesmo da série do projeto
CLIMATOLOGIA_FIM = "2025-12-31"
FUSO = "America/Fortaleza"             # São Luís: UTC-3, sem horário de verão
DIAS_PREVISAO = 16                     # horizonte máximo do modelo de previsão
DIAS_PASSADOS_MODELO = 31              # janela recente do modelo (usada para corrigir viés frente ao ERA5)
DEFASAGEM_ERA5 = 6                     # dias até a reanálise ERA5 ficar disponível
LIMIAR_ACAO = 60                       # IVC a partir do qual o protocolo é acionado (pactuável)
HORIZONTE_ALERTA = 3                   # dias à frente considerados no alerta (D+0 a D+3)

PESOS_IVC = {"exposicao": 0.60, "sensibilidade": 0.25, "capacidade": 0.15}

# Região Metropolitana da Grande São Luís (13 municípios). Coordenadas
# aproximadas das sedes municipais; a grade dos modelos tem 9 a 25 km.
MUNICIPIOS_OPERACIONAIS = [
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

DIR_REF = DIR_DADOS / "ref"
DIR_SERIE = DIR_DADOS / "serie"
DIR_SITE = RAIZ / "site"
DIR_SITE_DADOS = DIR_SITE / "data"
