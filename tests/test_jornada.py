"""Trilha guiada: Atividades → Entradas → Agentes transformadores → Ambiente → Plano."""
from tests.conftest import registrar
from tests.test_plano import _cadastrar_contorno, _mesa

ATIV = ["movimentacao", "corte", "montagem", "inspecao"]  # sem borda e sem furação


def _estados(a, uid):
    return [p["estado"] for p in a.get(f"/jornada?unidade_id={uid}").json()["passos"]]


def _completar(a, uid, atividades=ATIV):
    """Percorre as quatro etapas como a pessoa faria."""
    assert a.patch(f"/unidades/{uid}", {"atividades": atividades}).status_code == 200
    _mesa(a)
    assert a.patch(f"/unidades/{uid}", {"equipe_pessoas": 2, "jornada": {"blocos": [["07:00", "11:00"], ["12:00", "16:00"]], "so_dias_uteis": True}}).status_code == 200
    _cadastrar_contorno(a, uid)


def test_unidade_nova_so_libera_a_primeira_etapa(admin, unidade_id):
    j = admin.get(f"/jornada?unidade_id={unidade_id}").json()
    assert [p["estado"] for p in j["passos"]] == ["atual", "bloqueado", "bloqueado", "bloqueado"] and j["completo"] is False
    assert [p["titulo"] for p in j["passos"]] == ["Atividades", "Entradas", "Agentes transformadores", "Ambiente"]
    assert j["proximo"]["link"] == "#/preparar/atividades"
    assert {a["codigo"] for a in j["catalogo"]} == {"movimentacao", "corte", "bordo", "furacao", "montagem", "inspecao"}
    assert admin.get("/jornada").json()["unidade_id"] == unidade_id  # sem parâmetro: a primeira unidade


def test_cada_etapa_libera_a_seguinte(admin, unidade_id):
    admin.patch(f"/unidades/{unidade_id}", {"atividades": ATIV})
    assert _estados(admin, unidade_id) == ["concluido", "atual", "bloqueado", "bloqueado"]
    assert "Cadastre o produto" in admin.get(f"/jornada?unidade_id={unidade_id}").json()["passos"][1]["pendencias"][0]
    _mesa(admin)
    assert _estados(admin, unidade_id) == ["concluido", "concluido", "atual", "bloqueado"]
    pend = admin.get(f"/jornada?unidade_id={unidade_id}").json()["passos"][2]["pendencias"]
    assert any("pessoas" in p for p in pend) and any("horário" in p for p in pend) and any("máquina que faz corte" in p for p in pend)
    admin.patch(f"/unidades/{unidade_id}", {"equipe_pessoas": 2, "jornada": {"blocos": [["08:00", "12:00"], ["13:00", "17:00"]]}})
    admin.post("/recursos", {"unidade_id": unidade_id, "nome": "Seccionadora", "funcao": "corte"})
    pend = admin.get(f"/jornada?unidade_id={unidade_id}").json()["passos"][2]["pendencias"]
    assert pend == ["Informe quantas peças por hora faz 'Seccionadora'."]
    serra = admin.get("/recursos").json()[0]
    admin.patch(f"/recursos/{serra['id']}", {"capacidade": 30})
    assert _estados(admin, unidade_id) == ["concluido", "concluido", "concluido", "atual"]
    pend = admin.get(f"/jornada?unidade_id={unidade_id}").json()["passos"][3]["pendencias"]
    assert any("estoque" in p for p in pend) and any("montagem" in p for p in pend) and any("em que local fica 'Seccionadora'" in p for p in pend)


def test_trilha_completa_leva_ao_plano(admin, unidade_id):
    _completar(admin, unidade_id)
    j = admin.get(f"/jornada?unidade_id={unidade_id}").json()
    assert j["completo"] is True and _estados(admin, unidade_id) == ["concluido"] * 4
    assert j["proximo"]["codigo"] == "novo_plano" and j["equipe_pessoas"] == 2
    assert admin.get(f"/inicio?unidade_id={unidade_id}").json()["acoes"][0]["link"] == "#/planos"


def test_plano_usa_equipe_e_horario_da_unidade_e_so_as_atividades_escolhidas(admin, unidade_id):
    _completar(admin, unidade_id)
    pid = admin.get("/produtos").json()[0]["id"]
    p = admin.post("/planos", {"produto_id": pid, "unidade_id": unidade_id, "quantidade": 2, "inicio": "2026-10-14T07:00:00-03:00"}).json()
    assert all(s["pessoas"] >= 2 for s in p["passos"])                         # equipe da unidade, sem perguntar de novo
    assert p["config"]["blocos"] == [["07:00", "11:00"], ["12:00", "16:00"]]   # horário da unidade
    assert {"corte", "montagem", "inspecao", "movimentacao"} >= {s["tipo"] for s in p["passos"]}
    # sem conferência final nas atividades, o passo não existe
    admin.patch(f"/unidades/{unidade_id}", {"atividades": ["movimentacao", "corte", "montagem"]})
    p = admin.post("/planos", {"produto_id": pid, "unidade_id": unidade_id, "quantidade": 2}).json()
    assert "inspecao" not in {s["tipo"] for s in p["passos"]}
    # pedido explícito ainda vence o padrão da unidade
    p = admin.post("/planos", {"produto_id": pid, "unidade_id": unidade_id, "pessoas": 5}).json()
    assert all(s["pessoas"] >= 5 for s in p["passos"])


