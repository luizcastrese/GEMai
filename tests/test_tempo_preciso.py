"""Tempo mais preciso: histórico em tempo corrido, janela dos pedidos recentes, tamanho de amostra clássico, decomposição do erro
entre atividades e entre preparo e execução, e intervenções de método com antes × depois."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import OrdemOperacao
from app.services import calibracao_modulos as cal
from app.services import decomposicao as dec
from app.services import estimativa
from tests.test_piloto import _pedido
from tests.test_plano import _cadastrar_contorno, _mesa


# ------------------------------------------------------------------ histórico por operação em tempo corrido
def test_historico_conta_equipe_junta_uma_vez():
    t = datetime(2026, 1, 5, 8, tzinfo=timezone.utc)
    regs = [estimativa.Registro(1, 10, "execucao", 60.0, 10, t, t + timedelta(minutes=60)),
            estimativa.Registro(1, 11, "execucao", 60.0, 10, t, t + timedelta(minutes=60))]  # duas pessoas, mesmo intervalo, mesmas peças
    amostras, _ = estimativa.amostras_do_historico(regs, {1: 10}, "linear", None)
    assert amostras == [pytest.approx(6.0)]  # 60 min corridos ÷ 10 peças (antes: 120 min ÷ 20)
    seq = [estimativa.Registro(1, 10, "execucao", 30.0, 5, t, t + timedelta(minutes=30)),
           estimativa.Registro(1, 11, "execucao", 30.0, 5, t + timedelta(minutes=30), t + timedelta(minutes=60))]
    assert estimativa.amostras_do_historico(seq, {1: 10}, "linear", None)[0] == [pytest.approx(6.0)]  # sem sobreposição: igual a antes


# ------------------------------------------------------------------ janela e tamanho de amostra
def test_janela_fica_com_os_mais_recentes_e_n_classico():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    am = [cal.Amostra(1, "m", None, None, 1.0 + i / 100, quando=t + timedelta(days=i)) for i in range(40)]
    assert [a.razao for a in cal.recentes(am, 30)] == [1.0 + i / 100 for i in range(39, 9, -1)]
    assert cal.recentes(am, 0) == am
    # N' = (40·√(n·Σx² − (Σx)²) ÷ Σx)²: dispersão maior pede mais pedidos
    assert cal.amostras_recomendadas([1.0, 1.0, 1.0]) == 1
    assert cal.amostras_recomendadas([0.8, 1.2, 1.0, 1.4, 0.6]) > cal.amostras_recomendadas([0.95, 1.05, 1.0, 1.02, 0.98])


# ------------------------------------------------------------------ decomposição entre atividades
def _pedidos_sinteticos(fatores, n=8):
    """Pedidos com composições diferentes: corte (preparo fixo + execução que cresce) e montagem."""
    out = []
    for i in range(n):
        x = {("corte", "preparo"): 5.0, ("corte", "execucao"): 2.0 + 3 * i, ("montagem", "execucao"): 10.0 + (i % 3) * 4}
        out.append((x, sum(fatores.get(k, 1.0) * v for k, v in x.items())))
    return out


def test_decomposicao_acha_a_atividade_e_a_parte_com_erro():
    cols = {(c.modulo, c.parte): c for c in dec.estimar(_pedidos_sinteticos({("corte", "preparo"): 2.0}))}
    assert all(c.identificavel for c in cols.values())
    # o preparo do corte sai como o maior fator (puxado para o padrão pelo prior); as demais ficam perto de 1
    assert cols[("corte", "preparo")].fator > 1.4 and cols[("corte", "preparo")].fator == max(c.fator for c in cols.values())
    assert cols[("corte", "execucao")].fator == pytest.approx(1.0, abs=0.15) and cols[("montagem", "execucao")].fator == pytest.approx(1.0, abs=0.15)


def test_composicao_identica_nao_separa_nada():
    x = {("corte", "execucao"): 5.0, ("montagem", "execucao"): 10.0}
    cols = dec.estimar([(dict(x), 22.5)] * 6)
    assert cols and not any(c.identificavel for c in cols)
    assert dec.fator_da_atividade(cols, "corte") is None


@pytest.fixture
def mesa(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    return pid


def _prev(db_factory, ordem_id):
    db = db_factory()
    try:
        return [(x.modulo, x.previsto_normal_min or 0.0, x.tempo_prep_est_min or 0.0, x.tempo_exec_est_min or 0.0)
                for x in db.query(OrdemOperacao).filter(OrdemOperacao.ordem_id == ordem_id)]
    finally:
        db.close()


def test_pedidos_no_total_com_quantidades_diferentes_revelam_o_preparo(admin, unidade_id, mesa, db_factory):
    for q in (1, 2, 4, 8, 3, 6):
        p = admin.post("/planos", {"produto_id": mesa, "unidade_id": unidade_id, "quantidade": q, "inicio": "2026-10-14T08:00:00-03:00"}).json()
        c = admin.c.post(f"/api/v1/planos/{p['id']}/confirmar?abrir_pedido=true", headers=admin.h).json()
        real = 0.0  # verdade: o preparo leva o DOBRO; o resto, o previsto
        for _mod, normal, prep, exe in _prev(db_factory, c["ordem_id"]):
            fp = prep / (prep + exe) if prep + exe else 0
            real += normal * (fp * 2.0 + (1 - fp))
        assert admin.post(f"/ordens/{c['ordem_id']}/terminar", {"horas": real / 60}).status_code == 200
    m = next(x for x in admin.post("/calibracao/modulos", {"unidade_id": unidade_id}).json()["modulos"]
             if x["modulo"] == "corte" and x["produto_id"] is None)
    assert "DECOMPOSIÇÃO" in m["nota"] and "preparo" in m["nota"]
    ciclo = admin.get(f"/planos/{p['id']}/ciclo").json()
    corte = next(a for a in ciclo["atividades"] if a["modulo"] == "corte")
    assert corte["decomposicao"]["preparo"]["fator"] > corte["decomposicao"]["execucao"]["fator"]


# ------------------------------------------------------------------ intervenção de método: antes × depois
def test_intervencao_mede_antes_e_depois(admin, unidade_id, mesa, db_factory):
    planos = []
    for f in (1.5, 1.6):
        p, o = _pedido(admin, mesa, unidade_id)
        admin.post(f"/ordens/{o['id']}/terminar", {"horas": f * (o["tempo_estimado_min"] or 0) / 60})
        planos.append(p)
    assert admin.post(f"/planos/{planos[-1]['id']}/intervencoes", {"modulo": "inexistente", "principio": "Combinar", "descricao": "x"}).status_code == 422
    r = admin.post(f"/planos/{planos[-1]['id']}/intervencoes", {"modulo": "montagem", "principio": "Combinar", "descricao": "Montagem a dois"})
    assert r.status_code == 201 and r.json()["efeito"]["conclusivo"] is False  # ainda não há pedidos depois
    for f in (1.02, 0.98):
        _, o = _pedido(admin, mesa, unidade_id)
        admin.post(f"/ordens/{o['id']}/terminar", {"horas": f * (o["tempo_estimado_min"] or 0) / 60})
    e = admin.get(f"/produtos/{mesa}/intervencoes").json()[0]["efeito"]
    assert e["conclusivo"] and e["antes"]["pedidos"] == 2 and e["depois"]["pedidos"] == 2 and e["variacao_erro_pp"] < -40
    assert admin.get(f"/planos/{planos[-1]['id']}/ciclo").json()["intervencoes"][0]["principio"] == "Combinar"
    ind = admin.get("/pesquisa/indicadores").json()["intervencoes"]
    assert ind == {"registradas": 1, "conclusivas": 1, "melhoraram": 1, "variacao_mediana_erro_pp": e["variacao_erro_pp"]}
