"""Item final + peças + agentes + ambiente → a plataforma deduz as atividades e diz o que falta para o tempo."""
from tests.conftest import registrar
from tests.test_plano import _cadastrar_contorno, _mesa


def _prep(a, pid, uid):
    r = a.get(f"/produtos/{pid}/preparo?unidade_id={uid}")
    assert r.status_code == 200, r.text
    return r.json()


def _cods(p):
    return [x["codigo"] for x in p["atividades"]]


def _pend(p, secao):
    return next(s for s in p["secoes"] if s["codigo"] == secao)["pendencias"]


def test_item_sem_pecas_ainda_nao_tem_atividades(admin, unidade_id):
    pid = admin.post("/produtos", {"nome": "Armário"}).json()["id"]
    p = _prep(admin, pid, unidade_id)
    assert p["atividades"] == [] and p["pode_gerar"] is False
    assert _pend(p, "pecas") == ["Informe as peças de 'Armário'."]
    assert "Informe as peças primeiro" in _pend(p, "agentes")[0] and "Informe as peças primeiro" in _pend(p, "ambiente")[0]   # não finge que está pronto


def test_atividades_saem_das_pecas_e_nao_sao_perguntadas(admin, unidade_id):
    pid, tampo, lat = _mesa(admin)          # peças com medidas e uma ligação, sem furos nem borda
    assert _cods(_prep(admin, pid, unidade_id)) == ["movimentacao", "corte", "montagem", "inspecao"]
    admin.patch(f"/produtos/{pid}/componentes/{tampo['id']}", {"furos": 4, "bordas_m": 2.0})
    p = _prep(admin, pid, unidade_id)
    assert _cods(p) == ["movimentacao", "corte", "bordo", "furacao", "montagem", "inspecao"]
    assert next(a for a in p["atividades"] if a["codigo"] == "furacao")["pecas"] == 1   # só o tampo tem furos


def test_cada_atividade_cobra_o_seu_agente_e_o_seu_ambiente(admin, unidade_id):
    pid, tampo, _ = _mesa(admin)
    admin.patch(f"/produtos/{pid}/componentes/{tampo['id']}", {"furos": 4})
    p = _prep(admin, pid, unidade_id)
    assert _pend(p, "pecas") == []
    assert _pend(p, "agentes") == ["Cadastre a máquina que faz corte.", "Cadastre a máquina que faz furação."]
    assert any("estoque" in t for t in _pend(p, "ambiente")) and any("montagem" in t for t in _pend(p, "ambiente"))
    assert p["pendencias_total"] == 4
    # completa os agentes e o ambiente exatamente como a tela pede
    _cadastrar_contorno(admin, unidade_id)                                          # estoque, corte, montagem, seccionadora (30 un/h) e distâncias
    admin.post("/recursos", {"unidade_id": unidade_id, "nome": "Furadeira", "funcao": "furacao"})
    p = _prep(admin, pid, unidade_id)
    assert _pend(p, "agentes") == ["Informe quantas peças por hora faz 'Furadeira'."]
    assert _pend(p, "ambiente") == ["Diga em que local fica 'Furadeira'."]
    furadeira = next(r for r in admin.get("/recursos").json() if r["nome"] == "Furadeira")
    cor = next(e for e in admin.get("/espacos").json() if e["nome"] == "Corte")
    admin.patch(f"/recursos/{furadeira['id']}", {"capacidade": 40, "espaco_id": cor["id"]})
    p = _prep(admin, pid, unidade_id)
    assert p["pendencias_total"] == 0 and all(s["completo"] for s in p["secoes"]) and p["pode_gerar"] is True


def test_distancia_que_falta_aparece_no_ambiente(admin, unidade_id):
    pid, _, _ = _mesa(admin)
    _cadastrar_contorno(admin, unidade_id, distancias=False)
    pend = _pend(_prep(admin, pid, unidade_id), "ambiente")
    assert pend and all("distância" in t for t in pend)


def test_o_plano_sai_do_item_com_equipe_e_horario_da_unidade(admin, unidade_id):
    pid, _, _ = _mesa(admin)
    _cadastrar_contorno(admin, unidade_id)
    assert admin.patch(f"/unidades/{unidade_id}", {"equipe_pessoas": 2, "jornada": {"blocos": [["07:00", "11:00"], ["12:00", "16:00"]], "so_dias_uteis": True}}).status_code == 200
    p = admin.post("/planos", {"produto_id": pid, "unidade_id": unidade_id, "quantidade": 2, "inicio": "2026-10-14T07:00:00-03:00"}).json()
    assert all(s["pessoas"] >= 2 for s in p["passos"]) and p["config"]["blocos"] == [["07:00", "11:00"], ["12:00", "16:00"]]
    assert p["totais"]["completo"] is True and p["totais"]["tempo_padrao_min"] > 0
    outro = admin.post("/planos", {"produto_id": pid, "unidade_id": unidade_id, "pessoas": 5}).json()   # pedido explícito vence o padrão
    assert all(s["pessoas"] >= 5 for s in outro["passos"])


def test_horario_invalido_e_equipe_invalida_sao_recusados(admin, unidade_id):
    assert admin.patch(f"/unidades/{unidade_id}", {"equipe_pessoas": 0}).status_code == 422
    assert admin.patch(f"/unidades/{unidade_id}", {"jornada": {"blocos": [["08:00", "12:00"], ["11:00", "17:00"]]}}).status_code == 422
    assert admin.patch(f"/unidades/{unidade_id}", {"jornada": {"blocos": [["10:00", "09:00"]]}}).status_code == 422
    assert admin.patch(f"/unidades/{unidade_id}", {"atividades": ["corte"]}).status_code == 422   # atividade não é mais um dado de entrada


def test_proximo_passo_acompanha_item_plano_e_ordem(admin, unidade_id):
    prox = lambda: admin.get(f"/inicio?unidade_id={unidade_id}").json()["acoes"]  # noqa: E731
    assert prox()[0]["codigo"] == "proximo" and prox()[0]["link"] == "#/itens"
    pid, _, _ = _mesa(admin)
    _cadastrar_contorno(admin, unidade_id)
    assert prox()[0]["link"] == f"#/itens/{pid}" and "plano de trabalho" in prox()[0]["titulo"]
    plano = admin.post("/planos", {"produto_id": pid, "unidade_id": unidade_id}).json()
    assert prox()[0]["link"] == f"#/planos/{plano['id']}" and "Conferir" in prox()[0]["titulo"]
    admin.post(f"/planos/{plano['id']}/confirmar")
    assert "Gerar a ordem" in prox()[0]["titulo"]
    ordem = admin.post(f"/planos/{plano['id']}/gerar-ordem", {}).json()
    assert prox()[0]["link"] == f"#/ordens/{ordem['id']}"
    admin.post(f"/ordens/{ordem['id']}/liberar")
    assert prox() == []                                                           # produzindo: nada a convocar


def test_isolamento_entre_empresas(client, admin, unidade_id):
    pid, _, _ = _mesa(admin)
    b = registrar(client, "Empresa B")
    assert b.get(f"/produtos/{pid}/preparo?unidade_id={b.unidade_id}").status_code == 404
    assert b.get(f"/produtos/{pid}/preparo?unidade_id={unidade_id}").status_code == 404
