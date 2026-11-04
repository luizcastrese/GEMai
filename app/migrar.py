"""Aplica migrações Alembic na subida do processo.

O serviço Python nativo no Render (`gemai-app`) inicia só o uvicorn; o Docker
`gemai` também sobrescreve o CMD do Dockerfile. Por isso o lifespan chama
`aplicar_migracoes` quando `ERP_DATABASE_URL` é Postgres.

Bancos criados com `Base.metadata.create_all` (modo desenvolvimento) têm o
esquema das models — igual ao head 0010 desde 56501996 — mas sem
`alembic_version`. `upgrade head` tentaria o 0001 e quebraria com
DuplicateTable. Nesse caso carimbamos head e só então fazemos upgrade.
"""
from __future__ import annotations

import logging
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
log = logging.getLogger("erp")

TABELA_APP = "empresas"
TABELA_ALEMBIC = "alembic_version"
COLUNA_HEAD = "capacidade_origem"  # 0010; create_all em 56501996 já a inclui


def url_postgres(url: str) -> bool:
    """True para postgres://, postgresql:// e postgresql+psycopg://."""
    return (url or "").strip().lower().startswith("postgres")


def precisa_stamp_head(tabelas: set[str], colunas_recursos: set[str] | None = None) -> bool:
    """Esquema vindo de create_all: tabelas da app sem histórico Alembic."""
    if TABELA_APP not in tabelas or TABELA_ALEMBIC in tabelas:
        return False
    if colunas_recursos is not None and COLUNA_HEAD not in colunas_recursos:
        return False
    return True


def _alembic_cfg():
    from alembic.config import Config
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "migrations"))
    return cfg


def revisao_head() -> str:
    from alembic.script import ScriptDirectory
    return ScriptDirectory.from_config(_alembic_cfg()).get_current_head()


def _nomes_tabelas(url: str) -> set[str]:
    from sqlalchemy import create_engine, inspect
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _colunas(url: str, tabela: str) -> set[str]:
    from sqlalchemy import create_engine, inspect
    engine = create_engine(url)
    try:
        insp = inspect(engine)
        if tabela not in insp.get_table_names():
            return set()
        return {c["name"] for c in insp.get_columns(tabela)}
    finally:
        engine.dispose()


def alinhar_esquema(url: str | None = None) -> str:
    """Stamp head se o banco já tem o esquema sem alembic_version; depois upgrade.

    Retorna \"stamp\" se carimbou, senão \"upgrade\".
    """
    if url is None:
        from .config import get_settings
        url = get_settings().database_url
    from alembic import command

    cfg = _alembic_cfg()
    tabelas = _nomes_tabelas(url)
    colunas = _colunas(url, "recursos") if "recursos" in tabelas else set()
    acao = "upgrade"
    if precisa_stamp_head(tabelas, colunas):
        log.info("Banco sem alembic_version (create_all legado); carimbando %s.", revisao_head())
        command.stamp(cfg, "head")
        acao = "stamp"
    command.upgrade(cfg, "head")
    return acao


def aplicar_migracoes(url: str | None = None) -> bool:
    """Alinha Alembic. Só age em Postgres; retorna True se aplicou."""
    if url is None:
        from .config import get_settings
        url = get_settings().database_url
    if not url_postgres(url):
        return False
    alinhar_esquema(url)
    return True
