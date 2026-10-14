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

    @property
    def unidade_id(self) -> int:
        return self.get("/unidades").json()[0]["id"]

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


def criar_usuario(admin: Sessao, email, unidades=()):
    """Cria outro usuário da mesma empresa (todos têm o mesmo acesso; `unidades` opcionalmente restringe)."""
    r = admin.post("/usuarios", {"nome": email.split("@")[0].title(), "email": email, "senha": SENHA,
                                 "unidade_ids": list(unidades)})
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
    return admin.unidade_id


@pytest.fixture()
def gestor(admin, unidade_id):
    return criar_usuario(admin, "gestor@a.com", [unidade_id])


@pytest.fixture()
def operador(admin, unidade_id):
    return criar_usuario(admin, "op@a.com", [unidade_id])
