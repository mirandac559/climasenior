# Guia de implementação — conexão às bases reais

> **Versão 0.4:** a operação diária com dados reais (Open-Meteo/ERA5 e IBGE) é automática e não
> depende das exportações manuais abaixo. Veja o README. Este guia continua válido para a calibração
> com dados de saúde do DataSUS (SIH e SIM), que entram como arquivos.


## 1. INMET / BDMEP (exposição)
1. Acesse https://bdmep.inmet.gov.br/ e selecione a estação **São Luís (A203)**
2. Dados diários, período 01/01/2014 a 31/12/2025, variáveis: temperatura máxima e mínima,
   umidade relativa média, precipitação
3. Salve como `data/real/bdmep_sao_luis.csv` (layout padrão do BDMEP, separador `;`)
4. Para municípios sem estação, use a reanálise ERA5 (Copernicus CDS) e salve um CSV por
   município com as mesmas colunas; o módulo `ingestao.py` aceita ambos

## 2. DataSUS / TabNet (sensibilidade e desfechos)
- **SIH/SUS** — internações por local de residência, faixa etária 60+, CID-10 capítulos I (circulatório)
  e J (respiratório), por dia de internação, 2014–2025 → `data/real/tabnet_atend_idosos.csv`
- **SIM** — óbitos 60+, mesmos capítulos, por dia → `data/real/tabnet_obitos_idosos.csv`
- Exporte em CSV com separador `;`. Os dados são agregados e não contêm identificação individual.

## 3. IBGE / SIDRA (estrutura etária)
- Censo 2022, tabela de população por grupos de idade e município → proporção de 60+
- Salve `data/real/sidra_rm_sao_luis.csv` com colunas `cod_ibge;municipio;prop_idosos;densidade`

## 4. CNES (capacidade de resposta)
- Estabelecimentos e leitos por município; cobertura da atenção básica (e-Gestor AB)
- Atualize `cap_resposta` em `climasenior/config.py` (0 a 1, normalizado pela RM)

## 5. Prevalência de comorbidades
- VIGITEL (capitais) ou PNS 2019 para a proporção de 60+ com hipertensão/diabetes;
  atualize `prev_comorb` em `config.py`

## 6. Calibração do limiar térmico local
Após carregar os dados reais, estime o limiar de menor mortalidade (MMT) com modelo de
defasagem distribuída (DLNM) e ajuste `LIMIAR_TERMICO_LOCAL` em `config.py`.

## 7. Versionamento e retreinamento
Cada execução do pipeline salva `modelos/climasenior_<versao>.joblib` e o resumo JSON.
Retreine ao início de cada estação quente ou quando o monitor de deriva sinalizar PSI > 0,2.
