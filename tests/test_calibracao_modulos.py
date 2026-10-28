"""Fase 6: calibração por módulo (fator multiplicativo validado por uma pessoa) e vínculo ordem ↔ módulo/passo."""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.models import Apontamento, Ordem, OrdemOperacao
from tests.conftest import FT, TEMPO_UNIDADE_MIN, criar_usuario, montar_processo, registrar
from tests.test_ritmo_historico import _pessoa

_n = iter(range(1, 10_000))


def _executar(gestor, admin, pid, minutos, qtd=10, pessoa_id=None, aprovar=True):
    """Cria uma ordem, executa a 1ª operação (retroativo), conclui e aprova. Devolve (ordem, ordem_operacao)."""
    o = gestor.post("/ordens", {"unidade_id": gestor.unidade_id, "processo_id": pid, "quantidade": qtd}).json()
    gestor.post(f"/ordens/{o['id']}/liberar")
    oo = o["operacoes"][0]
    ini = datetime.now(timezone.utc) - timedelta(days=1, hours=next(_n) % 20)
    corpo = {"ordem_operacao_id": oo["id"], "tipo": "execucao", "inicio": ini.isoformat(),
             "fim": (ini + timedelta(minutes=minutos)).isoformat(), "quantidade_boa": qtd}
    if pessoa_id:
        corpo["pessoa_id"] = pessoa_id
    a = gestor.post("/apontamentos", corpo)
    assert a.status_code == 201, a.text
    assert gestor.post(f"/ordens/{o['id']}/operacoes/{oo['id']}/concluir").status_code == 200
    if aprovar:
        assert admin.post(f"/apontamentos/{a.json()['id']}/aprovar").status_code == 200
    return o, oo


def _calibrar(a, **kw):
    r = a.post("/calibracao/modulos", kw)
    assert r.status_code == 200, r.text
    return r.json()


def _estimar_op(gestor, op_id, qtd=10):
    return gestor.get(f"/operacoes/{op_id}/estimativa?quantidade={qtd}").json()


# ------------------------------------------------------------------ vínculo da ordem com o módulo
def test_ordem_guarda_modulo_previsao_sem_calibracao_e_fracao_do_operador(admin, gestor, unidade_id):
    pid, ops = montar_processo(gestor, unidade_id)
    o = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 10}).json()
    db_oo = gestor.get(f"/ordens/{o['id']}").json()["operacoes"][0]
    assert db_oo["fonte_estimativa"] == "modulo" and db_oo["tempo_exec_est_min"] == pytest.approx(50 * FT, abs=0.01)


def test_previa_nao_grava_e_exige_o_minimo_de_amostras(admin, gestor, unidade_id):
    pid, _ = montar_processo(gestor, unidade_id)
    for _ in range(9):
        _executar(gestor, admin, pid, 60)  # 6 min/un contra 5 previstos
    d = _calibrar(gestor, unidade_id=unidade_id)
    assert d["aplicado"] is False and d["propostas"] == 0 and "POR MÓDULO" in d["aviso"] and d["criterios"] == {"min_amostras": 10, "limites": [0.5, 2.0]}
    m = d["modulos"][0]
    assert (m["modulo"], m["amostras"], m["minimo"], m["status"], m["fator_sugerido"]) == ("conferencia", 18 if False else 9, 10, "insuficiente", None)
    _executar(gestor, admin, pid, 60)
    m = _calibrar(gestor, unidade_id=unidade_id)["modulos"][0]
    assert m["status"] == "sugerido" and m["amostras"] == 10 and m["fator_sugerido"] == pytest.approx(1.2) and not m["limitado"]
    assert gestor.get("/calibracao/modulos").json() == []  # prévia não grava nada


