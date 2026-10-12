# Fase 3 — Protocolo de backtesting frente a eventos reais

## Objetivo
Verificar se o IVC teria acionado o protocolo de resposta com antecedência útil
nos episódios de calor efetivamente ocorridos no período de teste (2025), sem
gerar alarmes excessivos fora desses episódios.

## Definições operacionais
| Termo | Definição |
|---|---|
| Episódio de calor | ≥ 3 dias consecutivos com Tmáx acima do limiar térmico local (33 °C, calibrável) |
| Pico de demanda | Dia de maior número de atendimentos de idosos entre o início do episódio e D+5 |
| Detecção | IVC ≥ limiar de ação em algum dia entre D-3 do início do episódio e o pico |
| Antecedência | Dias entre a primeira detecção e o pico de demanda |
| Falso alarme | Dia com IVC ≥ limiar fora de qualquer janela [início-3, fim+3] de episódio |

## Métricas reportadas
- Sensibilidade por episódio (episódios detectados / episódios ocorridos)
- Antecedência média (dias)
- Taxa de falso alarme (dias de alarme fora de episódio / dias de alarme)
- Curva de limiares: sensibilidade × falso alarme para IVC ∈ {40, 50, 60, 70, 80}

## Execução
```bash
python -m climasenior.pipeline real     # com dados reais em data/real/
# resultados em modelos/resumo_v1.json e na aba "Validação" do dashboard
```

## Interpretação
A curva de limiares é o insumo da pactuação (instrumento 03). Não existe limiar
"ótimo" técnico: cada ponto da curva troca vidas potencialmente protegidas por
recursos mobilizados. A decisão cabe aos gestores responsáveis pela resposta.

## Reporte
Os valores obtidos com dados reais devem ser divulgados com intervalos de
confiança (bootstrap por episódio, 1.000 reamostragens) e acompanhados da lista
de episódios com data, duração e Tmáx, para auditoria.
