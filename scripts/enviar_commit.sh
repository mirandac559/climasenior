#!/usr/bin/env bash
# Envia ao main o commit desta execução, mesmo que outro commit tenha chegado enquanto ela rodava.
# Num conflito, prevalece o conteúdo desta execução: no rebase, "-X theirs" é o commit reaplicado.
set -u
ramo="${1:-main}"
for tentativa in 1 2 3 4 5; do
  if git pull -q --rebase -X theirs origin "$ramo" && git push -q origin "HEAD:$ramo"; then
    exit 0
  fi
  git rebase --abort 2>/dev/null || true
  echo "envio não concluído (tentativa $tentativa); nova tentativa em $((tentativa * 5)) s" >&2
  sleep $((tentativa * 5))
done
echo "não foi possível enviar o commit depois de 5 tentativas" >&2
exit 1
