"""Ciclo padrão ↔ fluxo: diagnóstico do desvio por etapa, leitura de cada atividade (corrigir o padrão ou o fluxo, critério de
Shewhart: estável × irregular), ajustes de método (ECRS) e alternativas recalculadas pelo motor."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import ciclo
from tests.test_piloto import _pedido
from tests.test_plano import _cadastrar_contorno, _mesa


# ------------------------------------------------------------------ leitura de uma atividade
@pytest.mark.parametrize("razoes,totais,leitura", [
    ([1.3, 1.31, 1.29, 1.3, 1.32], 0, "corrigir_padrao"),      # desvio estável: o padrão está otimista
    ([1.0, 1.6, 1.2, 2.0, 1.1], 0, "corrigir_fluxo"),          # acima do padrão e irregular: causas especiais
    ([1.05, 0.97, 1.02, 1.0], 0, "no_padrao"),                 # dentro de ±10 %
    ([1.5, 1.4], 0, "medir_mais"),                             # poucos pedidos
    ([1.3, 1.31, 1.29, 1.3], 3, "nivel_geral"),                # medido no total: não separa as atividades
    ([0.6, 0.9, 0.7, 1.0, 0.55], 0, "medir_mais"),             # abaixo do padrão mas instável
])
def test_leitura_padrao_ou_fluxo(razoes, totais, leitura):
    assert ciclo.classificar(razoes, totais)["leitura"] == leitura


# ------------------------------------------------------------------ pedido medido passo a passo
def _executar_passo_a_passo(a, ordem_id, fatores: dict[str, float], padrao=1.0):
    """Libera, aponta cada passo com duração = fator × previsto (padrão) e encerra. Equipe de 1: a própria pessoa aprova."""
    a.post(f"/ordens/{ordem_id}/liberar")
    o = a.get(f"/ordens/{ordem_id}").json()
    t = datetime.now(timezone.utc) - timedelta(days=2)
    for x in o["operacoes"]:
        prev = (x["tempo_prep_est_min"] or 0) + (x["tempo_exec_est_min"] or 0)
        mod = next((m for m in fatores if m in x["nome"].lower()), None)
        dur = prev * (fatores[mod] if mod else padrao)
        r = a.post("/apontamentos", {"ordem_operacao_id": x["id"], "tipo": "execucao", "inicio": t.isoformat(),
                                     "fim": (t + timedelta(minutes=dur)).isoformat(), "quantidade_boa": x["qtd_planejada"] or 1})
        assert r.status_code == 201, r.text
        assert a.post(f"/apontamentos/{r.json()['id']}/aprovar", {}).status_code == 200
        assert a.post(f"/ordens/{ordem_id}/operacoes/{x['id']}/concluir").status_code == 200
        t += timedelta(minutes=dur)
    assert a.post(f"/ordens/{ordem_id}/concluir").status_code == 200


@pytest.fixture
def mesa(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    return pid


def test_etapa_critica_aponta_o_fluxo_e_sugere_ecrs_e_alternativas(admin, unidade_id, mesa):
    plano, o = _pedido(admin, mesa, unidade_id)
    _executar_passo_a_passo(admin, o["id"], {"montar": 3.0})  # a montagem levou o triplo; o resto, o previsto
    c = admin.get(f"/planos/{plano['id']}/ciclo").json()
    crit = c["pedido"]["etapa_critica"]
    assert c["pedido"]["forma"] == "passo_a_passo" and crit["modulo"] == "montagem" and crit["parcela_do_excesso_pct"] == 100.0
    assert c["decisao"]["acao"] == "corrigir_fluxo" and c["decisao"]["foco"] == ["montagem"]
    assert {s["principio"] for s in c["sugestoes"]} == {"Combinar", "Reorganizar", "Simplificar"}
    assert all(not s["recalculado"] for s in c["sugestoes"]) and c["alternativas"] == []
    alt = admin.get(f"/planos/{plano['id']}/ciclo?alternativas=true").json()["alternativas"]
    assert alt and all(x["recalculado"] and x["prazo_min"] > 0 for x in alt)
    assert any(x["escolha"]["pessoas"] > 1 for x in alt)  # mais gente na montagem foi recalculado pelo motor


def test_pedido_no_padrao_mantem(admin, unidade_id, mesa):
    plano, o = _pedido(admin, mesa, unidade_id)
    _executar_passo_a_passo(admin, o["id"], {}, padrao=1.0)
    c = admin.get(f"/planos/{plano['id']}/ciclo").json()
    assert c["pedido"]["etapa_critica"] is None and c["pedido"]["desvio_pct"] == pytest.approx(0, abs=1)
    assert c["decisao"]["acao"] in ("medir_mais", "manter")  # com 1 pedido, ainda medir mais


def test_desvio_estavel_pede_corrigir_o_padrao(admin, unidade_id, mesa):
    ultimo = None
    for _ in range(3):  # todas as etapas 30 % acima, sempre: desvio sistemático
        ultimo, o = _pedido(admin, mesa, unidade_id)
        _executar_passo_a_passo(admin, o["id"], {}, padrao=1.3)
    c = admin.get(f"/planos/{ultimo['id']}/ciclo").json()
    leituras = {a["modulo"]: a["leitura"] for a in c["atividades"]}
    assert leituras["montagem"] == "corrigir_padrao" and c["decisao"]["acao"] == "corrigir_padrao" and c["sugestoes"] == []


def test_calibracao_avisa_quando_o_problema_e_o_fluxo(admin, unidade_id, mesa):
    for f in (1.0, 1.6, 1.2, 2.0, 1.1):
        _, o = _pedido(admin, mesa, unidade_id)
        _executar_passo_a_passo(admin, o["id"], {"montar": f})
    m = next(x for x in admin.post("/calibracao/modulos", {"unidade_id": unidade_id}).json()["modulos"]
             if x["modulo"] == "montagem" and x["produto_id"] is None)
    assert "FLUXO" in m["nota"]


def test_pedido_medido_no_total_so_da_o_nivel_geral(admin, unidade_id, mesa):
    plano, o = _pedido(admin, mesa, unidade_id)
    admin.post(f"/ordens/{o['id']}/terminar", {"horas": 2})
    c = admin.get(f"/planos/{plano['id']}/ciclo").json()
    assert c["pedido"]["forma"] == "total" and c["pedido"]["etapa_critica"] is None