def test_plano_nao_nasce_com_a_trilha_incompleta(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    admin.patch(f"/unidades/{unidade_id}", {"atividades": ATIV})                # falta equipe e horário
    r = admin.post("/planos", {"produto_id": pid, "unidade_id": unidade_id})
    assert r.status_code == 409 and "etapa 3" in r.json()["detail"] and "Agentes transformadores" in r.json()["detail"]
    assert admin.get("/planos").json() == []


def test_produto_pede_atividade_que_a_operacao_nao_tem(admin, unidade_id):
    admin.patch(f"/unidades/{unidade_id}", {"atividades": ATIV})                # sem furação
    pid, tampo, _ = _mesa(admin)
    admin.patch(f"/produtos/{pid}/componentes/{tampo['id']}", {"furos": 4})
    j = admin.get(f"/jornada?unidade_id={unidade_id}").json()
    assert j["passos"][1]["estado"] == "atual" and any("Furação" in p for p in j["passos"][1]["pendencias"])
    assert j["pendencias_produto"][str(pid)]
    admin.patch(f"/unidades/{unidade_id}", {"atividades": ATIV + ["furacao"]})
    assert admin.get(f"/jornada?unidade_id={unidade_id}").json()["passos"][1]["completo"] is True


def test_voltar_numa_etapa_trava_as_seguintes_de_novo(admin, unidade_id):
    _completar(admin, unidade_id)
    admin.patch(f"/unidades/{unidade_id}", {"atividades": ATIV + ["bordo"]})    # nova atividade exige máquina de borda
    assert _estados(admin, unidade_id) == ["concluido", "concluido", "atual", "bloqueado"]
    pend = admin.get(f"/jornada?unidade_id={unidade_id}").json()["passos"][2]["pendencias"]
    assert pend == ["Cadastre a máquina que faz colagem de borda."]


def test_distancia_que_falta_trava_o_ambiente(admin, unidade_id):
    admin.patch(f"/unidades/{unidade_id}", {"atividades": ATIV})
    _mesa(admin)
    admin.patch(f"/unidades/{unidade_id}", {"equipe_pessoas": 1, "jornada": {"blocos": [["08:00", "12:00"]]}})
    _cadastrar_contorno(admin, unidade_id, distancias=False)
    pend = admin.get(f"/jornada?unidade_id={unidade_id}").json()["passos"][3]["pendencias"]
    assert pend and all("distância" in p for p in pend)


def test_do_plano_a_ordem_o_proximo_passo_acompanha(admin, unidade_id):
    _completar(admin, unidade_id)
    pid = admin.get("/produtos").json()[0]["id"]
    plano = admin.post("/planos", {"produto_id": pid, "unidade_id": unidade_id}).json()
    prox = lambda: admin.get(f"/jornada?unidade_id={unidade_id}").json()["proximo"]  # noqa: E731
    assert prox()["codigo"] == "plano_conferir"
    admin.post(f"/planos/{plano['id']}/confirmar")
    assert prox()["codigo"] == "gerar_ordem"
    ordem = admin.post(f"/planos/{plano['id']}/gerar-ordem", {}).json()
    assert prox()["codigo"] == "liberar_ordem" and prox()["link"] == f"#/ordens/{ordem['id']}"
    admin.post(f"/ordens/{ordem['id']}/liberar")
    assert prox() is None                                                         # produzindo: sem convocação


def test_validacoes_e_isolamento(client, admin, unidade_id):
    assert admin.patch(f"/unidades/{unidade_id}", {"atividades": []}).status_code == 422
    assert admin.patch(f"/unidades/{unidade_id}", {"atividades": ["teletransporte"]}).status_code == 422
    assert admin.patch(f"/unidades/{unidade_id}", {"equipe_pessoas": 0}).status_code == 422
    assert admin.patch(f"/unidades/{unidade_id}", {"jornada": {"blocos": [["08:00", "12:00"], ["11:00", "17:00"]]}}).status_code == 422
    assert admin.patch(f"/unidades/{unidade_id}", {"jornada": {"blocos": [["10:00", "09:00"]]}}).status_code == 422
    assert admin.patch(f"/unidades/{unidade_id}", {"atividades": ["corte", "corte", "montagem"]}).json()["atividades"] == ["corte", "montagem"]
    b = registrar(client, "Empresa B")
    assert b.get(f"/jornada?unidade_id={unidade_id}").status_code == 404
    assert b.get("/jornada").json()["passos"][0]["estado"] == "atual"
