"""Isolamento entre empresas e entre unidades – o requisito mais crítico para uso por terceiros."""
from tests.conftest import criar_usuario, montar_processo, registrar


def _dados_a(admin, gestor, unidade_id):
    pid, ops = montar_processo(gestor, unidade_id)
    ordem = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 5,
                                    "cliente": "Cliente A"}).json()
    rec = gestor.post("/recursos", {"unidade_id": unidade_id, "nome": "Serra 1"}).json()
    gestor.post(f"/ordens/{ordem['id']}/liberar")
    return pid, ops, ordem, rec


def test_empresa_b_nao_acessa_nada_da_empresa_a(client, admin, gestor, unidade_id):
    pid, ops, ordem, rec = _dados_a(admin, gestor, unidade_id)
    oo = ordem["operacoes"][0]["id"]
    ap = gestor.post("/apontamentos/iniciar", {"ordem_operacao_id": oo}).json()
    b = registrar(client, "Empresa B")
    ub = b.usuario["unidade_ids"][0]

    # leitura
    for url in (f"/unidades/{unidade_id}", f"/processos/{pid}", f"/ordens/{ordem['id']}",
                f"/recursos/{rec['id']}", f"/ordens/{ordem['id']}/analise", f"/unidades/{unidade_id}/diagnostico"):
        assert b.get(url).status_code == 404, url
    # listas vêm vazias
    assert b.get("/ordens").json() == [] and b.get("/processos").json() == []
    assert b.get("/recursos").json() == [] and b.get("/apontamentos").json() == []
    # escrita
    assert b.post(f"/ordens/{ordem['id']}/cancelar", {"motivo": "invasão"}).status_code == 404
    assert b.post(f"/apontamentos/{ap['id']}/finalizar", {}).status_code == 404
    assert b.post("/apontamentos/iniciar", {"ordem_operacao_id": oo}).status_code == 404
    assert b.patch(f"/recursos/{rec['id']}", {"nome": "hack"}).status_code == 404
    assert b.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 1}).status_code == 404
    assert b.post("/ordens", {"unidade_id": ub, "processo_id": pid, "quantidade": 1}).status_code == 404
    assert b.get(f"/parametros?escopo_tipo=operacao&escopo_id={ops[0]}").status_code == 404
    assert b.post("/parametros", {"escopo_tipo": "operacao", "escopo_id": ops[0], "nome": "x", "valor_num": 1}).status_code == 404
    assert b.get(f"/dashboard?unidade_id={unidade_id}").status_code == 404
    assert b.patch(f"/usuarios/{gestor.usuario['id']}", {"ativo": False}).status_code == 404
    # auditoria da B não mostra eventos da A
    assert all(e["entidade_id"] != ordem["id"] or e["entidade"] != "ordem" for e in b.get("/auditoria").json())
    # a ordem da A segue intacta
    assert admin.get(f"/ordens/{ordem['id']}").json()["status"] == "em_producao"


def test_numeracao_de_ordens_por_empresa(client, admin, gestor, unidade_id):
    pid, _ = montar_processo(gestor, unidade_id)
    o1 = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 1}).json()
    o2 = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 1}).json()
    assert (o1["numero"], o2["numero"]) == ("OP-000001", "OP-000002")
    b = registrar(client, "Empresa B")
    gb = criar_usuario(b, "gestor", "g@b.com", b.usuario["unidade_ids"])
    pb, _ = montar_processo(gb, b.usuario["unidade_ids"][0])
    ob = gb.post("/ordens", {"unidade_id": b.usuario["unidade_ids"][0], "processo_id": pb, "quantidade": 1}).json()
    assert ob["numero"] == "OP-000001"


def test_restricao_por_unidade(client, admin, gestor, unidade_id):
    u2 = admin.post("/unidades", {"nome": "Filial"}).json()["id"]
    g_filial = criar_usuario(admin, "gestor", "gf@a.com", [u2])
    pid, _ = montar_processo(gestor, unidade_id)
    ordem = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 1}).json()
    assert g_filial.get(f"/ordens/{ordem['id']}").status_code == 404
    assert g_filial.get(f"/processos/{pid}").status_code == 404
    assert g_filial.get("/ordens").json() == []
    assert [u["id"] for u in g_filial.get("/unidades").json()] == [u2]
    assert g_filial.get(f"/unidades/{unidade_id}").status_code == 404
    assert g_filial.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 1}).status_code == 404
    # o gestor da matriz não vê a filial; o admin vê as duas
    assert gestor.get(f"/unidades/{u2}").status_code == 404
    assert len(admin.get("/unidades").json()) == 2


def test_nao_cruza_unidades_dentro_da_empresa(admin, gestor, unidade_id):
    u2 = admin.post("/unidades", {"nome": "Filial"}).json()["id"]
    pid, ops = montar_processo(gestor, unidade_id)
    r_filial = admin.post("/recursos", {"unidade_id": u2, "nome": "Máquina da filial"}).json()
    # recurso de outra unidade não pode ser usado no roteiro
    r = admin.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 1,
                               "recursos": [{"operacao_id": ops[0], "recurso_id": r_filial["id"]}]})
    assert r.status_code == 422
    # processo de uma unidade não gera ordem em outra
    assert admin.post("/ordens", {"unidade_id": u2, "processo_id": pid, "quantidade": 1}).status_code == 422


def test_operador_so_ve_seus_apontamentos_e_nao_decide(admin, gestor, operador, unidade_id):
    pid, _ = montar_processo(gestor, unidade_id)
    o = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 2}).json()
    gestor.post(f"/ordens/{o['id']}/liberar")
    oo = o["operacoes"][0]["id"]
    a_op = operador.post("/apontamentos/iniciar", {"ordem_operacao_id": oo}).json()
    operador.post(f"/apontamentos/{a_op['id']}/finalizar", {"quantidade_boa": 2})
    a_g = gestor.post("/apontamentos/iniciar", {"ordem_operacao_id": o["operacoes"][1]["id"]}).json()
    assert [a["id"] for a in operador.get("/apontamentos").json()] == [a_op["id"]]
    assert operador.post(f"/apontamentos/{a_g['id']}/finalizar", {}).status_code == 404
    assert operador.post(f"/apontamentos/{a_op['id']}/aprovar").status_code == 403
    assert operador.post(f"/apontamentos/{a_op['id']}/anular", {"motivo": "tentativa indevida"}).status_code == 403
    assert operador.get("/dashboard").status_code == 403
    assert operador.get("/auditoria").status_code == 403


def test_operador_nao_edita_estrutura(operador, unidade_id):
    assert operador.post("/processos", {"unidade_id": unidade_id, "nome": "X"}).status_code == 403
    assert operador.post("/recursos", {"unidade_id": unidade_id, "nome": "X"}).status_code == 403
    assert operador.post("/ordens", {"unidade_id": unidade_id, "processo_id": 1, "quantidade": 1}).status_code == 403
    assert operador.post("/ia/analises", {"tipo": "relatorio_gestor", "unidade_id": unidade_id}).status_code == 403
