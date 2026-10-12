# Alternativa ao GitHub Actions: servidor da instituição.
# Atualiza ao iniciar, todo dia às 06:00 e completa lacunas a cada 2 horas (horário de Brasília), e serve o painel na porta 8080.
FROM python:3.12-slim
ENV TZ=America/Sao_Paulo PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-operacional.txt .
RUN pip install --no-cache-dir -r requirements-operacional.txt \
    && apt-get update && apt-get install -y --no-install-recommends cron tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*
COPY climasenior/ climasenior/
COPY site/ site/
RUN printf '%s\n' \
      '0 6 * * * cd /app && /usr/local/bin/python -m climasenior.brasil >> /var/log/climasenior.log 2>&1' \
      '30 */2 * * * cd /app && /usr/local/bin/python -m climasenior.brasil --complemento >> /var/log/climasenior.log 2>&1' \
      > /etc/cron.d/climasenior && chmod 0644 /etc/cron.d/climasenior && crontab /etc/cron.d/climasenior
VOLUME ["/app/data", "/app/site/data"]
EXPOSE 8080
CMD python -m climasenior.brasil; cron && python -m http.server 8080 -d site