def test_proposta_pendente_nao_vale_ate_ser_validada_depois_calibra_com_rotulo(admin, gestor, unidade_id):
    pid, ops = montar_processo(gestor, unidade_id)
    for _ in range(10):
        _executar(gestor, admin, pid, 60)
    antes = _estimar_op(gestor, ops[0])
    assert antes["fonte"] == "historico"  # 10 aprovadas: o histórico já vale; o módulo é a base calibrada para operações novas
    r = _calibrar(gestor, unidade_id=unidade_id, aplicar=True)
    assert r["aplicado"] and r["propostas"] == 1
    prop = gestor.get("/calibracao/modulos").json()[0]
    assert (prop["status"], prop["vigente"], prop["versao"], prop["amostras"]) == ("pendente", False, 1, 10) and prop["fator"] == pytest.approx(1.2)
    assert prop["mediana_bruta"] == pytest.approx(1.2)
    # nada mudou para o cálculo: o plano de um produto com a mesma operação ainda usa o módulo sem fator
    novo = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": pid, "quantidade": 10}).json()["operacoes"][0]
    assert novo["fonte_estimativa"] == "historico"
    d = admin.post(f"/calibracao/modulos/{prop['id']}/validar", {"observacao": "conferi"})
    assert d.status_code == 200 and d.json()["status"] == "validado" and d.json()["vigente"]
    assert admin.post(f"/calibracao/modulos/{prop['id']}/validar", {}).status_code == 409  # já decidida
    logs = admin.get("/auditoria", params={"acao": "calibracao_modulo."}).json()
    assert {l["acao"] for l in logs} == {"calibracao_modulo.propor", "calibracao_modulo.validar"}


def test_modulo_calibrado_multiplica_o_previsto_e_e_rotulado(admin, gestor, unidade_id):
    from tests.test_modulos import _op_com_modulo
    # operação NOVA com o mesmo módulo (sem histórico próprio): ganha o fator validado da unidade
    pid, _ = montar_processo(gestor, unidade_id)
    for _ in range(10):
        _executar(gestor, admin, pid, 60)
    _calibrar(gestor, unidade_id=unidade_id, aplicar=True)
    cid = gestor.get("/calibracao/modulos").json()[0]["id"]
    nova = _op_com_modulo(gestor, unidade_id, modulo="conferencia")
    base = _estimar_op(gestor, nova["id"])
    assert base["fonte"] == "modulo" and base["execucao_min"] == pytest.approx(50 * FT, abs=0.01)  # proposta pendente não entra
    assert admin.post(f"/calibracao/modulos/{cid}/validar", {}).status_code == 200
    cal = _estimar_op(gestor, nova["id"])
    assert cal["execucao_min"] == pytest.approx(50 * FT * 1.2, abs=0.01)
    # a ordem criada guarda a previsão SEM calibração e o fator aplicado (para não calibrar sobre a calibração)
    p2 = gestor.post("/processos", {"unidade_id": unidade_id, "nome": "P2"}).json()
    e2 = gestor.post(f"/processos/{p2['id']}/etapas", {"nome": "E"}).json()
    gestor.post(f"/etapas/{e2['id']}/operacoes", {"nome": "Conferir", "modulo": "conferencia"})
    gestor.post(f"/processos/{p2['id']}/publicar")
    o = gestor.post("/ordens", {"unidade_id": unidade_id, "processo_id": p2["id"], "quantidade": 10}).json()["operacoes"][0]
    assert o["tempo_exec_est_min"] == pytest.approx(50 * FT * 1.2, abs=0.01)
    from app.database import get_db
    db = next(gestor.c.app.dependency_overrides[get_db]())
    row = db.get(OrdemOperacao, o["id"])
    assert (row.modulo, row.fator_calibracao) == ("conferencia", pytest.approx(1.2)) and row.previsto_normal_min == pytest.approx(50.0, abs=0.01)
    assert row.fracao_operador == pytest.approx(1.0)
    db.close()


