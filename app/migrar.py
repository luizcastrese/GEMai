"""Aplica migrações Alembic na subida do processo.

O serviço Python nativo no Render (`gemai-app`) inicia só o uvicorn; o Docker
`gemai` também sobrescreve o CMD do Dockerfile. Por isso o lifespan chama
`aplicar_migracoes` quando `ERP_DATABASE_URL` é Postgres.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def url_postgres(url: str) -> bool:
    """True para postgres://, postgresql:// e postgresql+psycopg://."""
    return (url or "").strip().lower().startswith("postgres")


def aplicar_migracoes(url: str | None = None) -> bool:
    """Roda `alembic upgrade head`. Só age em Postgres; retorna True se aplicou."""
    if url is None:
        from .config import get_settings
        url = get_settings().database_url
    if not url_postgres(url):
        return False
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(RAIZ / "alembic.ini"))
    command.upgrade(cfg, "head")
    return True
