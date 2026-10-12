# Metodologia

Este documento descreve como o ClimaSênior calcula o Índice de Vulnerabilidade Climática (IVC),
como o valida com internações reais e como estima a demanda assistencial. Os números atualizados
de cada etapa aparecem no próprio painel (aba Validação) e em `data/validacao/resultados.json`.

## 1. Unidades e período

- **Município** (5.571, IBGE) é a unidade do índice. Cada município tem sensibilidade e capacidade
  próprias.
- **Célula climática** de 0,5° (cerca de 55 km) da grade da CPC/NOAA que contém a sede municipal
  é a unidade da exposição. Municípios na mesma célula compartilham a temperatura.
- **Referência climática:** 2014 a 2025. **Painel diário:** de 1º de janeiro de 2026 em diante, com
  previsão de 7 dias. **Validação:** 2014 a 2025.

## 2. Fontes de dados

| Dado | Fonte | Uso |
|---|---|---|
| Temperatura máxima e mínima diária observada | CPC Global Unified Temperature (NOAA PSL), grade de 0,5° | climatologia, série observada, validação |
| Dias recentes e previsão de 7 dias | Open-Meteo (previsão e previsão histórica, CC BY 4.0) | dias ainda não publicados pela NOAA e previsão |
| População total, 60+ e 80+ | IBGE, Censo 2022 (tabela 9514) | sensibilidade |
| Municípios, UFs e contornos | IBGE (localidades e malhas) | território |
| Coordenadas das sedes | kelvins/municipios-brasileiros (MIT) e geocodificação do Open-Meteo | atribuição da célula |
| Equipes de Saúde da Família e de Atenção Primária | CNES/DataSUS (arquivos EP) | capacidade de resposta |
| Internações (AIH reduzida) | SIH/DataSUS (arquivos RD) | validação e modelo de demanda |

A CPC é construída a partir de estações de superfície (inclusive as do INMET transmitidas ao
sistema global) e oferece uma série nacional homogênea desde 1979. Ela foi adotada no lugar das
estações do INMET isoladas e da reanálise ERA5 previstas no projeto (seção 6.2) por cobrir todo
o país sem lacunas e por ser atualizada diariamente.

## 3. O índice

**IVC = 100 × (0,60 × E + 0,25 × S + 0,15 × C)**, de 0 a 100.

**Exposição (E).** Usa o Fator de Excesso de Calor (EHF) de Nairn e Fawcett (2015). A temperatura
média do dia é T = (Tmáx + Tmín) / 2, e T3 é a média de T no dia e nos dois seguintes.

- EHIsig = T3 − P95, em que P95 é o percentil 95 de T na célula entre 2014 e 2025.
- EHIaccl = T3 − média de T nos 30 dias anteriores.
- EHF = EHIsig × máx(1, EHIaccl). A severidade é EHF / EHF85, sendo EHF85 o percentil 85 dos
  EHF positivos da célula.

Com EHF positivo (onda de calor), E = 0,5 + 0,5 × mín(severidade / 3, 1). Sem onda de calor,
E = 0,5 × (T3 − P50) / (P95 − P50), limitado a 0 e 1. Assim, E sobe com o calor relativo ao
próprio lugar: 35 °C é comum em Teresina e extremo em Curitiba.

**Sensibilidade (S).** S = 0,7 × proporção de 60+ / percentil 99 do país + 0,3 × proporção de
80+ / percentil 99 do país (Censo 2022), cada termo limitado a 1.

**Capacidade de resposta (C).** As equipes de Saúde da Família fazem a busca ativa e o cuidado
domiciliar que o protocolo prevê. A razão "pessoas que as equipes podem acompanhar por habitante"
é (equipes de Saúde da Família × 3.450 + equipes de Atenção Primária × 3.000) / população. Ela
vem do CNES (equipes ativas na competência mais recente) e é usada sem o teto de 100%. Ela é
dividida pelo percentil 99 do país, e C = 1 − essa razão relativa, limitado entre 0 e 1. Menos
equipes por habitante resulta em C maior e IVC maior. O CNES é atualizado uma vez por ano.

