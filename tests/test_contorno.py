"""Contorno físico mínimo: locais, distâncias, peças por hora e peso — o suficiente para a IA prever o tempo."""
from tests.conftest import registrar


def _processo(g, uid, publicar=False):
    p = g.post("/processos", {"unidade_id": uid, "nome": "Corte"}).json()
    e = g.post(f"/processos/{p['id']}/etapas", {"nome": "Corte"}).json()
    return p["id"], e["id"]


def test_sem_nada_pede_primeiro_os_locais(gestor, unidade_id):
    r = gestor.get(f"/contorno?unidade_id={unidade_id}").json()
    assert r["completo"] is False and r["tarefas"] == [] and any("locais" in f for f in r["faltando"])


def test_lista_o_que_falta_e_o_progresso_sobe_ate_completar(gestor, unidade_id):
    est = gestor.post("/espacos", {"unidade_id": unidade_id, "nome": "Estoque"}).json()
    cor = gestor.post("/espacos", {"unidade_id": unidade_id, "nome": "Corte"}).json()
    serra = gestor.post("/recursos", {"unidade_id": unidade_id, "nome": "Serra"}).json()
    pid, eid = _processo(gestor, unidade_id)
    ops = [gestor.post(f"/etapas/{eid}/operacoes", {"nome": n, "recurso_padrao_id": serra["id"],
                                                    "espaco_origem_id": est["id"], "espaco_destino_id": cor["id"]}).json()["id"]
           for n in ("Cortar", "Lixar")]
    r = gestor.get(f"/contorno?unidade_id={unidade_id}").json()
    textos = " | ".join(r["faltando"])
    assert "Peso da peça em 'Cortar'" in textos and "Peso da peça em 'Lixar'" in textos
    assert "Quantas peças por hora faz 'Serra'" in textos
    assert len([f for f in r["faltando"] if f.startswith("Distância")]) == 1  # o mesmo par conta uma vez
    assert r["pendentes"] == 4 and r["completo"] is False
    antes = r["progresso_pct"]

    assert gestor.c.put("/api/v1/distancias", headers=gestor.h, json={"origem_id": cor["id"], "destino_id": est["id"], "metros": 25}).status_code == 200
    assert gestor.patch(f"/recursos/{serra['id']}", {"capacidade": 60}).status_code == 200
    for op in ops:
        assert gestor.patch(f"/operacoes/{op}", {"item_peso_kg": 8}).status_code == 200
    r = gestor.get(f"/contorno?unidade_id={unidade_id}").json()
    assert r["pendentes"] == 0 and r["completo"] is True and r["progresso_pct"] == 100 > antes
    assert r["distancias"][0]["metros"] == 25 and r["tarefas"][0]["distancia_m"] == 25
    assert r["equipamentos"][0]["pecas_por_hora"] == 60

    # e com o contorno completo a IA já consegue prever o tempo (sem inventar nada além do declarado)
    m = gestor.post(f"/operacoes/{ops[0]}/modelo-tempo/gerar").json()
    est_ = gestor.get(f"/operacoes/{ops[0]}/estimativa?quantidade=10").json()
    assert est_["fonte"] == "modelo_ia" and est_["total_min"] > 0
    assert not any("Distância" in f or "Capacidade" in f or "Peso" in f for f in m["dados_faltantes"])


def test_um_local_so_pede_o_outro(gestor, unidade_id):
    est = gestor.post("/espacos", {"unidade_id": unidade_id, "nome": "Estoque"}).json()
    _, eid = _processo(gestor, unidade_id)
    gestor.post(f"/etapas/{eid}/operacoes", {"nome": "Mover", "espaco_origem_id": est["id"], "item_peso_kg": 3})
    r = gestor.get(f"/contorno?unidade_id={unidade_id}").json()
    assert any("De onde a peça sai e para onde vai" in f for f in r["faltando"])


def test_contorno_pode_ser_corrigido_em_processo_publicado_mas_a_estrutura_nao(gestor, unidade_id):
    est = gestor.post("/espacos", {"unidade_id": unidade_id, "nome": "Estoque"}).json()
    pid, eid = _processo(gestor, unidade_id)
    op = gestor.post(f"/etapas/{eid}/operacoes", {"nome": "Cortar"}).json()["id"]
    gestor.post(f"/processos/{pid}/publicar")
    assert gestor.patch(f"/operacoes/{op}", {"item_peso_kg": 12, "espaco_origem_id": est["id"], "num_pessoas": 2}).status_code == 200
    assert gestor.patch(f"/operacoes/{op}", {"nome": "Outro nome"}).status_code == 409  # estrutura segue fixa
    assert gestor.patch(f"/operacoes/{op}", {"item_peso_kg": 12, "nome": "x"}).status_code == 409  # misto também não passa
    tarefa = gestor.get(f"/contorno?unidade_id={unidade_id}").json()["tarefas"][0]
    assert tarefa["item_peso_kg"] == 12 and tarefa["status"] == "ativo"


def test_inicio_avisa_do_contorno_e_some_quando_completo(gestor, unidade_id):
    est = gestor.post("/espacos", {"unidade_id": unidade_id, "nome": "A"}).json()
    _, eid = _processo(gestor, unidade_id)
    op = gestor.post(f"/etapas/{eid}/operacoes", {"nome": "Mover"}).json()["id"]
    por = {a["codigo"]: a for a in gestor.get("/inicio").json()["acoes"]}
    assert por["contorno"]["link"] == "#/contorno" and "contorno físico" in por["contorno"]["titulo"]
    gestor.patch(f"/operacoes/{op}", {"item_peso_kg": 2})
    assert "contorno" not in [a["codigo"] for a in gestor.get("/inicio").json()["acoes"]]


def test_contorno_isolado_por_empresa(client, gestor, unidade_id):
    _processo(gestor, unidade_id)
    outra = registrar(client, "Outra Ltda")
    assert outra.get(f"/contorno?unidade_id={unidade_id}").status_code == 404
    assert outra.get(f"/contorno?unidade_id={outra.unidade_id}").json()["tarefas"] == []


def test_ia_pergunta_o_contorno_minimo_e_cria_os_locais(gestor, unidade_id):
    gestor.patch(f"/unidades/{unidade_id}", {"descricao_operacao": "Recebemos chapas, cortamos e montamos."})
    perguntas = []
    for _ in range(3):  # as rodadas cobrem todos os grupos
        perguntas += gestor.post(f"/unidades/{unidade_id}/diagnostico/perguntas/gerar").json()["perguntas"]
    textos = " ".join(p["texto"] for p in perguntas)
    assert "quantas peças ou unidades ela faz por hora" in textos  # capacidade das máquinas
    assert "Quanto pesa, em média, cada peça" in textos  # peso
    assert "lugares por onde o material passa" in textos  # locais
    resp = {p["texto"]: p["id"] for p in perguntas}
    lugares = next(i for t, i in resp.items() if t.startswith("Quais são os lugares"))
    gestor.patch(f"/diagnostico/perguntas/{lugares}", {"resposta": "Estoque, Bancada de corte, estoque a 20 m da bancada, Montagem"})
    rec = gestor.post(f"/unidades/{unidade_id}/diagnostico/estruturar").json()
    nomes = [e["nome"] for e in rec["conteudo"]["espacos"]]
    assert nomes == ["Estoque", "Bancada de corte", "Montagem"]  # item com número (distância) não vira local
