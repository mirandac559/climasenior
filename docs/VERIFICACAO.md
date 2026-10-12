# Verificação do produto técnico (versão 1.0)

Verificação feita em 12/10/2026 sobre o painel publicado e os dados que o alimentam. Ela tem três
camadas, e todas podem ser repetidas a qualquer momento:

| Camada | Como rodar | Resultado |
|---|---|---|
| Testes automáticos do código (sem rede, com fontes simuladas) | `python -m pytest tests -q` | todos aprovados; rodam no GitHub a cada mudança |
| Coerência dos dados publicados | `python -m climasenior.verificar site/data` | 26 de 26 verificações |
| Funcionamento do painel no navegador (controles, abas, números, celular, modo escuro) | roteiro abaixo | 42 de 42 verificações |

## 1. Coerência dos dados publicados

| Verificação | Resultado |
|---|---|
| Municípios no painel e na referência | 5.571 |
| Células climáticas | 1.446; todos os municípios têm célula |
| Dias no painel | contínuos de 01/01/2026 até o fim da previsão; observados no início, previsão no fim |
| População 60+ total | 32,11 milhões (Censo 2022: 32,1 milhões) |
| Sensibilidade e capacidade | entre 0 e 1 |
| Pesos do IVC | 60% / 25% / 15%, os mesmos na validação |
| IVC publicado = IVC recalculado a partir da temperatura, da climatologia, da sensibilidade e da capacidade | 12 dias × 5.571 municípios: 99,3% idênticos, diferença máxima de 1 ponto (arredondamento da temperatura gravada) |
| Internações previstas | não negativas; as sensíveis ao calor nunca excedem o total; total do dia coerente com a demanda habitual |
| Validação | faixas somam 100% dos dias; dias em alerta diminuem com o limiar; razão dentro do intervalo; dias em alerta = ALTA + MUITO ALTA; Brasil, 27 UFs e 5 regiões |
| Modelo de demanda (teste em 2025) | observado/previsto 1,02 (todas as causas) e 1,01 (sensíveis ao calor) |

## 2. Funcionamento do painel

| Função | Verificado |
|---|---|
| Cabeçalho | título; subtítulo "Índice de Vulnerabilidade Climática para a saúde da população idosa"; logos do Itaú Viver Mais e do Portal do Envelhecimento e Longeviver carregadas |
| Abas | Situação, Série temporal, Protocolo, Validação |
| Avisos e filtros retirados | sem avisos de capacidade e de Censo; sem o filtro da RM |
| Indicadores de área | municípios em alerta, IVC máximo, pessoas com 60+ em alerta e internações previstas conferidos com o arquivo do dia |
| Limiar | 40, 60 e 80: contagens conferidas e decrescentes |
| Data | primeiro dia (01/01/2026), último dia (marcado como previsão), indicadores acompanham a data |
| Área | Maranhão, São Paulo, Amazonas e Distrito Federal: contagens conferidas; a tabela só mostra a UF escolhida |
| CSV do dia | baixa um arquivo com todos os municípios da área e as internações previstas |
| Município | São Luís: IVC, posição no ranking e internações previstas conferidos; linha de escopo; volta à área |
| Mapa | dica ao passar o mouse; o clique abre a série do município |
| Série temporal | todos os dias de 2026 no painel |
| Protocolo | lista os municípios em alerta, com o mesmo total dos indicadores |
| Validação | frase-resumo; tabela de limiares com o limiar atual em destaque; regiões; modelo de demanda com 6 métricas; troca do grupo de causas; série observada e prevista em 2025; acompanha a área; data de atualização |
| Telas | 400 px (claro e escuro) e 1.280 px (escuro): sem rolagem lateral e sem erros |
| Console do navegador | sem erros |

## 3. O que o projeto previa e o que foi entregue

