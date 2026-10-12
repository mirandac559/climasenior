# Alternativa ao GitHub Actions: servidor da instituição.
# Atualiza ao iniciar, depois todo dia às 06:00 (horário de São Luís), e serve o painel na porta 8080.
FROM python:3.12-slim
ENV TZ=America/Fortaleza PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-operacional.txt .
RUN pip install --no-cache-dir -r requirements-operacional.txt \
    && apt-get update && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*
COPY climasenior/ climasenior/
COPY site/ site/
RUN echo '0 6 * * * cd /app && /usr/local/bin/python -m climasenior.operacional >> /var/log/climasenior.log 2>&1' \
      > /etc/cron.d/climasenior && chmod 0644 /etc/cron.d/climasenior && crontab /etc/cron.d/climasenior
VOLUME ["/app/data", "/app/site/data"]
EXPOSE 8080
CMD python -m climasenior.operacional; cron && python -m http.server 8080 -d site
