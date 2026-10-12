# Plano de governança de dados

## Princípios (LGPD, Lei nº 13.709/2018)
- **Finalidade**: proteção da saúde da população idosa diante de extremos climáticos
- **Minimização**: apenas dados agregados por município e dia; nenhum dado pessoal identificável
- **Transparência**: fontes, transformações e versões de modelo registradas em `modelos/`
- **Não discriminação**: o índice descreve territórios, nunca indivíduos (vedação à falácia ecológica)

## Rastreabilidade
| Etapa | Registro |
|---|---|
| Ingestão | nome do arquivo, fonte, data de download, hash SHA-256 |
| Atributos | lista em `atributos.ATRIBUTOS`, versionada com o código |
| Modelo | `modelos/climasenior_<versao>.joblib` + `metricas_<versao>.json` |
| IVC | `modelos/ivc_<versao>.parquet` |

## Acesso
- Leitura pública da API para dados agregados (após transferência ao ente receptor)
- Escrita restrita ao operador do pipeline
- Logs de acesso mantidos pelo ente receptor

## Transferência
Cessão do código sob licença MIT, capacitação da equipe receptora e definição de
responsável pela atualização sazonal, formalizadas em termo de cooperação técnica.
