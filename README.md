# ClimaSênior

**Índice de Vulnerabilidade Climática (IVC) para a saúde da população idosa**, para os 5.571
municípios do Brasil, atualizado todos os dias.

Painel: **https://mirandac559.github.io/climasenior/**

> O presente trabalho foi realizado com apoio do Itaú Viver Mais e Portal do Envelhecimento.

## O que a plataforma faz

- **Calcula o IVC de cada município, todos os dias**, de 2026 em diante, com previsão para os
  próximos 7 dias. O índice combina três componentes:
  - o calor fora do comum para o lugar (exposição, 60%);
  - a proporção de pessoas com 60 e 80 anos ou mais (sensibilidade, 25%);
  - a cobertura da atenção primária (capacidade de resposta, 15%).
- **Indica a conduta** pelo protocolo de resposta graduada: BAIXA, MODERADA, ALTA e MUITO ALTA,
  com limiar de ação pactuável.
- **Estima as internações de idosos esperadas** em cada município e dia, com um modelo de
  aprendizado de máquina treinado com as internações reais do SUS.
- **Mostra a evidência** de que o índice funciona. A validação retrospectiva de 2014 a 2025 compara
  os dias de alerta com 27 milhões de internações de urgência de pessoas com 60+ do SIH/DataSUS.
- **Disponibiliza os dados abertos** em arquivos JSON e permite baixar a situação do dia em CSV.

## Documentação

| Documento | Para quem |
|---|---|
| [Manual do usuário](docs/MANUAL_DO_USUARIO.md) | gestores e técnicos que usam o painel |
| [Metodologia](docs/METODOLOGIA.md) | IVC, fontes, validação, modelo de demanda e limites |
| [Guia de implantação e transferência](docs/GUIA_DE_IMPLANTACAO.md) | equipe que vai operar a plataforma |
| [Governança de dados](docs/GOVERNANCA_DADOS.md) | LGPD, inventário, rastreabilidade |
| [Verificação do produto](docs/VERIFICACAO.md) | o que foi testado e o que o projeto previa |
| [Instrumentos da Fase 3](docs/fase3/) | roteiro do workshop, ficha de pactuação de limiares, avaliação de usabilidade |

## Estrutura

```
climasenior/brasil.py        operação diária: território, climatologia, observação, previsão, IVC, painel
climasenior/cpc.py           leitura da temperatura observada (CPC/NOAA, NetCDF)
climasenior/fontes.py        conectores IBGE, Open-Meteo e coordenadas
climasenior/ehf.py           Fator de Excesso de Calor (Nairn e Fawcett, 2015)
climasenior/cnes.py          capacidade de resposta (equipes da atenção primária, CNES)
climasenior/sih.py           internações do SIH/DataSUS (download, leitura e agregação)
climasenior/validacao.py     validação retrospectiva do IVC (2014-2025)
climasenior/demanda.py       modelo de demanda assistencial (aprendizado de máquina)
climasenior/simulacao_br.py  respostas simuladas das fontes, para os testes
site/index.html              painel (uma página; dados em site/data/, gerados pelo pipeline)
modelos/                     modelos de demanda versionados e suas métricas
data/                        referências, série diária por célula, resultados da validação
.github/workflows/           operação diária, CNES, validação e testes
tests/                       testes automáticos (sem rede)
```

## Executar

```bash
pip install -r requirements-validacao.txt pytest
python -m pytest tests -q                          # testes
python -m climasenior.brasil                       # atualização completa (acesso às fontes)
python -m climasenior.brasil --painel              # só recalcula o painel com os dados gravados
python -m http.server 8000 -d site                 # painel em http://localhost:8000
python -m climasenior.cnes                         # capacidade de resposta (CNES)
python -m climasenior.validacao sih --ano 2024 --ufs MA --saida sih
python -m climasenior.validacao analisar --sih sih --ufs MA --anos 2024
```

Sem rede, com dados fictícios: `python -m climasenior.brasil --simular`.

## Licença

MIT. Os dados vêm de fontes públicas: NOAA, Open-Meteo (CC BY 4.0), IBGE, DataSUS (CNES e SIH)
e kelvins/municipios-brasileiros (MIT).
