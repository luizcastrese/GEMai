#!/bin/sh
# Render (Python nativo): defina o start command como `sh start.sh`.
# Sem isso, o app ainda aplica migrações no lifespan quando o banco é Postgres.
set -eu
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
