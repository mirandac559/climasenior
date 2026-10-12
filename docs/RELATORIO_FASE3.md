# Relatório de execução — Fase 3 (Validação e Estudo de Caso)

**Período:** Meses 6–7 · **Território-piloto:** Região Metropolitana de São Luís (MA)

## 1. O que foi executado
1. **Protótipo funcional (Produto 8)** — pacote `climasenior` com núcleo de modelagem, API REST
   (FastAPI) e painel interativo (Streamlit + Plotly + Folium), cobertos por testes automatizados.
2. **Módulo de backtesting** — identificação de episódios de calor e verificação de detecção,
   antecedência e falso alarme do IVC (`climasenior/backtesting.py`, protocolo em `fase3/01`).
3. **Curva de limiares** — sensibilidade × falso alarme para IVC ∈ {40, 50, 60, 70, 80},
   insumo da pactuação com gestores.
4. **Monitor de deriva** — PSI por atributo, com sinalização automática de retreinamento.
5. **Instrumentos de validação participativa** — roteiro de workshop, ficha de pactuação de
   limiares e condutas, e instrumento de usabilidade (SUS adaptado).

## 2. Verificação da esteira (modo demonstração)
A execução completa em modo `demo` confirmou a integridade funcional: 56.979 registros diários
(13 municípios, 2014–2025), 14 atributos, três componentes treinados com divisão temporal,
IVC calculado e backtesting executado sobre 2025. Em coerência com as fases anteriores,
as medidas de acumulação térmica (`tmax_mm14`, `tmax_mm7`) e as noites quentes lideraram
a importância das variáveis. O monitor de deriva sinalizou `tmax_mm7` e `tmax_mm14`,
capturando a tendência de aquecimento embutida na série, o que demonstra o funcionamento
do mecanismo.

> **Os valores numéricos deste relatório provêm de dados sintéticos e não constituem
> resultados científicos.** Os resultados válidos serão obtidos ao conectar as bases reais
> (`docs/GUIA_IMPLEMENTACAO.md`) e reportados com intervalos de confiança.

## 3. Pendências que dependem de acesso e de agenda
| Item | Situação | Responsável |
|---|---|---|
| Exportação das bases reais (BDMEP, TabNet, SIDRA, CNES) | a executar | equipe |
| Calibração do limiar térmico local (DLNM) | a executar após dados reais | equipe |
| Workshop de validação com gestores | a agendar | coordenação |
| Pactuação dos limiares e pesos | após workshop | gestores + equipe |
| Definição do ente receptor | em articulação | coordenação |

## 4. Próximos passos (Fase 4)
Documentação final, termo de cooperação, capacitação da equipe receptora e entrega do
protótipo (código aberto, licença MIT).
