# Referências da operação

Gerados automaticamente e reaproveitados nas execuções seguintes:

| Arquivo | Conteúdo | Gerado por |
|---|---|---|
| `municipios_br.csv` | 5.571 municípios: código IBGE, nome, UF, coordenadas da sede, população total, 60+ e 80+ (Censo 2022) e célula climática | primeira execução (`climasenior.brasil`) |
| `ufs.json` | contornos simplificados das UFs para o mapa | primeira execução |
| `celulas.csv` | 1.446 células de 0,5°: percentis 50, 90 e 95 da temperatura média e EHF85 (CPC, 2014–2025) | primeira execução |
| `vies.csv` | diferença média entre a previsão do Open-Meteo e a observação da CPC, por célula (atualizada todo dia) | operação diária |
| `capacidade.csv` | equipes de Saúde da Família e de Atenção Primária e cobertura por município (CNES) | fluxo "Atualizar capacidade de resposta (CNES)" |
| `demanda_base.csv` | demanda habitual de cada município (internações de 60+ por dia, último ano completo do SIH) | fluxo "Validação retrospectiva" |
| `fontes.json`, `pendencias.json`, `uso_api.json` | controle da operação: última versão da CPC lida, lacunas, chamadas ao Open-Meteo | operação diária |

Para refazer uma referência (por exemplo, com um novo Censo), apague o arquivo e rode a
atualização completa.