**Faixas e protocolo.**

| Faixa | IVC | Conduta proposta |
|---|---|---|
| BAIXA | 0 a 39 | monitoramento de rotina; ações educativas permanentes |
| MODERADA | 40 a 59 | comunicação preventiva a idosos e cuidadores; checagem de insumos de hidratação |
| ALTA | 60 a 79 | reforço de equipes na atenção básica; busca ativa de idosos em isolamento; articulação com assistência social e defesa civil |
| MUITO ALTA | 80 a 100 | pontos de apoio com hidratação e climatização; contato dirigido a idosos com comorbidades; retaguarda hospitalar |

O limiar de ação proposto é 60 e é pactuável com os gestores. O painel permite mudá-lo, e a aba
Validação mostra o efeito de cada limiar.

## 4. Operação diária

1. A NOAA publica os dias observados da CPC do ano corrente, que são incorporados assim que saem.
2. A previsão do Open-Meteo traz os próximos 7 dias e os 7 dias anteriores, para cada uma das
   1.446 células. A diferença média entre a previsão e a observação de cada célula é medida e
   descontada, e a correção é atualizada todo dia.
3. Dias entre o fim da observação e a janela recente são completados com a previsão histórica
   do Open-Meteo.
4. A exposição, o IVC, as internações previstas e os arquivos do painel são recalculados.

Tudo roda no GitHub Actions: completo às 06:00 de Brasília e complementos a cada 2 horas. O
painel é publicado no GitHub Pages. O consumo do Open-Meteo fica abaixo de 10.000 chamadas por
dia.

## 5. Validação retrospectiva

**Pergunta.** Nos dias em que o IVC atinge o limiar, as internações de idosos aumentam?

**Dados.** Foram usados os arquivos RD do SIH de todas as UFs, das competências de 2014 em
diante. Contam-se as internações de urgência (AIH tipo 1, sem as eletivas, de continuação e de
longa permanência) de pessoas com 60+, por município de residência e data de internação.

| Grupo de causas | CID-10 do diagnóstico principal |
|---|---|
| Sensíveis ao calor (Bobb et al., 2014) | E86–E87, N17, N19, N39.0, A40–A41, T67, X30 |
| Aparelho circulatório | I00–I99 |
| Aparelho respiratório | J00–J99 |
| Todas as causas clínicas | todas, exceto S00–T98 e V01–Y98 (salvo T67 e X30), O00–O99 e Z00–Z99 |

**IVC histórico.** O IVC de cada dia de 2014 a 2025 é recalculado com a temperatura observada da
CPC, pela mesma fórmula, com os mesmos pesos e o mesmo arredondamento do painel. Os testes
automáticos conferem que o valor recalculado é igual ao do painel.

**Desenho.** Série temporal estratificada no tempo (Janes et al., 2005): cada dia de um município
é comparado só com dias do mesmo município, ano, mês e dia da semana. Isso controla estação do
ano, tendência, tamanho e perfil da população e características fixas do lugar.

**Exposição.** Um dia está em alerta quando o IVC do próprio dia ou de um dos dois anteriores
atinge o limiar, porque o IVC de um dia mede a onda de calor daquele dia e dos dois seguintes.
A faixa do dia é a maior das três.

**Medidas.**

- Razão de taxas de Mantel-Haenszel.
- Intervalo de 95% por bootstrap de municípios (500 réplicas), que respeita a autocorrelação dos
  dias de um mesmo lugar. Nas UFs com menos de 30 municípios a reamostragem é por município-ano.
- Internações a mais = internações nos dias de alerta × (1 − 1/razão).

As análises são feitas por faixa, por dia após o alerta (0 a 7), por limiar (40 a 80), por UF e
por região.

