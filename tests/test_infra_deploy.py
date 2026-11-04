"""Cache de estáticos, URL do Postgres e migrações na subida — o que o Render precisa."""
import psycopg

from app.config import Settings, normalizar_database_url
from app.main import html_com_versao, versao_estaticos
from app.migrar import aplicar_migracoes, url_postgres


def test_cache_control_html_e_estaticos(client):
    v = versao_estaticos()
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    assert f'/static/style.css?v={v}' in r.text
    assert f'/static/app.js?v={v}' in r.text
    assert 'type="module"' in r.text
    css = client.get("/static/style.css")
    js = client.get("/static/app.js")
    assert css.status_code == js.status_code == 200
    assert css.headers["cache-control"] == js.headers["cache-control"] == "no-cache"


def test_api_continua_sem_cache_store(client):
    r = client.get("/api/v1/saude")
    assert r.headers["cache-control"] == "no-store"


def test_html_com_versao_so_nos_assets_de_entrada():
    bruto = '<link rel="stylesheet" href="/static/style.css">\n<script type="module" src="/static/app.js"></script>'
    assert html_com_versao(bruto, "abc123") == (
        '<link rel="stylesheet" href="/static/style.css?v=abc123">\n'
        '<script type="module" src="/static/app.js?v=abc123"></script>')


def test_normaliza_urls_postgres():
    assert normalizar_database_url("postgresql://u:p@h:5432/erp") == "postgresql+psycopg://u:p@h:5432/erp"
    assert normalizar_database_url("postgres://u:p@h:5432/erp") == "postgresql+psycopg://u:p@h:5432/erp"
    assert normalizar_database_url("postgresql+psycopg://u:p@h:5432/erp") == "postgresql+psycopg://u:p@h:5432/erp"
    assert normalizar_database_url("sqlite:///./erp.db") == "sqlite:///./erp.db"
    # Render costuma mandar sslmode=require na query string.
    s = Settings(database_url="postgresql://u:p@h:5432/erp?sslmode=require")
    assert s.database_url == "postgresql+psycopg://u:p@h:5432/erp?sslmode=require"
    maiuscula = Settings(database_url="PostgreSQL://u:p@h:5432/erp")
    assert maiuscula.database_url == "postgresql+psycopg://u:p@h:5432/erp"


def test_url_postgres_e_migracoes_nao_rodam_no_sqlite(monkeypatch):
    assert url_postgres("postgresql+psycopg://u:p@localhost/db")
    assert url_postgres("postgresql://u:p@localhost/db")
    assert url_postgres("postgres://u:p@localhost/db")
    assert not url_postgres("sqlite://")
    assert not url_postgres("sqlite:///./erp.db")
    called = []
    monkeypatch.setattr("alembic.command.upgrade", lambda cfg, rev: called.append(rev))
    assert aplicar_migracoes("sqlite://") is False
    assert called == []
    assert aplicar_migracoes("postgresql+psycopg://u:p@localhost/db") is True
    assert called == ["head"]


def test_psycopg_instalado():
    assert psycopg.connect  # driver usado em postgresql+psycopg://