def test_limites_do_fator_e_normalizacao_pelo_ritmo(admin, gestor, unidade_id, db_factory):
    pid, _ = montar_processo(gestor, unidade_id)
    rapido = _pessoa(gestor, unidade_id, "Rápido", ritmo_pct=125)["id"]
    for i in range(10):  # 48 min feitos por quem tem ritmo 125 = 60 min normais; 6 sem pessoa/ritmo já valem 60 também
        _executar(gestor, admin, pid, 48, pessoa_id=rapido)
    m = _calibrar(gestor, unidade_id=unidade_id)["modulos"][0]
    assert m["fator_sugerido"] == pytest.approx(1.2)  # 60 ÷ 50, e não 48 ÷ 50 = 0,96
    pid2, _ = montar_processo(gestor, unidade_id)  # novo processo, mesmo módulo: mistura de amostras
    for _ in range(10):
        _executar(gestor, admin, pid2, 600)  # 12× o previsto
    m = next(x for x in _calibrar(gestor, unidade_id=unidade_id)["modulos"] if x["modulo"] == "conferencia")
    assert m["amostras"] == 20 and m["fator_sugerido"] == pytest.approx(2.0) and m["limitado"] is True  # mediana ≈ 6,6 ⇒ limitado a 2,0
    assert m["mediana_bruta"] > 2.0


def test_fator_abaixo_de_um_e_limite_inferior(admin, gestor, unidade_id):
    pid, _ = montar_processo(gestor, unidade_id)
    for _ in range(10):
        _executar(gestor, admin, pid, 10)  # 1 min/un contra 5: razão 0,2 ⇒ limitado a 0,5
    m = _calibrar(gestor, unidade_id=unidade_id)["modulos"][0]
    assert m["fator_sugerido"] == 0.5 and m["limitado"] and m["mediana_bruta"] == pytest.approx(0.2)


def test_so_conta_aprovado_nao_anulado_e_concluido(admin, gestor, unidade_id):
    pid, _ = montar_processo(gestor, unidade_id)
    for _ in range(9):
        _executar(gestor, admin, pid, 60)
    _executar(gestor, admin, pid, 60, aprovar=False)  # registrado, nunca aprovado: não conta
    assert _calibrar(gestor, unidade_id=unidade_id)["modulos"][0]["amostras"] == 9
    o, oo = _executar(gestor, admin, pid, 60)
    assert _calibrar(gestor, unidade_id=unidade_id)["modulos"][0]["amostras"] == 10
    ap = gestor.get(f"/apontamentos?ordem_id={o['id']}").json()[0]
    assert admin.post(f"/apontamentos/{ap['id']}/anular", {"motivo": "erro de digitação"}).status_code == 200
    assert _calibrar(gestor, unidade_id=unidade_id)["modulos"][0]["amostras"] == 9


def test_nova_proposta_substitui_a_pendente_e_rejeitar_nao_vale(admin, gestor, unidade_id):
    pid, _ = montar_processo(gestor, unidade_id)
    for _ in range(10):
        _executar(gestor, admin, pid, 60)
    _calibrar(gestor, unidade_id=unidade_id, aplicar=True)
    _calibrar(gestor, unidade_id=unidade_id, aplicar=True)
    props = gestor.get("/calibracao/modulos").json()
    assert [(p["versao"], p["status"]) for p in props] == [(2, "pendente"), (1, "rejeitado")]
    assert admin.post(f"/calibracao/modulos/{props[0]['id']}/rejeitar", {}).json()["status"] == "rejeitado"
    assert all(not p["vigente"] for p in gestor.get("/calibracao/modulos").json())


