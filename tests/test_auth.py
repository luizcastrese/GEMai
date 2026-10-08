from app.config import get_settings
from tests.conftest import SENHA, criar_usuario, registrar


def test_registrar_e_login(client):
    s = registrar(client)
    assert s.get("/auth/eu").json()["perfil"] == "admin"
    r = client.post("/api/v1/auth/login", json={"email": "ADMIN@empresaa.com", "senha": SENHA})
    assert r.status_code == 200 and r.json()["usuario"]["empresa_id"] == s.usuario["empresa_id"]


def test_senha_fraca_e_email_duplicado(client):
    base = {"empresa_nome": "X", "unidade_nome": "U", "nome": "N", "email": "a@x.com"}
    assert client.post("/api/v1/auth/registrar", json={**base, "senha": "curta"}).status_code == 422
    assert client.post("/api/v1/auth/registrar", json={**base, "senha": "tudominusculo123"}).status_code == 422
    assert client.post("/api/v1/auth/registrar", json={**base, "senha": SENHA}).status_code == 201
    assert client.post("/api/v1/auth/registrar", json={**base, "empresa_nome": "Y", "senha": SENHA}).status_code == 409


def test_cadastro_publico_desabilitado(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "permitir_cadastro_publico", False)
    r = client.post("/api/v1/auth/registrar", json={"empresa_nome": "X", "unidade_nome": "U", "nome": "N",
                                                    "email": "a@x.com", "senha": SENHA})
    assert r.status_code == 403


def test_bloqueio_apos_tentativas(client, admin):
    for _ in range(get_settings().max_tentativas_login):
        r = client.post("/api/v1/auth/login", json={"email": "admin@empresaa.com", "senha": "errada-Errada1"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "admin@empresaa.com", "senha": SENHA})
    assert r.status_code == 423  # bloqueado mesmo com a senha certa


def test_mensagem_igual_para_usuario_inexistente(client, admin):
    a = client.post("/api/v1/auth/login", json={"email": "naoexiste@x.com", "senha": SENHA})
    b = client.post("/api/v1/auth/login", json={"email": "admin@empresaa.com", "senha": "errada-Errada1"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_sem_token_ou_token_invalido(client):
    assert client.get("/api/v1/unidades").status_code == 401
    assert client.get("/api/v1/unidades", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_troca_de_senha_invalida_tokens_antigos(client, admin):
    r = admin.post("/auth/alterar-senha", {"senha_atual": SENHA, "nova_senha": "Outra-Senha-456"})
    assert r.status_code == 204
    assert admin.get("/auth/eu").status_code == 401


def test_desativar_usuario_derruba_sessao(admin, unidade_id):
    op = criar_usuario(admin, "operador", "o@a.com", [unidade_id])
    assert op.get("/unidades").status_code == 200
    assert admin.patch(f"/usuarios/{op.usuario['id']}", {"ativo": False}).status_code == 200
    assert op.get("/unidades").status_code == 401


def test_nao_remove_ultimo_admin(admin):
    r = admin.patch(f"/usuarios/{admin.usuario['id']}", {"perfil": "gestor"})
    assert r.status_code == 409
    assert admin.patch(f"/usuarios/{admin.usuario['id']}", {"ativo": False}).status_code == 409


def test_apenas_admin_gerencia_usuarios(gestor, operador):
    assert gestor.get("/usuarios").status_code == 403
    assert operador.post("/usuarios", {"nome": "x", "email": "x@x.com", "senha": SENHA, "perfil": "admin"}).status_code == 403


def test_cabecalhos_de_seguranca(client):
    r = client.get("/api/v1/saude")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_secret_padrao_proibido_em_producao():
    import pytest
    from app.config import Settings
    with pytest.raises(ValueError):
        Settings(ambiente="producao")
    assert Settings(ambiente="producao", secret_key="x" * 40).producao
