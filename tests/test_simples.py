"""Experiência simples: o Início conduz ao próximo passo e mostra os alertas em linguagem comum."""
from datetime import date, timedelta

from tests.conftest import registrar
from tests.helpers import montar_ordem


def test_inicio_vazio_orienta_a_informar_o_item(gestor, operador):
    acoes = gestor.get("/inicio").json()["acoes"]
    assert [a["codigo"] for a in acoes] == ["proximo"] and acoes[0]["link"] == "#/itens"
    assert [a["codigo"] for a in operador.get("/inicio").json()["acoes"]] == ["proximo"]  # mesma tela para todos


def test_inicio_lista_alertas_em_linguagem_comum(gestor, unidade_id):
    montar_ordem(gestor, unidade_id, prazo=(date.today() - timedelta(days=2)).isoformat(), liberar=True)
    por = {a["codigo"]: a for a in gestor.get("/inicio").json()["acoes"]}
    assert por["atrasadas"]["titulo"] == "1 ordem atrasada" and por["atrasadas"]["nivel"] == "alerta"
    assert gestor.get("/inicio").json()["numeros"]["ordens_abertas"] == 1


def test_inicio_isolado_por_empresa(client, gestor, unidade_id):
    montar_ordem(gestor, unidade_id)
    b = registrar(client, "Empresa B")
    assert b.get(f"/inicio?unidade_id={unidade_id}").status_code == 404
    assert [a["codigo"] for a in b.get("/inicio").json()["acoes"]] == ["proximo"]
