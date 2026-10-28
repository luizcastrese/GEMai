"""Fase 1: todo usuário ativo tem uma pessoa (quem executa) nas unidades em que atua."""
from datetime import datetime, timezone

from app.models import AuditLog, Pessoa, Usuario
from app.services import equipe
from tests.conftest import criar_usuario, montar_processo


def _pessoas(sessao, **qs):
    return sessao.get("/pessoas", params=qs).json()


def test_registrar_e_criar_usuario_criam_a_pessoa_vinculada(admin, unidade_id):
    ps = _pessoas(admin)
    assert [(p["nome"], p["usuario_id"], p["unidade_id"], p["ativo"]) for p in ps] == [("Admin", admin.usuario["id"], unidade_id, True)]
    u2 = admin.post("/unidades", {"nome": "Filial"}).json()["id"]
    restrito = criar_usuario(admin, "restrito@a.com", [unidade_id])  # só a unidade 1
    livre = criar_usuario(admin, "livre@a.com")  # sem restrição: todas as unidades ativas (1 e 2)
    por_usuario = {}
    for p in _pessoas(admin):
        por_usuario.setdefault(p["usuario_id"], set()).add(p["unidade_id"])
    assert por_usuario[restrito.usuario["id"]] == {unidade_id}
    assert por_usuario[livre.usuario["id"]] == {unidade_id, u2}
    assert admin.get("/auditoria", params={"acao": "pessoa.vincular_usuario"}).json()


def test_rotina_e_idempotente_e_nunca_sobrescreve(admin, unidade_id, db_factory):
    gestor = criar_usuario(admin, "gestor@a.com", [unidade_id])
    pessoa = next(p for p in _pessoas(admin) if p["usuario_id"] == gestor.usuario["id"])
    # o gestor renomeia a pessoa, define ritmo e a desativa de propósito
    assert admin.patch(f"/pessoas/{pessoa['id']}", {"nome": "Zé da Serra", "ritmo_pct": 110, "ativo": False}).status_code == 200
    antes = admin.get(f"/pessoas/{pessoa['id']}").json()
    r = admin.post("/pessoas/vincular-usuarios").json()
    assert r["criadas"] == 0  # nada novo: a pessoa desativada é respeitada
    assert admin.get(f"/pessoas/{pessoa['id']}").json() == antes  # nada alterado, nem reativado
    assert admin.post("/pessoas/vincular-usuarios").json()["criadas"] == 0


def test_rotina_cria_a_pessoa_de_usuario_existente_sem_vinculo(admin, unidade_id, db_factory):
    gestor = criar_usuario(admin, "gestor@a.com", [unidade_id])
    db = db_factory()
    db.query(Pessoa).filter(Pessoa.usuario_id == gestor.usuario["id"]).delete()  # usuário anterior à mudança
    db.commit()
    db.close()
    r = admin.post("/pessoas/vincular-usuarios").json()
    assert r["criadas"] == 1 and r["pessoas"][0]["nome"] == "Gestor"
    assert admin.post("/pessoas/vincular-usuarios").json()["criadas"] == 0


def test_usuario_inativo_nao_ganha_pessoa(admin, unidade_id, db_factory):
    db = db_factory()
    u = Usuario(empresa_id=admin.usuario["empresa_id"], nome="Saiu", email="saiu@a.com", senha_hash="x", ativo=False)
    db.add(u)
    db.commit()
    assert equipe.garantir_pessoas_do_usuario(db, u) == []
    db.close()


def test_apontamento_sem_pessoa_usa_a_vinculada_e_aceita_outra(admin, gestor, unidade_id, db_factory):
    pid, _ = montar_processo(gestor, unidade_id)
    o = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 5}).json()
    gestor.post(f"/ordens/{o['id']}/liberar")
    oo = o["operacoes"][0]["id"]
    # usuário antigo, sem pessoa: o apontamento cria o vínculo na hora (não bloqueia)
    db = db_factory()
    db.query(Pessoa).filter(Pessoa.usuario_id == gestor.usuario["id"]).delete()
    db.commit()
    db.close()
    a = gestor.post("/apontamentos/iniciar", {"ordem_operacao_id": oo, "tipo": "execucao"}).json()
    vinculada = next(p for p in _pessoas(gestor) if p["usuario_id"] == gestor.usuario["id"])
    assert a["pessoa_id"] == vinculada["id"]
    gestor.post(f"/apontamentos/{a['id']}/finalizar", {"quantidade_boa": 5})
    outra = gestor.post("/pessoas", {"unidade_id": unidade_id, "nome": "Colega"}).json()
    b = gestor.post("/apontamentos/iniciar", {"ordem_operacao_id": oo, "tipo": "execucao", "pessoa_id": outra["id"]}).json()
    assert b["pessoa_id"] == outra["id"]  # "Quem está executando?" prevalece sobre o padrão
