# ClimaSênior

Índice de Vulnerabilidade Climática (IVC) para a saúde da população idosa nos **5.570 municípios
do Brasil**, atualizado todos os dias desde 1º de janeiro de 2026. O painel mostra a situação do dia,
a previsão para os próximos dias, a série de cada município e a conduta do protocolo de resposta graduada.

> O presente trabalho foi realizado com apoio do Itaú Viver Mais e Portal do Envelhecimento.

## Como os dados chegam

| O quê | Fonte | Frequência |
|---|---|---|
| Municípios, UF e contornos | IBGE (localidades e malhas) | uma vez |
| Coordenadas das sedes | [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros) (MIT), com geocodificação do Open-Meteo para as que faltarem | uma vez |
| População 60+ e 80+ | IBGE, Censo 2022, tabela 9514 | uma vez |
| Climatologia 2014–2025 | CPC Global Unified Temperature (NOAA), grade de 0,5° | uma vez |
| Temperatura observada de 2026 | CPC (enquanto a NOAA publicar) | diária, se houver novidade |
| Dias recentes e previsão de 7 dias | Open-Meteo (CC BY 4.0) | diária, 06:00 de Brasília |
| Lacunas entre a observação e os dias recentes | Open-Meteo, previsão histórica | a cada 2 horas, até completar |

Cada município usa a célula de 0,5° (cerca de 55 km) que contém a sua sede; municípios vizinhos
na mesma célula compartilham a exposição, e cada um tem a sua sensibilidade. O desvio médio do
modelo de previsão em relação à observação é medido célula a célula e descontado.

O uso gratuito do Open-Meteo tem limite de 10.000 chamadas por dia. O sistema consulta uma vez por
célula (cerca de 2.000) e respeita um teto de 9.500 por dia; o que não couber fica para a execução seguinte.

## O índice

| Componente | Peso | Medida |
|---|---|---|
| Exposição | 60% | Fator de Excesso de Calor (Nairn e Fawcett, 2015): média dos três dias seguintes contra o percentil 95 local e contra os 30 dias anteriores |
| Sensibilidade | 25% | proporção de pessoas com 60+ (70%) e 80+ (30%), relativa ao percentil 99 do país |
| Capacidade de resposta | 15% | estabelecimentos de atenção básica por habitante (CNES), opcional em `data/ref/capacidade.csv` |

Sem o arquivo de capacidade, o peso é redistribuído entre exposição e sensibilidade e o painel avisa.
Faixas: BAIXA (0–39), MODERADA (40–59), ALTA (60–79), MUITO ALTA (80–100). Limiar de ação: 60.

## Rodar

```bash
pip install -r requirements-operacional.txt
python -m climasenior.brasil                    # dados reais (a primeira execução baixa a climatologia)
python -m climasenior.brasil --complemento      # só completa lacunas
python -m http.server 8000 -d site              # painel em http://localhost:8000
```

Teste sem rede, com dados e municípios fictícios: `python -m climasenior.brasil --simular` e
`python -m http.server 8000 -d simulacao_br/site` (copie `site/index.html` para lá).

Testes: `pip install pytest scikit-learn joblib && python -m pytest tests -q`

## Publicação

O fluxo `.github/workflows/atualizar.yml` roda às 06:00 de Brasília e a cada 2 horas para lacunas,
grava a série em `data/clima/AAAA/AAAA-MM-DD.csv` (uma linha por célula) e publica o painel no
GitHub Pages. O registro da última execução fica em `data/log/ultima_execucao.log`.
Alternativa para servidor próprio: `Dockerfile`.

## Estrutura

```
climasenior/brasil.py        operação nacional (orquestração, EHF, IVC, exportação)
climasenior/cpc.py           leitura da CPC (NetCDF)
climasenior/fontes.py        conectores IBGE, Open-Meteo e coordenadas
climasenior/ehf.py           Fator de Excesso de Calor
climasenior/simulacao_br.py  respostas simuladas para testes
site/index.html              painel
climasenior/operacional.py   versão-piloto da RM de São Luís com ERA5 por sede (0.4)
climasenior/modelos.py, backtesting.py, api/, app/   módulos de pesquisa (0.3)
```

## Limites

O índice descreve municípios, não pessoas. A resolução de 0,5° não distingue bairros nem ilhas de
calor urbanas. Na Amazônia a CPC se apoia em poucas estações. Os limiares ainda serão calibrados com
internações e óbitos do DataSUS, que chegam com meses de atraso, e pactuados com os gestores.