def test_validar_nova_versao_aposenta_a_vigente(admin, gestor, unidade_id):
    pid, _ = montar_processo(gestor, unidade_id)
    for _ in range(10):
        _executar(gestor, admin, pid, 60)
    _calibrar(gestor, unidade_id=unidade_id, aplicar=True)
    v1 = gestor.get("/calibracao/modulos").json()[0]["id"]
    admin.post(f"/calibracao/modulos/{v1}/validar", {})
    _calibrar(gestor, unidade_id=unidade_id, aplicar=True)
    v2 = gestor.get("/calibracao/modulos").json()[0]["id"]
    admin.post(f"/calibracao/modulos/{v2}/validar", {})
    por_versao = {c["versao"]: c for c in gestor.get("/calibracao/modulos").json()}
    assert por_versao[2]["vigente"] and not por_versao[1]["vigente"] and por_versao[1]["status"] == "validado"
    m = _calibrar(gestor, unidade_id=unidade_id)["modulos"][0]
    assert m["vigente"]["versao"] == 2


# ------------------------------------------------------------------ plano de trabalho
def test_plano_vincula_a_ordem_ao_passo_e_usa_calibracao_validada(admin, unidade_id, db_factory):
    from tests.test_plano import _cadastrar_contorno, _gerar, _mesa
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id)
    montar = next(s for s in p["passos"] if s["modulo"] == "montagem")
    assert montar["fator_calibracao"] == 1.0 and montar["amostras_calibracao"] == 0
    assert montar["previsto_normal_min"] == pytest.approx((3 * 0.174 + 8 * 0.30) * 2, abs=0.01)
    admin.post(f"/planos/{p['id']}/confirmar")
    o = admin.post(f"/planos/{p['id']}/gerar-ordem", {}).json()
    db = db_factory()
    oo = db.get(OrdemOperacao, next(x["id"] for x in o["operacoes"] if x["nome"] == montar["nome"]))
    assert oo.plano_passo_id == montar["id"] and oo.modulo == "montagem"
    assert oo.previsto_normal_min == pytest.approx(montar["previsto_normal_min"]) and oo.fator_calibracao == 1.0
    # 10 operações de montagem concluídas levaram 1,5× o previsto ⇒ fator 1,5 depois de validado
    emp, uni = admin.usuario["empresa_id"], unidade_id
    for i in range(10):
        ordem = Ordem(empresa_id=emp, unidade_id=uni, numero=f"CAL{i:03d}", quantidade=2, status="concluida")
        db.add(ordem)
        db.flush()
        x = OrdemOperacao(empresa_id=emp, ordem_id=ordem.id, sequencia=1, etapa_nome="Corpo", nome="Montar", qtd_planejada=2, status="concluida",
                          modulo="montagem", previsto_normal_min=10.0, fracao_operador=1.0)
        db.add(x)
        db.flush()
        ini = datetime(2026, 1, 5, 8, tzinfo=timezone.utc) + timedelta(hours=i)
        db.add(Apontamento(empresa_id=emp, unidade_id=uni, ordem_id=ordem.id, ordem_operacao_id=x.id, tipo="execucao", inicio=ini,
                           fim=ini + timedelta(minutes=15), quantidade_boa=2, status="aprovado", registrado_por=admin.usuario["id"]))
    db.commit()
    db.close()
    r = _calibrar(admin, unidade_id=unidade_id, aplicar=True)
    m = next(x for x in r["modulos"] if x["modulo"] == "montagem")
    assert m["fator_sugerido"] == pytest.approx(1.5) and m["amostras"] == 10
    cid = admin.get("/calibracao/modulos").json()[0]["id"]
    sem = _gerar(admin, pid, unidade_id)
    assert next(s for s in sem["passos"] if s["modulo"] == "montagem")["tempo_padrao_min"] == montar["tempo_padrao_min"]  # pendente não vale
    admin.post(f"/calibracao/modulos/{cid}/validar", {})
    com = _gerar(admin, pid, unidade_id)
    mc = next(s for s in com["passos"] if s["modulo"] == "montagem")
    assert mc["tempo_padrao_min"] == pytest.approx(montar["tempo_padrao_min"] * 1.5, abs=0.01)
    assert mc["fator_calibracao"] == 1.5 and mc["amostras_calibracao"] == 10
    assert mc["previsto_normal_min"] == pytest.approx(montar["previsto_normal_min"])  # a base da calibração não se contamina
    rot = next(c for c in mc["coeficientes"] if c["chave"] == "calibracao:montagem")
    assert rot["status"] == "calibrado" and "10 amostras" in rot["fonte"] and rot["valor"] == 1.5
    assert any("CALIBRADOS" in x and "montagem × 1.5" in x for x in com["premissas"])
    # os outros módulos seguem com coeficientes genéricos
    assert next(s for s in com["passos"] if s["modulo"] == "conferencia")["fator_calibracao"] == 1.0