## 6. Modelo de demanda (aprendizado de máquina)

**Objetivo.** Estimar as internações de urgência de pessoas com 60+ esperadas em cada município e
dia, em dois desfechos: todas as causas clínicas e causas sensíveis ao calor.

**Algoritmo.** Gradient boosting de árvores de decisão com perda de Poisson (scikit-learn
HistGradientBoostingRegressor). O modelo aprende a razão entre as internações do dia e a demanda
habitual do município, e a previsão é essa razão multiplicada pela demanda habitual. Assim cidades
grandes e pequenas ficam na mesma escala. Gradient boosting é da mesma família do Random Forest
previsto no projeto, mas trata contagens com a perda adequada e escala para os cerca de 20
milhões de registros município-dia. Uma rede LSTM por município exigiria séries densas que a
maioria dos 5.571 municípios não tem (menos de uma internação por dia).

**Variáveis.** Todas estão disponíveis no dia da previsão:

- demanda habitual: média diária dos 365 dias que terminam 180 dias antes, porque o SIH chega com
  meses de atraso;
- mês, dia da semana e sazonalidade;
- exposição do IVC no dia e nos dois anteriores, e o maior IVC desses três dias;
- sensibilidade, capacidade, população 60+ e UF.

**Validação temporal, como no projeto (seção 6.1).** Treino até 2022, validação em 2023–2024 e
teste em 2025, um ano que o modelo não viu. O período de validação também recalibra o nível das
previsões: as internações crescem com o envelhecimento da população, e a razão observado/previsto
de 2023–2024 multiplica as previsões seguintes. O mesmo modelo sem as variáveis de calor serve de
comparação. As métricas são:

- erro absoluto médio e quadrático por município-dia e por UF-dia;
- erro percentual por UF-dia;
- variação explicada (D² de Poisson);
- acurácia, precisão, sensibilidade e F1 para os dias de demanda alta (acima do percentil 90 de
  cada UF);
- calibração por décimos;
- razão entre observado e previsto nos dias de alerta.

**Operação.** Os modelos ficam versionados em `modelos/` (`demanda_*.joblib` e `demanda.json`, com
período, variáveis e métricas). A demanda habitual operacional, em `data/ref/demanda_base.csv`, é
a do último ano completo do SIH. O retreinamento é feito ao rodar de novo a validação, uma vez por
ano ou quando o desempenho cair.

## 7. Limites

- O índice e o modelo descrevem municípios, não pessoas (falácia ecológica).
- A resolução de 0,5° não distingue bairros nem ilhas de calor urbanas. Na Amazônia a CPC se apoia
  em poucas estações.
- Umidade, poluição e precipitação não entram no índice nem foram ajustadas na validação.
- O SIH cobre só internações pagas pelo SUS. O município é o de residência.
- A sensibilidade usa o Censo 2022 em todos os anos, e a referência climática é do mesmo período
  da validação.
- A prevalência de comorbidades, prevista no projeto, não entrou no índice por falta de dado
  municipal aberto e atualizado. A sensibilidade usa a proporção de 80+ como aproximação do maior
  risco clínico.
- Os óbitos (SIM) ainda não foram usados na validação.

## Referências

- BOBB, J. F. et al. Cause-specific risk of hospital admission related to extreme heat in older
  adults. JAMA, v. 312, n. 24, p. 2659–2667, 2014.
- JANES, H.; SHEPPARD, L.; LUMLEY, T. Case-crossover analyses of air pollution exposure data:
  referent selection strategies and their implications for bias. Epidemiology, v. 16, n. 6,
  p. 717–726, 2005.
- NAIRN, J.; FAWCETT, R. The Excess Heat Factor: a metric for heatwave intensity and its use in
  classifying heatwave severity. Int. J. Environ. Res. Public Health, v. 12, p. 227–253, 2015.
