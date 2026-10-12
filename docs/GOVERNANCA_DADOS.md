# Governança de dados

## Princípios (LGPD, Lei nº 13.709/2018)

- **Finalidade:** proteção da saúde da população idosa diante de extremos climáticos.
- **Minimização:** só dados públicos e agregados por município e dia. Nenhum dado pessoal é
  guardado. Os arquivos do SIH são lidos em memória, reduzidos a contagens diárias por município
  e descartados na mesma execução. Nome, CPF, endereço, data de nascimento e número da AIH nunca
  são gravados.
- **Transparência:** fontes, transformações, versões de modelo e resultados ficam no repositório
  público, com histórico completo no Git.
- **Não discriminação:** o índice descreve territórios, nunca indivíduos, para evitar a falácia
  ecológica.

## Inventário

| Dado | Origem | Nível | Onde fica | Atualização |
|---|---|---|---|---|
| Temperatura observada | NOAA PSL (CPC) | célula de 0,5°, dia | `data/clima/AAAA/` | diária |
| Temperatura prevista | Open-Meteo | célula, dia | `data/clima/`, `data/previsao/` | diária |
| População | IBGE, Censo 2022 | município | `data/ref/municipios_br.csv` | a cada Censo |
| Equipes da atenção primária | CNES/DataSUS | município | `data/ref/capacidade.csv` | anual |
| Internações | SIH/DataSUS | município de residência, dia, grupo de causa (contagens) | artefatos do GitHub Actions (90 dias); resultados agregados em `data/validacao/` | anual |
| Modelo de demanda | treinado sobre as contagens acima | — | `modelos/` | anual |

## Rastreabilidade

| Etapa | Registro |
|---|---|
| Execução diária | `data/log/ultima_execucao.log` e histórico de commits do robô ("Atualização AAAA-MM-DD") |
| Fontes consultadas | `data/ref/fontes.json` (última modificação dos arquivos da NOAA), `meta.json` do painel |
| Consumo do Open-Meteo | `data/ref/uso_api.json` |
| Validação | `data/validacao/resultados.json` (arquivos do SIH lidos, falhas, período, método) |
| Modelo | `modelos/demanda.json` (versão, data do treino, períodos, variáveis, métricas) e `modelos/demanda_*.joblib` |

## Acesso e responsabilidades

- **Leitura:** pública (painel e arquivos JSON). Todo o conteúdo é agregado e derivado de dados
  públicos.
- **Escrita:** só os fluxos automáticos e a equipe técnica do ente receptor, com permissão no
  repositório.
- **Responsável pela operação, pela atualização anual e pela comunicação com as fontes:** definido
  no termo de cooperação técnica com o ente receptor.

## Transferência

A transferência inclui a cessão do código sob licença MIT, a capacitação da equipe receptora
(ver o Guia de implantação) e a definição do responsável pela manutenção anual, formalizadas em
termo de cooperação técnica.
