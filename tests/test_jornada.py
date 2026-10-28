"""Primeiros passos: produto → oficina → plano → confirmar → produzir, deduzidos do que já foi cadastrado."""
from tests.test_plano import _cadastrar_contorno, _gerar, _mesa


def _jornada(a, u=None):
    return a.get("/jornada" + (f"?unidade_id={u}" if u else "")).json()


def _feitos(j):
    return [p["codigo"] for p in j["passos"] if p["feito"]]


def test_empresa_nova_comeca_no_passo_1(gestor, unidade_id):
    j = _jornada(gestor, unidade_id)
    assert [p["codigo"] for p in j["passos"]] == ["produto", "oficina", "plano", "confirmar", "ordem"]
    assert j["atual"] == 1 and j["feitos"] == 0 and j["total"] == 5
    assert j["passos"][0]["link"] == "#/produtos"
    assert gestor.get("/inicio").json()["jornada"]["atual"] == 1  # a tela inicial recebe o mesmo retrato


def test_produto_sem_componentes_leva_de_volta_ao_produto(gestor, unidade_id):
    pid = gestor.post("/produtos", {"nome": "Armário"}).json()["id"]
    j = _jornada(gestor, unidade_id)
    assert j["atual"] == 1 and j["passos"][0]["link"] == f"#/produtos/{pid}" and j["passos"][0]["botao"] == "Continuar o produto"


def test_o_caminho_todo_avanca_passo_a_passo(admin, unidade_id):
    pid, _, _ = _mesa(admin)
    assert _feitos(_jornada(admin, unidade_id)) == ["produto"] and _jornada(admin, unidade_id)["atual"] == 2
    _cadastrar_contorno(admin, unidade_id)
    assert _feitos(_jornada(admin, unidade_id)) == ["produto", "oficina"] and _jornada(admin, unidade_id)["atual"] == 3
    plano = _gerar(admin, pid, unidade_id)
    j = _jornada(admin, unidade_id)
    assert j["atual"] == 4 and j["passos"][3]["link"] == f"#/planos/{plano['id']}"
    assert admin.post(f"/planos/{plano['id']}/confirmar").status_code == 200
    j = _jornada(admin, unidade_id)
    assert j["atual"] == 5 and j["passos"][4]["link"] == f"#/planos/{plano['id']}"
    assert admin.post(f"/planos/{plano['id']}/gerar-ordem", {}).status_code == 201
    j = _jornada(admin, unidade_id)
    assert j["atual"] is None and j["feitos"] == 5


def test_plano_cancelado_nao_conta(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    plano = _gerar(admin, pid, unidade_id)
    admin.post(f"/planos/{plano['id']}/cancelar")
    assert "plano" not in _feitos(_jornada(admin, unidade_id))


def test_jornada_isolada_por_empresa(client, admin, unidade_id):
    from tests.conftest import registrar
    _mesa(admin)
    outra = registrar(client, "Outra Ltda")
    assert _jornada(outra)["feitos"] == 0
    assert outra.get(f"/jornada?unidade_id={unidade_id}").status_code == 404
