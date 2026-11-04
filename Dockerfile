FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY migrations migrations
COPY static static
COPY alembic.ini .
COPY start.sh .
RUN chmod 755 start.sh && useradd --system --uid 10001 erp && chown -R erp /srv
USER erp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/v1/saude', timeout=3)"
# Aplica migrações e sobe a API. Atrás de proxy reverso (HTTPS), ajuste FORWARDED_ALLOW_IPS.
# O serviço Docker no Render pode sobrescrever o CMD; o lifespan também migra em Postgres.
CMD ["./start.sh"]