# ------------------------------------------------------------------ acurácia por módulo, isolamento, migração
def test_painel_de_acuracia_por_modulo(admin, gestor, unidade_id):
    pid, _ = montar_processo(gestor, unidade_id)
    for _ in range(2):
        _executar(gestor, admin, pid, 60)
    d = gestor.get("/dashboard").json()["acuracia_por_modulo"]
    assert d[0]["modulo"] == "conferencia" and d[0]["operacoes"] == 2 and d[0]["operacoes_calibradas"] == 0
    assert d[0]["desvio_medio_pct"] == pytest.approx((60 / (10 * TEMPO_UNIDADE_MIN) - 1) * 100, abs=0.2)


def test_isolamento_e_escopo_de_unidade(client, admin, gestor, unidade_id):
    pid, _ = montar_processo(gestor, unidade_id)
    for _ in range(10):
        _executar(gestor, admin, pid, 60)
    _calibrar(gestor, unidade_id=unidade_id, aplicar=True)
    cid = gestor.get("/calibracao/modulos").json()[0]["id"]
    b = registrar(client, "Empresa B")
    assert b.post(f"/calibracao/modulos/{cid}/validar", {}).status_code == 404
    assert b.post("/calibracao/modulos", {"unidade_id": unidade_id}).status_code == 404
    assert b.post("/calibracao/modulos", {}).json()["modulos"] == [] and b.get("/calibracao/modulos").json() == []
    u2 = admin.post("/unidades", {"nome": "Filial"}).json()["id"]
    assert gestor.post("/calibracao/modulos", {"unidade_id": u2}).status_code == 404  # gestor só vê a unidade 1
    assert admin.post("/calibracao/modulos", {"unidade_id": u2}).json()["modulos"] == []
    assert gestor.post("/calibracao/modulos", {"unidade_id": unidade_id, "aplicar": True, "x": 1}).status_code == 422  # extra=forbid


def test_migracao_0009_sobe_e_desce_no_sqlite(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys
    db = tmp_path / "mig.db"
    env = {**os.environ, "ERP_DATABASE_URL": f"sqlite:///{db}"}
    raiz = os.path.dirname(os.path.dirname(__file__))

    def alembic(*args):
        r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=raiz, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-2000:]

    def colunas(tabela):
        with sqlite3.connect(db) as c:
            return {r[1] for r in c.execute(f"pragma table_info({tabela})")}

    alembic("upgrade", "0008")
    assert "plano_passo_id" not in colunas("ordem_operacoes") and not colunas("calibracoes_modulo")
    alembic("upgrade", "0009")
    assert {"plano_passo_id", "modulo", "previsto_normal_min", "fracao_operador", "fator_calibracao"} <= colunas("ordem_operacoes")
    assert {"previsto_normal_min", "fracao_operador", "fator_calibracao", "amostras_calibracao"} <= colunas("plano_passos")
    assert {"modulo", "fator", "amostras", "status", "vigente"} <= colunas("calibracoes_modulo")
    alembic("downgrade", "-1")
    assert "plano_passo_id" not in colunas("ordem_operacoes") and not colunas("calibracoes_modulo")
    alembic("upgrade", "head")
