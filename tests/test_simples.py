"""Experiência simples: início com pendências em linguagem comum e confirmação de previsões em um clique."""
from datetime import date, timedelta

from tests.conftest import criar_usuario, montar_processo, registrar


def _cenario(gestor, uid):
    est = gestor.post("/espacos", {"unidade_id": uid, "nome": "Estoque"}).json()
    cor = gestor.post("/espacos", {"unidade_id": uid, "nome": "Corte"}).json()
    gestor.c.put("/api/v1/distancias", headers=gestor.h, json={"origem_id": est["id"], "destino_id": cor["id"], "metros": 20})
    rec = gestor.post("/recursos", {"unidade_id": uid, "nome": "Serra", "capacidade": 60}).json()
    p = gestor.post("/processos", {"unidade_id": uid, "nome": "Corte"}).json()
    e = gestor.post(f"/processos/{p['id']}/etapas", {"nome": "Corte"}).json()
    ops = [gestor.post(f"/etapas/{e['id']}/operacoes", {
        "nome": n, "recurso_padrao_id": rec["id"], "espaco_origem_id": est["id"], "espaco_destino_id": cor["id"],
        "item_peso_kg": 5, "inicio_marco": "pega", "fim_marco": "solta"}).json()["id"] for n in ("Cortar", "Lixar")]
    return p["id"], ops


def test_inicio_vazio_orienta_a_configurar(gestor, operador):
    acoes = [a["codigo"] for a in gestor.get("/inicio").json()["acoes"]]
    assert acoes == ["configurar"]
    assert operador.get("/inicio").json()["acoes"] == []  # operador não recebe pendências de gestão


def test_inicio_lista_pendencias_em_linguagem_comum(gestor, unidade_id):
    pid, ops = _cenario(gestor, unidade_id)
    gestor.post(f"/processos/{pid}/modelar-tempos")
    r = gestor.get("/inicio").json()
    por = {a["codigo"]: a for a in r["acoes"]}
    assert por["previsoes"]["titulo"] == "2 previsões de tempo da IA para confirmar" and por["rascunhos"]["titulo"].startswith("1 processo")
    gestor.post(f"/processos/{pid}/publicar")
    o = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 5,
                                "prazo": (date.today() - timedelta(days=2)).isoformat()}).json()
    gestor.post(f"/ordens/{o['id']}/liberar")
    por = {a["codigo"]: a for a in gestor.get("/inicio").json()["acoes"]}
    assert por["atrasadas"]["titulo"] == "1 ordem atrasada" and por["atrasadas"]["nivel"] == "alerta"
    assert gestor.get("/inicio").json()["numeros"]["ordens_abertas"] == 1


def test_confirmar_previsoes_em_um_clique(admin, gestor, operador, unidade_id):
    pid, ops = _cenario(gestor, unidade_id)
    gestor.post(f"/processos/{pid}/modelar-tempos")
    assert operador.post(f"/processos/{pid}/confirmar-previsoes").status_code == 403
    assert gestor.post(f"/processos/{pid}/confirmar-previsoes").json() == {"confirmadas": 2}
    assert gestor.post(f"/processos/{pid}/confirmar-previsoes").json() == {"confirmadas": 0}  # idempotente
    for op in ops:
        assert gestor.get(f"/operacoes/{op}/estimativa?quantidade=10").json()["validada"] is True
    assert "previsoes" not in [a["codigo"] for a in gestor.get("/inicio").json()["acoes"]]
    eventos = [e["acao"] for e in admin.get("/auditoria?entidade=modelo_tempo&acao=modelo_tempo.validado").json()]
    assert eventos == ["modelo_tempo.validado"] * 2  # a confirmação em lote continua auditada, uma a uma


def test_prontidao_separa_o_que_e_simples_do_que_e_tecnico(gestor, unidade_id):
    pid, _ = montar_processo(gestor, unidade_id, publicar=False)
    itens = [i for o in gestor.get(f"/processos/{pid}/prontidao").json()["operacoes"] for i in o["itens"]]
    assert {i["categoria"] for i in itens} <= {"simples", "seguranca", "tecnico"}
    tecnicos = [i for i in itens if i["categoria"] == "tecnico"]
    assert any("perfil" in i["msg"].lower() for i in tecnicos)  # jargão fica fora da visão simples
    assert not any("NIOSH" in i["msg"] for i in itens if i["categoria"] == "simples")


def test_alerta_de_seguranca_continua_visivel_para_todos(gestor, unidade_id):
    p = gestor.post("/processos", {"unidade_id": unidade_id, "nome": "P"}).json()
    e = gestor.post(f"/processos/{p['id']}/etapas", {"nome": "E"}).json()
    gestor.post(f"/etapas/{e['id']}/operacoes", {"nome": "Carregar", "item_peso_kg": 70, "inicio_marco": "a", "fim_marco": "b",
                                                 "levantamento": {"carga_kg": 70}})
    itens = [i for o in gestor.get(f"/processos/{p['id']}/prontidao").json()["operacoes"] for i in o["itens"]]
    seg = [i for i in itens if i["categoria"] == "seguranca"]
    assert any("60 kg" in i["msg"] for i in seg)  # acima do limite de 60 kg
    assert not any(t in i["msg"] for i in seg for t in ("CLT", "AET", "NIOSH", "NR-"))  # texto simples, sem siglas
    assert any("CLT" in i["detalhe"] for i in seg)  # a referência normativa fica no detalhe


def test_inicio_isolado_por_empresa(client, gestor, unidade_id):
    _cenario(gestor, unidade_id)
    b = registrar(client, "Empresa B")
    assert b.get(f"/inicio?unidade_id={unidade_id}").status_code == 404
    assert [a["codigo"] for a in b.get("/inicio").json()["acoes"]] == ["configurar"]
