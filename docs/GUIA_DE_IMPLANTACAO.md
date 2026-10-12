# Guia de implantação e transferência

Como um ente público (secretaria de saúde, defesa civil) assume a operação do ClimaSênior.

## 1. O que é transferido

- **Código** (licença MIT): pipeline em Python, painel em uma página HTML, testes e fluxos
  automáticos.
- **Dados de referência** em `data/ref/`: municípios, células climáticas, climatologia, cobertura
  da atenção primária e demanda habitual.
- **Modelos versionados** em `modelos/`: modelo de demanda com período de treino, variáveis e
  métricas em `demanda.json`.
- **Resultados da validação** em `data/validacao/`.
- **Documentação**: este guia, a metodologia, o manual do usuário, a governança de dados e os
  instrumentos da Fase 3 (`docs/fase3/`).

## 2. Implantação no GitHub (recomendada, sem custo)

1. Transfira o repositório para a conta institucional (Settings → Transfer) ou faça um fork.
2. Em **Settings → Pages**, escolha "GitHub Actions" como origem.
3. Em **Settings → Actions → General**, permita leitura e escrita para os fluxos ("Read and
   write permissions").
4. Rode à mão, na aba **Actions**, o fluxo "Atualizar ClimaSênior" (modo `completo`). A partir daí
   ele roda sozinho.

Na primeira execução, se `data/ref/` estiver vazio, o pipeline baixa municípios, Censo, coordenadas
e climatologia (cerca de 15 minutos). Depois, cada execução diária leva poucos minutos.

| Fluxo | Quando roda | O que faz |
|---|---|---|
| Atualizar ClimaSênior | 06:00 de Brasília (completo), a cada 2 h (lacunas) e a cada mudança no painel | temperatura observada e prevista, IVC, internações previstas, publicação do painel |
| Atualizar capacidade de resposta (CNES) | 15 de fevereiro, ou à mão | equipes da atenção primária por município |
| Validação retrospectiva | à mão | baixa o SIH (cerca de 1h20), refaz a validação e retreina o modelo de demanda |
| Testes | a cada mudança no código | testes automáticos, sem acesso à rede |

## 3. Implantação em servidor próprio (alternativa)

O `Dockerfile` monta uma imagem que atualiza ao iniciar, às 06:00 e a cada 2 horas, e serve o
painel na porta 8080. As pastas `data/` e `site/data/` devem ficar em volumes persistentes.

```bash
docker build -t climasenior .
docker run -d -p 8080:8080 -v climasenior-dados:/app/data -v climasenior-site:/app/site/data climasenior
```

## 4. Custos de operação

| Item | Custo |
|---|---|
| GitHub Actions e Pages (repositório público) | gratuito |
| NOAA (CPC), IBGE, DataSUS | gratuito (dados públicos) |
| Open-Meteo | gratuito para uso não comercial, até 10.000 chamadas/dia (o sistema usa cerca de 3.000). Para uso institucional permanente, confirme os termos; o plano comercial e a hospedagem própria (código aberto) são as alternativas |
| Servidor próprio (opcional) | 1 vCPU e 2 GB de RAM bastam para a operação diária; a validação precisa de cerca de 8 GB por algumas horas, uma vez por ano |

## 5. Calendário de manutenção

| Quando | Tarefa | Responsável |
|---|---|---|
| Todo dia | Conferir a data de atualização no painel (aba Validação → Dados do painel diário) | operador |
| Se a atualização parar | Ler `data/log/ultima_execucao.log` e a aba Actions; rodar o fluxo de novo | operador |
| Fevereiro | Fluxo do CNES (roda sozinho) e conferência da cobertura | operador |
| Uma vez por ano (sugestão: julho, com o SIH do ano anterior completo) | Validação retrospectiva e retreinamento do modelo de demanda; ajuste de `FIM` em `climasenior/validacao.py` e dos períodos em `climasenior/demanda.py` para incluir o ano novo; registro das métricas novas | equipe técnica |
| A cada novo Censo | Apagar `data/ref/municipios_br.csv` para recarregar a população | equipe técnica |
| Após a pactuação | Ajustar `LIMIAR_ACAO` e `PESOS_IVC` em `climasenior/config.py` e as condutas em `site/index.html` (constante `FAIXAS`) | equipe técnica, com os gestores |

**Monitoramento do modelo (drift).** A cada retreinamento, compare as métricas de teste em
`modelos/demanda.json` com as anteriores, que ficam no histórico do Git. Retreine fora do
calendário se a razão observado/previsto anual sair da faixa de 0,9 a 1,1, ou se o erro por
estado e dia crescer mais de 20%.

## 6. Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Aviso "Previsão obtida para X de Y células" | limite diário do Open-Meteo ou instabilidade | nada; as execuções seguintes completam |
| "Observação (CPC) até" parada há semanas | a NOAA atrasou a publicação | nada; o modelo cobre os dias e é corrigido quando a observação chega |
| Fluxo de validação falhou num ano | instabilidade do FTP do DataSUS | rodar de novo; ou só a análise, com `reusar` = número da execução anterior |
| Painel em branco | `site/data/` não publicado | rodar "Atualizar ClimaSênior" em modo `painel` |

## 7. Integração com outros sistemas

Os arquivos JSON do painel são dados abertos e podem alimentar outros painéis, mensagens ou
rotinas (ver o Manual do usuário, "Dados abertos"). Para mensagens do Defesa Civil Alerta ou
boletins, a lista de municípios em alerta do dia está em `data/dia/AAAA-MM-DD.json`: municípios
com `ivc` maior ou igual ao limiar pactuado.

## 8. Executar localmente

```bash
pip install -r requirements-validacao.txt pytest
python -m pytest tests -q                          # testes sem rede
python -m climasenior.brasil                       # operação real (com acesso às fontes)
python -m climasenior.brasil --painel              # só recalcula o painel com os dados gravados
python -m http.server 8000 -d site                 # painel em http://localhost:8000
```
