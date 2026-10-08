import os

os.environ["ERP_DATABASE_URL"] = "sqlite://"
os.environ["ERP_AMBIENTE"] = "desenvolvimento"
os.environ["ERP_ANTHROPIC_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import ratelimit
from app.database import Base, criar_engine, get_db
from app.main import app

SENHA = "Senha-Forte-123"


@pytest.fixture()
def engine():
    eng = criar_engine("sqlite://")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(db_factory):
    def _get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    for rl in (ratelimit.limite_login, ratelimit.limite_cadastro, ratelimit.limite_ia):
        rl.reset()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class Sessao:
    """Atalho para chamadas autenticadas."""

    def __init__(self, client, token, usuario):
        self.c, self.usuario, self.h = client, usuario, {"Authorization": f"Bearer {token}"}

    def get(self, url, **kw):
        return self.c.get(f"/api/v1{url}", headers=self.h, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(f"/api/v1{url}", headers=self.h, json=json if json is not None else {}, **kw)

    def patch(self, url, json=None, **kw):
        return self.c.patch(f"/api/v1{url}", headers=self.h, json=json or {}, **kw)

    def delete(self, url, **kw):
        return self.c.delete(f"/api/v1{url}", headers=self.h, **kw)


def registrar(client, nome="Empresa A", email=None):
    email = email or f"admin@{nome.lower().replace(' ', '')}.com"
    r = client.post("/api/v1/auth/registrar", json={
        "empresa_nome": nome, "segmento": "Marcenaria", "unidade_nome": "Matriz",
        "nome": "Admin", "email": email, "senha": SENHA})
    assert r.status_code == 201, r.text
    d = r.json()
    return Sessao(client, d["access_token"], d["usuario"])


def criar_usuario(admin: Sessao, perfil, email, unidades):
    r = admin.post("/usuarios", {"nome": perfil.title(), "email": email, "senha": SENHA,
                                 "perfil": perfil, "unidade_ids": unidades})
    assert r.status_code == 201, r.text
    login = admin.c.post("/api/v1/auth/login", json={"email": email, "senha": SENHA})
    assert login.status_code == 200, login.text
    d = login.json()
    return Sessao(admin.c, d["access_token"], d["usuario"])


@pytest.fixture()
def admin(client):
    return registrar(client)


@pytest.fixture()
def unidade_id(admin):
    return admin.usuario["unidade_ids"][0]


@pytest.fixture()
def gestor(admin, unidade_id):
    return criar_usuario(admin, "gestor", "gestor@a.com", [unidade_id])


@pytest.fixture()
def operador(admin, unidade_id):
    return criar_usuario(admin, "operador", "op@a.com", [unidade_id])


def montar_processo(gestor: Sessao, unidade_id: int, *, tempo_unit=2.0, tempo_prep=10.0, publicar=True):
    """Processo com 2 etapas / 2 operações, parâmetros validados e (opcionalmente) publicado."""
    p = gestor.post("/processos", {"unidade_id": unidade_id, "nome": "Armário", "macroprocesso": "Produção"}).json()
    e1 = gestor.post(f"/processos/{p['id']}/etapas", {"nome": "Corte"}).json()
    e2 = gestor.post(f"/processos/{p['id']}/etapas", {"nome": "Montagem"}).json()
    o1 = gestor.post(f"/etapas/{e1['id']}/operacoes", {"nome": "Cortar chapas"}).json()
    o2 = gestor.post(f"/etapas/{e2['id']}/operacoes", {
        "nome": "Montar", "campos_extras": [{"nome": "temperatura", "tipo": "numero", "obrigatorio": False}]}).json()
    if tempo_unit is not None:
        for op in (o1, o2):
            assert gestor.post("/parametros", {"escopo_tipo": "operacao", "escopo_id": op["id"],
                                               "nome": "tempo_unitario_min", "valor_num": tempo_unit}).status_code == 201
            assert gestor.post("/parametros", {"escopo_tipo": "operacao", "escopo_id": op["id"],
                                               "nome": "tempo_preparacao_min", "valor_num": tempo_prep}).status_code == 201
    if publicar:
        r = gestor.post(f"/processos/{p['id']}/publicar")
        assert r.status_code == 200, r.text
    return p["id"], [o1["id"], o2["id"]]
