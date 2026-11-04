"""Cache de estáticos, URL do Postgres e migrações na subida — o que o Render precisa."""
import logging

import psycopg
from alembic import command
from alembic.config import Config

from app.config import Settings, get_settings, normalizar_database_url
from app.main import html_com_versao, js_com_versao, versao_estaticos
from app.migrar import RAIZ, alinhar_esquema, aplicar_migracoes, precisa_stamp_head, revisao_head, url_postgres


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


def test_fluxo_simplificado_e_o_padrao_do_front(client):
    """PR #9 já tinha este fluxo; o teste impede o nav antigo (Dia a dia) de voltar no merge."""
    appjs = client.get("/static/app.js").text
    assert "['Plano de trabalho', '1. Produtos'" in appjs
    assert "['Plano de trabalho', '2. Oficina'" in appjs
    assert "['Plano de trabalho', '3. Planos de trabalho'" in appjs
    assert "Dia a dia" not in appjs
    assert "Contorno físico" not in appjs
    inicio = client.get("/static/telas_inicio.js").text
    assert "O produto" in inicio and "A oficina" in inicio
    assert "Ordens em andamento" not in inicio
    assert "O que precisa da sua atenção" not in inicio
    assert "Posso prometer esta data?" in client.get("/static/telas_plano.js").text
    assert "← Voltar ao passo a passo" in client.get("/static/telas_contorno.js").text


def test_modulos_js_recebem_cache_bust(client):
    v = versao_estaticos()
    js = client.get("/static/app.js").text
    assert f"./telas_inicio.js?v={v}" in js
    assert f"./api.js?v={v}" in js
    assert js_com_versao("import { get } from './api.js';", "abc") == "import { get } from './api.js?v=abc';"


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
    stamped, upgraded = [], []
    monkeypatch.setattr("app.migrar._nomes_tabelas", lambda url: set())
    monkeypatch.setattr("app.migrar._colunas", lambda url, tabela: set())
    monkeypatch.setattr("alembic.command.stamp", lambda cfg, rev: stamped.append(rev))
    monkeypatch.setattr("alembic.command.upgrade", lambda cfg, rev: upgraded.append(rev))
    assert aplicar_migracoes("sqlite://") is False
    assert stamped == upgraded == []
    assert aplicar_migracoes("postgresql+psycopg://u:p@localhost/db") is True
    assert stamped == [] and upgraded == ["head"]


def test_precisa_stamp_head():
    assert precisa_stamp_head({"empresas", "recursos"}, {"id", "capacidade_origem"})
    assert not precisa_stamp_head({"empresas", "alembic_version"}, {"capacidade_origem"})
    assert not precisa_stamp_head(set(), set())
    assert not precisa_stamp_head({"empresas", "recursos"}, {"id"})  # falta a coluna do 0010


def test_create_all_sem_alembic_version_recebe_stamp_head(tmp_path, monkeypatch):
    """Postgres do Render nasceu de create_all: tabelas no head, sem alembic_version."""
    from sqlalchemy import inspect, text

    from app.database import Base, criar_engine

    url = f"sqlite:///{tmp_path / 'legado.db'}"
    monkeypatch.setenv("ERP_DATABASE_URL", url)
    get_settings.cache_clear()
    eng = criar_engine(url)
    try:
        Base.metadata.create_all(eng)
        insp = inspect(eng)
        nomes = set(insp.get_table_names())
        assert "empresas" in nomes and "alembic_version" not in nomes
        assert "capacidade_origem" in {c["name"] for c in insp.get_columns("recursos")}
        assert alinhar_esquema(url) == "stamp"
        with eng.connect() as c:
            assert c.execute(text("select version_num from alembic_version")).scalar() == revisao_head()
        assert alinhar_esquema(url) == "upgrade"
        with eng.connect() as c:
            assert c.execute(text("select version_num from alembic_version")).scalar() == revisao_head()
    finally:
        eng.dispose()
        get_settings.cache_clear()


def test_psycopg_instalado():
    assert psycopg.connect  # driver usado em postgresql+psycopg://


def test_alembic_inprocess_nao_desliga_loggers(tmp_path, monkeypatch):
    """fileConfig do Alembic não pode desligar uvicorn/erp quando o upgrade roda no lifespan."""
    erp = logging.getLogger("erp")
    acesso = logging.getLogger("uvicorn.access")
    erp.disabled = acesso.disabled = False
    erp.setLevel(logging.INFO)
    monkeypatch.setenv("ERP_DATABASE_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    get_settings.cache_clear()
    try:
        cfg = Config(str(RAIZ / "alembic.ini"))
        cfg.set_main_option("script_location", str(RAIZ / "migrations"))
        command.upgrade(cfg, "head")
        assert erp.disabled is False and acesso.disabled is False
    finally:
        get_settings.cache_clear()
