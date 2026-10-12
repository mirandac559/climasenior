# ClimaSênior

Boletim diário de vulnerabilidade ao calor da população idosa na Região Metropolitana
da Grande São Luís (MA). Calcula, para os 13 municípios, o **Índice de Vulnerabilidade
Climática (IVC)** de hoje e dos próximos dias, a partir de dados públicos atualizados
automaticamente, e indica a conduta do protocolo de resposta graduada.

> O presente trabalho foi realizado com apoio do Itaú Viver Mais e Portal do Envelhecimento.

## O que roda todo dia

Às 06:00 de São Luís, o fluxo `Atualizar ClimaSênior` (GitHub Actions):

1. completa a série desde 01/01/2026 com a **reanálise ERA5** (dias consolidados);
2. busca a **janela recente e a previsão de 16 dias** do modelo meteorológico e corrige
   o desvio médio do modelo em relação ao ERA5;
3. calcula o **Fator de Excesso de Calor (EHF)** e o **IVC** por município e dia;
4. grava a série em `data/serie/AAAA.csv` (um arquivo por ano: 2026, 2027, ...);
5. publica o painel no **GitHub Pages**.

Na primeira execução, também resolve os códigos IBGE dos municípios, lê a população
com 60 e 80 anos ou mais (Censo 2022) e monta a climatologia de referência
(ERA5, 2014–2025). Isso leva alguns minutos e fica guardado em `data/ref/`.

Se o fluxo ficar dias sem rodar, a execução seguinte recupera o intervalo inteiro.
A virada de ano não exige nenhuma ação.

## O índice

| Componente | Peso | Dado | Atualização |
|---|---|---|---|
| Exposição | 60% | EHF (Nairn e Fawcett, 2015) sobre a temperatura média; ERA5 e previsão via Open-Meteo | diária |
| Sensibilidade | 25% | proporção de pessoas com 60+ e 80+ (IBGE, Censo 2022) | estrutural |
| Capacidade de resposta | 15% | estabelecimentos de atenção básica por habitante (CNES) | opcional, `data/ref/capacidade.csv` |

Sem o arquivo de capacidade, o peso é redistribuído entre exposição e sensibilidade e o
painel informa. Faixas: BAIXA (0–39), MODERADA (40–59), ALTA (60–79), MUITO ALTA (80–100);
o protocolo é acionado a partir de 60 (`LIMIAR_ACAO` em `climasenior/config.py`).

## Publicar no GitHub Pages

1. Coloque este repositório no GitHub.
2. Em **Settings → Pages**, escolha **Source: GitHub Actions**.
3. Em **Actions**, abra *Atualizar ClimaSênior* e clique em **Run workflow**.
4. Ao terminar, o endereço do painel aparece no resumo da execução.

## Rodar localmente

```bash
pip install -r requirements-operacional.txt
python -m climasenior.operacional               # dados reais (precisa de internet)
python -m http.server 8000 -d site              # painel em http://localhost:8000
```

Teste sem rede, com dados simulados e municípios fictícios:

```bash
python -m climasenior.operacional --simular
python -m http.server 8000 -d simulacao/site
```

Testes: `pip install pytest && python -m pytest tests -q`

## Servidor da instituição

`docker build -t climasenior . && docker run -p 8080:8080 -v climasenior-dados:/app/data climasenior`
atualiza ao iniciar e todo dia às 06:00, servindo o painel na porta 8080.

## Estrutura

```
climasenior/operacional.py   orquestra a atualização diária
climasenior/fontes.py        conectores Open-Meteo e IBGE
climasenior/ehf.py           Fator de Excesso de Calor
climasenior/simulacao.py     respostas simuladas para testes
site/index.html              painel (lê site/data/*.json)
data/serie/, data/ref/       série diária por ano e referências (versionadas)
.github/workflows/           atualização e publicação diárias
climasenior/modelos.py, backtesting.py, api/, app/   módulos de pesquisa (v0.3, modo demonstração)
```

## Fontes e licenças

- Dados meteorológicos: [Open-Meteo](https://open-meteo.com) (CC BY 4.0), com reanálise ERA5
  (Copernicus/ECMWF). Uso gratuito não comercial; para uso intensivo por órgão público,
  há planos com chave de API.
- População: IBGE, Censo Demográfico 2022, tabela 9514; códigos de município: API de localidades do IBGE.
- Código: licença MIT.

## Limites

O índice descreve municípios, não pessoas. Os limiares e pesos ainda serão calibrados com
internações e óbitos do DataSUS (que chegam com meses de atraso) e pactuados com os gestores.
