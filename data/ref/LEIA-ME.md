# Referências da operação

Gerados automaticamente na primeira execução e reaproveitados depois:

- `municipios.json` — nomes, códigos IBGE e coordenadas das sedes (com auditoria de geocodificação)
- `censo2022.json` — população total, 60+ e 80+ (IBGE, Censo 2022, tabela 9514)
- `climatologia.json` — percentis 50, 90 e 95 da temperatura média e EHF85 (ERA5, 2014–2025)
- `vies_modelo.json` — desvio médio do modelo de previsão frente ao ERA5 na última execução

Opcional, preenchido pela equipe:

- `capacidade.csv` — `cod_ibge;estab_atencao_basica` (CNES), uma linha por município.
  Sem ele, o IVC usa exposição e sensibilidade, e o painel informa.

Para refazer uma referência (por exemplo, ao mudar o período da climatologia), apague o arquivo.