| Previsto no projeto | Situação | Onde está |
|---|---|---|
| IVC para a população idosa em escala local, integrando clima, demografia e saúde | **Atendido** em escala nacional: 5.571 municípios, diário, com previsão de 7 dias | painel; `climasenior/brasil.py` |
| Componentes: exposição, densidade de idosos, capacidade de resposta | **Atendido** (60/25/15): exposição pelo EHF; idosos 60+ e 80+ (Censo 2022); cobertura da atenção primária (CNES) | Metodologia, seção 3 |
| Prevalência de comorbidades no índice | **Não atendido**: não há dado municipal aberto e atualizado. A proporção de 80+ entra como aproximação do maior risco clínico | Metodologia, seção 7 |
| Integrar e qualificar bases, avaliando cobertura, lacunas e limitações | **Atendido**: correção diária do desvio da previsão, preenchimento de lacunas, verificador de coerência, limites documentados | aba Validação → Dados do painel diário; `climasenior/verificar.py` |
| Dados do INMET (temperatura, umidade, precipitação, qualidade do ar) | **Adaptado**: temperatura da CPC/NOAA, que incorpora estações do INMET e cobre todo o país. Umidade, precipitação e qualidade do ar não foram incorporadas | Metodologia, seções 2 e 7 |
| Dados do DataSUS (emergência, internações, óbitos) | **Parcial**: internações (SIH, 156 milhões de AIH lidas) e equipes (CNES). Óbitos (SIM) e atendimentos ambulatoriais de emergência não foram usados | aba Validação |
| Modelos de aprendizado de máquina para a demanda assistencial e o nível de risco | **Atendido**: gradient boosting com perda de Poisson (família do Random Forest) para a demanda; o nível de risco é o IVC, validado com internações | aba Validação → Modelo de demanda; `modelos/` |
| LSTM e regressão logística | **Substituídos, com justificativa**: LSTM exige séries densas que a maioria dos municípios não tem; a composição do IVC usa os pesos do projeto, interpretáveis e pactuáveis, e a validação mostra gradiente por faixa | Metodologia, seção 6 |
| Validação temporal: treino até 2022, validação 2023–2024, teste 2025; acurácia, precisão, recall, F1, MAE, RMSE, calibração | **Atendido** | `modelos/demanda.json`; aba Validação |
| Backtesting com eventos reais | **Atendido** para 2014–2025: 27,4 milhões de internações de urgência de 60+; nos dias de alerta, +17% nas internações por causas sensíveis ao calor (IC 95%: 15% a 19%), cerca de 600 a mais por ano | aba Validação; `data/validacao/` |
| Dashboard (FastAPI, Streamlit, Plotly, Folium) | **Adaptado**: página web estática publicada no GitHub Pages, com dados abertos em JSON e CSV. Não tem servidor para manter e tem custo zero | painel; Guia de implantação |
| Banco InfluxDB/PostgreSQL | **Adaptado**: arquivos versionados no repositório (CSV/JSON), com histórico completo no Git | Governança de dados |
| Protocolo com limiares e recomendações | **Atendido**: faixas e condutas, limiar pactuável e tabela de efeito de cada limiar | abas Protocolo e Validação |
| Monitoramento de desempenho, re-treinamento e versionamento | **Atendido**: modelos e métricas versionados, retreino anual pelo fluxo de validação, critérios de drift | Guia de implantação, seção 5 |
| Validação de uso com gestores (workshops, usabilidade) | **Instrumentos prontos**: roteiro, ficha de pactuação e escala de usabilidade. A aplicação depende da agenda com os gestores | `docs/fase3/` |
| LGPD: só dados agregados e anonimizados | **Atendido**: nenhum dado pessoal é gravado | Governança de dados |
| Código aberto, documentação completa, guias de implementação, transferência | **Atendido**: licença MIT, manual, metodologia, guia de implantação, governança | `README.md`, `docs/` |
| Território-piloto RM de São Luís | **Coberto** dentro da operação nacional. No Maranhão a associação entre alerta e internações não foi significativa (razão 1,01; IC 0,78 a 1,14), ponto a levar ao workshop | aba Validação (Maranhão) |
| Integração aos fluxos de alerta (Cemaden, Defesa Civil Alerta) | **Pronto do lado técnico**: dados abertos e CSV do dia. A integração formal depende de acordo institucional | Guia de implantação, seção 7 |

## 4. O que foi retirado na consolidação

- **Protótipo 0.3:** API FastAPI, painel Streamlit, modelos treinados com dados de demonstração,
  backtesting de demonstração e documentos que descreviam essa versão.
- **Operação piloto 0.4:** 13 municípios com ERA5 por sede, com seus dados e testes.
- **Funções de acesso a dados** que só serviam às versões anteriores.
- **No painel:**
  - o trecho "· Brasil, 5.571 municípios · atualização diária" do subtítulo;
  - os avisos de capacidade e de Censo;
  - o filtro da RM;
  - o indicador técnico de "pendências", trocado pela data de atualização;
  - "(Fase 3)" no nome da aba.
