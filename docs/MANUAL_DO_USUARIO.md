# Manual do usuário

Painel: **https://mirandac559.github.io/climasenior/**. Funciona em qualquer navegador, no
computador e no celular, sem cadastro. Os dados se atualizam sozinhos todos os dias às 06:00 de
Brasília.

## Controles (topo)

| Controle | O que faz |
|---|---|
| **Data de referência** | Escolhe o dia. Vai de 1º de janeiro de 2026 até o último dia da previsão. Ao lado da data aparece a origem do dado: observado (NOAA), modelo dos dias recentes ou previsão. |
| **Limiar de ação** | IVC a partir do qual um município conta como "em alerta" (padrão 60). Mudá-lo recalcula os indicadores, a tabela e o protocolo. |
| **Área** | Brasil ou um estado. Indicadores, mapa, tabela e validação passam a ser da área escolhida. |
| **Município** | Digite o nome e escolha na lista. Os indicadores passam a ser do município. Para voltar à área, apague o campo ou clique em "Ver …" acima dos indicadores. |

## Indicadores

**Sem município escolhido (área):**

- **Municípios em alerta:** quantos estão com IVC igual ou acima do limiar.
- **IVC máximo:** o maior valor e onde ocorre.
- **Tmáx média:** temperatura máxima média entre os municípios.
- **Pessoas com 60+ em alerta:** soma da população idosa (Censo 2022) dos municípios em alerta.
- **Internações previstas de idosos:** internações de urgência por dia esperadas pelo modelo de
  demanda, somando todas as causas clínicas, com a parte por causas sensíveis ao calor.

**Com município escolhido:**

- posição no ranking da área;
- IVC e faixa do município;
- temperatura máxima e dias seguidos de onda de calor;
- pessoas com 60+ em alerta: toda a população idosa do município quando ele está em alerta, zero
  quando não está;
- internações previstas do município.

## Abas

**Situação.** O mapa mostra cada município na cor da sua faixa. Passe o mouse para ver os
detalhes e clique para abrir a série temporal. A tabela traz os 150 municípios de maior IVC.
**Baixar CSV** salva os dados do dia de todos os municípios da área (separador ";", abre no Excel).

**Série temporal.** Para o município escolhido, mostra:

- o IVC diário, com as faixas ao fundo e o limiar em vermelho; o trecho tracejado é a previsão;
- a temperatura máxima e a média de três dias, com o percentil 95 local, acima do qual começa a
  onda de calor.

**Protocolo.** Mostra as condutas por faixa e a lista dos municípios acima do limiar na data, com
a conduta de cada um. Com um município escolhido, mostra a conduta dele.

**Validação.** Mostra o que aconteceu de 2014 a 2025 quando o IVC atingiu o limiar. O seletor
"Causas de internação" troca o grupo de diagnósticos. Os blocos são:

- a frase-resumo e os indicadores: aumento das internações nos dias de alerta, internações a mais
  por ano e percentual de dias em alerta;
- **Risco por faixa:** quanto as internações sobem em cada faixa, em relação à BAIXA;
- **Escolha do limiar:** para cada limiar, quantos dias ficariam em alerta e quanto as internações
  sobem nesses dias. É a base para a pactuação com os gestores;
- **Internações e alertas, dia a dia:** a série de internações do ano escolhido, com os dias de
  alerta ao fundo e, de 2023 em diante, o previsto pelo modelo;
- **Em que dia o risco aparece:** o aumento no dia do alerta e nos sete seguintes;
- **Por região / Comparação:** os resultados por região, ou o estado comparado à sua região e ao
  Brasil;
- **Modelo de demanda:** o desempenho do modelo de aprendizado de máquina em 2025, ano que ele
  não viu no treino, e a calibração;
- **Dados do painel diário:** cobertura, data da observação e da previsão, qualidade dos dados.

Com um município escolhido, a validação mostra os resultados do estado dele.

## Como ler

- O IVC compara o calor com o que é habitual **no próprio lugar** e soma o peso da população
  idosa e da cobertura da atenção primária. Um IVC 70 em Curitiba e em Teresina significa risco
  semelhante, não a mesma temperatura.
- "Em alerta" é uma decisão de gestão (o limiar), não uma previsão de que algo vai acontecer a uma
  pessoa.
- As internações previstas são uma expectativa média. Use-as para dimensionar equipes, não como
  meta.

## Dados abertos

Os arquivos que alimentam o painel podem ser lidos por outros sistemas (Cemaden, Defesa Civil,
secretarias):

| Arquivo | Conteúdo |
|---|---|
| `data/meta.json` | data de referência, lista de dias, fontes, pesos, informações do modelo |
| `data/municipios.json` | códigos IBGE, nomes, UF, coordenadas, população, sensibilidade, capacidade |
| `data/dia/AAAA-MM-DD.json` | IVC de cada município, temperatura e onda de calor por célula, internações previstas (em centésimos) |
| `data/serie/AAAA/UF.json` | séries diárias por célula de cada estado |
| `data/validacao/resultados.json` | todos os resultados da validação e do modelo |

O endereço é o do painel seguido do caminho, por exemplo
`https://mirandac559.github.io/climasenior/data/meta.json`.
