"""Histórico normalizado pelo ritmo da pessoa, tolerâncias do modelo preservadas e calibração do ritmo pela equipe."""
import itertools
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.models import Apontamento, AuditLog, Operacao, Ordem, OrdemOperacao, Pessoa
from app.services import estimativa
from app.services import modelo_tempo as mt
from app.services.ritmo import ritmo_efetivo
from tests.conftest import criar_usuario, registrar

FT = 1 / 0.91  # tolerâncias 5 % + 4 %
TOL = [{"categoria": "necessidades pessoais", "percentual": 5}, {"categoria": "fadiga básica", "percentual": 4}]
_numero = itertools.count(1)


# ------------------------------------------------------------------ montagem
def _operacao(gestor, uid, nome="Montar", **extra):
    p = gestor.post("/processos", {"unidade_id": uid, "nome": f"P {nome}"}).json()
    e = gestor.post(f"/processos/{p['id']}/etapas", {"nome": "E"}).json()
    r = gestor.post(f"/etapas/{e['id']}/operacoes", {"nome": nome, **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _pessoa(gestor, uid, nome, **kw):
    r = gestor.post("/pessoas", {"unidade_id": uid, "nome": nome, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _modelo(gestor, op, elementos, tolerancias=None):
    r = gestor.post(f"/operacoes/{op}/modelo-tempo", {"elementos": elementos, "tolerancias": tolerancias or []})
    assert r.status_code == 201, r.text


def _historico(db_factory, quem, operacao_id, unidade_id, ordens):
    """Cria ordens concluídas com apontamentos. `ordens`: lista de ordens; cada ordem é uma lista de dicts
    {pessoa, min, qtd, [status, anulado, tipo]} (um apontamento por dict, na mesma ordem_operacao)."""
    db = db_factory()
    t0 = datetime(2026, 1, 5, 8, tzinfo=timezone.utc)
    for apts in ordens:
        n = next(_numero)
        o = Ordem(empresa_id=quem["empresa_id"], unidade_id=unidade_id, numero=f"H{n:05d}", quantidade=sum(a["qtd"] for a in apts),
                  status="concluida")
        db.add(o)
        db.flush()
        oo = OrdemOperacao(empresa_id=o.empresa_id, ordem_id=o.id, operacao_id=operacao_id, sequencia=1, etapa_nome="E",
                           nome="Montar", qtd_planejada=o.quantidade, status="concluida")
        db.add(oo)
        db.flush()
        for i, a in enumerate(apts):
            ini = t0 + timedelta(hours=n * 3 + i)
            db.add(Apontamento(
                empresa_id=o.empresa_id, unidade_id=unidade_id, ordem_id=o.id, ordem_operacao_id=oo.id,
                tipo=a.get("tipo", "execucao"), pessoa_id=a.get("pessoa"), inicio=ini, fim=ini + timedelta(minutes=a["min"]),
                quantidade_boa=a["qtd"] if a.get("tipo", "execucao") == "execucao" else 0, status=a.get("status", "aprovado"),
                anulado=a.get("anulado", False), registrado_por=quem["id"]))
    db.commit()
    db.close()


def _estimar(db_factory, quem, operacao_id, quantidade=10):
    db = db_factory()
    try:
        return estimativa.estimar_operacao(db, quem["empresa_id"], db.get(Operacao, operacao_id), quantidade)
    finally:
        db.close()


def _n(pessoa, minutos, qtd=10, **kw):
    return {"pessoa": pessoa, "min": minutos, "qtd": qtd, **kw}


# ------------------------------------------------------------------ a) mistura 80/20 e normalização por apontamento
def test_mediana_normalizada_corrige_a_mistura_de_pessoas(admin, gestor, unidade_id, db_factory):
    op = _operacao(gestor, unidade_id)
    rapida = _pessoa(gestor, unidade_id, "Rápida", ritmo_pct=125)
    lenta = _pessoa(gestor, unidade_id, "Lenta", ritmo_pct=80)
    # todos fazem 1,0 min/un de TEMPO NORMAL: 0,8 × 1,25 = 1,25 × 0,8 = 1,0
    ordens = [[_n(rapida["id"], 8)] for _ in range(8)] + [[_n(lenta["id"], 12.5)] for _ in range(2)]
    _historico(db_factory, admin.usuario, op, unidade_id, ordens)

    db = db_factory()
    bruto, _ = estimativa.historico_operacao(db, admin.usuario["empresa_id"], op, "linear", None)
    db.close()
    assert sorted(bruto) == [0.8] * 8 + [1.25] * 2 and sum(bruto) / len(bruto) < 1  # a mediana bruta (0,8) é enviesada

    e = _estimar(db_factory, admin.usuario, op)
    assert e.fonte == "historico" and e.amostras == 10
    assert e.tempo_normal == pytest.approx(10.0)  # 1,0 min/un × 10 un
    assert e.exec == pytest.approx(10.0) and e.ritmo_normalizado and e.amostras_nao_normalizadas == 0


def test_normaliza_por_apontamento_quando_duas_pessoas_dividem_a_mesma_ordem(admin, gestor, unidade_id, db_factory):
    op = _operacao(gestor, unidade_id)
    rapida = _pessoa(gestor, unidade_id, "Rápida", ritmo_pct=125)
    lenta = _pessoa(gestor, unidade_id, "Lenta", ritmo_pct=80)
    ordens = [[_n(rapida["id"], 8)], [_n(lenta["id"], 12.5)],
              [_n(rapida["id"], 4, 5), _n(lenta["id"], 6.25, 5)]]  # 5 un de cada: 4 min e 6,25 min
    _historico(db_factory, admin.usuario, op, unidade_id, ordens)
    e = _estimar(db_factory, admin.usuario, op)
    # normalizado: 4×1,25 + 6,25×0,8 = 10 min para 10 un = 1,0 (a soma bruta daria 1,025)
    assert e.tempo_normal == pytest.approx(10.0)


# ------------------------------------------------------------------ b) fração que depende do operador
def test_ritmo_so_incide_na_parte_do_operador(admin, gestor, unidade_id, db_factory):
    op = _operacao(gestor, unidade_id)
    _modelo(gestor, op, [
        {"nome": "Manual", "tipo": "manuseio", "metodo": "fixo", "por_unidade": True, "a_min": 0.5},
        {"nome": "Máquina", "tipo": "processamento", "metodo": "fixo", "por_unidade": True, "a_min": 0.5,
         "depende_operador": False}], TOL)
    veloz = _pessoa(gestor, unidade_id, "Veloz", ritmo_pct=150)
    # observado 0,8 min/un; f = 0,5 ⇒ normal = 0,8 × (0,5 × 1,5 + 0,5) = 1,0 (e não 0,8 × 1,5 = 1,2)
    _historico(db_factory, admin.usuario, op, unidade_id, [[_n(veloz["id"], 8)] for _ in range(3)])
    e = _estimar(db_factory, admin.usuario, op)
    assert e.tempo_normal == pytest.approx(10.0)
    assert e.exec == pytest.approx(10.0 * FT)
    assert not any("assumido 100%" in a for a in e.avisos)
    assert not any("revise as premissas" in a for a in e.avisos)  # modelo (10 min normais) e histórico concordam


def test_fracao_operador_do_motor():
    c = mt.Contexto(quantidade=10)
    els = [{"nome": "m", "tipo": "manuseio", "metodo": "fixo", "por_unidade": True, "a_min": 0.5},
           {"nome": "q", "tipo": "processamento", "metodo": "fixo", "por_unidade": True, "a_min": 1.5, "depende_operador": False},
           {"nome": "p", "tipo": "preparacao", "metodo": "fixo", "a_min": 4}]
    fr = mt.fracao_operador(els, c)
    assert fr.execucao == pytest.approx(5 / 20) and fr.preparacao == 1.0 and fr.geral == pytest.approx(9 / 24)
    falta = mt.fracao_operador([{"nome": "d", "metodo": "deslocamento", "velocidade_m_min": 60}], c)
    assert falta.geral is None and falta.faltantes  # sem distância: não estima a fração


def test_sem_modelo_assume_tudo_dependente_do_operador_com_aviso(admin, gestor, unidade_id, db_factory):
    op = _operacao(gestor, unidade_id)
    veloz = _pessoa(gestor, unidade_id, "Veloz", ritmo_pct=150)
    _historico(db_factory, admin.usuario, op, unidade_id, [[_n(veloz["id"], 8)] for _ in range(3)])
    e = _estimar(db_factory, admin.usuario, op)
    assert e.tempo_normal == pytest.approx(12.0)  # f = 1: 0,8 × 1,5
    assert any("Sem módulo nem modelo: assumido 100% do tempo dependente do operador" in a for a in e.avisos)


# ------------------------------------------------------------------ c) tolerâncias
def test_tempo_padrao_e_normal_vezes_ft(admin, gestor, unidade_id, db_factory):
    op = _operacao(gestor, unidade_id)
    _modelo(gestor, op, [{"nome": "Montar", "tipo": "manuseio", "metodo": "fixo", "por_unidade": True, "a_min": 2}], TOL)
    p = _pessoa(gestor, unidade_id, "Normal", ritmo_pct=100)
    _historico(db_factory, admin.usuario, op, unidade_id, [[_n(p["id"], 20)] for _ in range(3)])
    e = _estimar(db_factory, admin.usuario, op)
    ft, pct = mt.fator_tolerancia(TOL)
    assert e.fonte == "historico" and e.tempo_normal == pytest.approx(20.0)
    assert e.exec == pytest.approx(e.tempo_normal * ft) and e.tolerancia_pct == pytest.approx(pct * 100)
    nomes = [d["nome"] for d in e.detalhe]
    assert any("necessidades pessoais" in n for n in nomes) and any("fadiga básica" in n for n in nomes)
    assert sum(d["minutos"] for d in e.detalhe if d["tipo"] in ("normal", "tolerancia")) == pytest.approx(e.exec, abs=0.005)
    api = gestor.get(f"/operacoes/{op}/estimativa?quantidade=10").json()
    assert api["fonte"] == "historico" and api["execucao_min"] == pytest.approx(20 * ft, abs=0.01)


def test_sem_modelo_nao_inventa_tolerancia(admin, gestor, unidade_id, db_factory):
    op = _operacao(gestor, unidade_id)
    p = _pessoa(gestor, unidade_id, "Normal", ritmo_pct=100)
    _historico(db_factory, admin.usuario, op, unidade_id, [[_n(p["id"], 20)] for _ in range(3)])
    e = _estimar(db_factory, admin.usuario, op)
    assert e.exec == pytest.approx(e.tempo_normal) and e.tolerancia_pct is None  # FT = 1
    assert any("Sem tolerâncias: tempo normal, não padrão" in a for a in e.avisos)


def test_avisa_quando_modelo_e_historico_divergem_mais_de_30_pct(admin, gestor, unidade_id, db_factory):
    op = _operacao(gestor, unidade_id)
    _modelo(gestor, op, [{"nome": "Montar", "tipo": "manuseio", "metodo": "fixo", "por_unidade": True, "a_min": 1}], TOL)
    p = _pessoa(gestor, unidade_id, "Normal", ritmo_pct=100)
    _historico(db_factory, admin.usuario, op, unidade_id, [[_n(p["id"], 20)] for _ in range(3)])  # 2 min/un contra 1 do modelo
    assert any("revise as premissas" in a for a in _estimar(db_factory, admin.usuario, op).avisos)


# ------------------------------------------------------------------ d) precedência do ritmo
def test_precedencia_pessoa_perfil_padrao():
    perfil = SimpleNamespace(ritmo_pct=120.0)
    assert ritmo_efetivo(SimpleNamespace(ritmo_pct=90.0), perfil) == (90.0, "pessoa")
    assert ritmo_efetivo(SimpleNamespace(ritmo_pct=None), perfil) == (120.0, "perfil")
    assert ritmo_efetivo(SimpleNamespace(ritmo_pct=None), None) == (100.0, "padrao")
    assert ritmo_efetivo(None, None).conhecido is False and ritmo_efetivo(None, perfil).origem == "perfil"


def test_historico_usa_pessoa_depois_perfil_e_conta_os_nao_normalizados(admin, gestor, unidade_id, db_factory):
    op = _operacao(gestor, unidade_id)
    perfil = gestor.post("/perfis-mao-de-obra", {"unidade_id": unidade_id, "nome": "Rápido", "ritmo_pct": 125}).json()
    so_perfil = _pessoa(gestor, unidade_id, "Só perfil", perfil_id=perfil["id"])
    ambos = _pessoa(gestor, unidade_id, "Ambos", perfil_id=perfil["id"], ritmo_pct=80)  # a pessoa prevalece sobre o perfil
    sem_nada = _pessoa(gestor, unidade_id, "Sem nada")
    assert so_perfil["ritmo_efetivo"] is None  # (criação não preenche) ...
    lista = {p["nome"]: p for p in gestor.get("/pessoas").json()}
    assert (lista["Só perfil"]["ritmo_efetivo"], lista["Só perfil"]["ritmo_efetivo_origem"]) == (125, "perfil")
    assert (lista["Ambos"]["ritmo_efetivo"], lista["Ambos"]["ritmo_efetivo_origem"]) == (80, "pessoa")
    assert (lista["Sem nada"]["ritmo_efetivo"], lista["Sem nada"]["ritmo_efetivo_origem"]) == (100, "padrao")
    ordens = [[_n(so_perfil["id"], 8)],  # 0,8 × 1,25 = 1,0
              [_n(ambos["id"], 12.5)],  # 1,25 × 0,8 = 1,0
              [_n(sem_nada["id"], 10)],  # sem ritmo: entra com 100 ⇒ 1,0
              [_n(None, 10)]]  # sem pessoa: idem
    _historico(db_factory, admin.usuario, op, unidade_id, ordens)
    e = _estimar(db_factory, admin.usuario, op)
    assert e.tempo_normal == pytest.approx(10.0) and e.amostras == 4
    assert e.amostras_nao_normalizadas == 2 and e.ritmo_normalizado
    assert any("2 de 4 apontamentos sem pessoa/ritmo, não normalizados" in a for a in e.avisos)
    assert any("mais de 30%" in a for a in e.avisos)  # 50 % sem normalizar: aviso reforçado


# ------------------------------------------------------------------ g) fonte, anulados e não aprovados
def test_fonte_historico_ignora_anulado_e_nao_aprovado(admin, gestor, unidade_id, db_factory):
    op = _operacao(gestor, unidade_id)
    p = _pessoa(gestor, unidade_id, "P", ritmo_pct=100)
    boas = [[_n(p["id"], 10)] for _ in range(3)]
    ruins = [[_n(p["id"], 100, anulado=True)], [_n(p["id"], 100, status="registrado")], [_n(p["id"], 100, status="rejeitado")]]
    _historico(db_factory, admin.usuario, op, unidade_id, boas + ruins)
    e = _estimar(db_factory, admin.usuario, op)
    assert e.fonte == "historico" and e.amostras == 3 and e.tempo_normal == pytest.approx(10.0)
    # só 2 aprovadas válidas: histórico insuficiente ⇒ não é mais a fonte
    op2 = _operacao(gestor, unidade_id, nome="Outra")
    _historico(db_factory, admin.usuario, op2, unidade_id, boas[:2] + ruins)
    assert _estimar(db_factory, admin.usuario, op2).fonte == "sem_base"


def test_preparacao_do_historico_tambem_vira_tempo_padrao(admin, gestor, unidade_id, db_factory):
    op = _operacao(gestor, unidade_id)
    _modelo(gestor, op, [{"nome": "Montar", "tipo": "manuseio", "metodo": "fixo", "por_unidade": True, "a_min": 1}], TOL)
    p = _pessoa(gestor, unidade_id, "P", ritmo_pct=100)
    _historico(db_factory, admin.usuario, op, unidade_id,
               [[_n(p["id"], 10), {"pessoa": p["id"], "min": 5, "qtd": 0, "tipo": "preparacao"}] for _ in range(3)])
    e = _estimar(db_factory, admin.usuario, op)
    assert e.prep == pytest.approx(5 * FT) and e.exec == pytest.approx(10 * FT) and e.tempo_normal == pytest.approx(15)


# ------------------------------------------------------------------ e) calibração
def _equipe(admin, gestor, unidade_id, db_factory, tempos, qtd_amostras=6, op=None):
    """tempos: {nome: min/un}. Cria as pessoas e `qtd_amostras` ordens de 10 un para cada uma."""
    op = op or _operacao(gestor, unidade_id)
    ids = {}
    for nome in tempos:
        ids[nome] = _pessoa(gestor, unidade_id, nome)["id"]
    _historico(db_factory, admin.usuario, op, unidade_id,
               [[_n(ids[nome], t * 10)] for nome, t in tempos.items() for _ in range(qtd_amostras)])
    return op, ids


def _pessoa_api(gestor, pid):
    return gestor.get(f"/pessoas/{pid}").json()


def test_calibracao_previa_nao_grava_e_aplicar_grava_e_audita(admin, gestor, unidade_id, db_factory):
    # referência = mediana de 18 amostras (6 × 0,8; 6 × 1,0; 6 × 1,25) = 1,0
    op, ids = _equipe(admin, gestor, unidade_id, db_factory, {"Ana": 0.8, "Bia": 1.0, "Caio": 1.25})
    r = gestor.post("/pessoas/calibrar-ritmo", {"unidade_id": unidade_id})
    assert r.status_code == 200, r.text
    previa = r.json()
    assert previa["aplicado"] is False and previa["aplicadas"] == 0 and "RELATIVO À EQUIPE" in previa["aviso"]
    nomes = [p["nome"] for p in previa["pessoas"]]
    assert nomes == sorted(nomes, key=str.lower)  # ordem alfabética, sem ranking (inclui as pessoas dos usuários)
    equipe = [p for p in previa["pessoas"] if p["nome"] in ("Ana", "Bia", "Caio")]
    assert {p["nome"]: p["ritmo_sugerido"] for p in equipe} == {"Ana": 125.0, "Bia": 100.0, "Caio": 80.0}
    assert all(p["status"] == "sugerido" and not p["aplicado"] and p["amostras"] == 6 for p in equipe)
    assert all(_pessoa_api(gestor, i)["ritmo_pct"] is None for i in ids.values())  # nada gravado
    db = db_factory()
    assert db.query(AuditLog).filter(AuditLog.acao == "pessoa.calibrar_ritmo").count() == 0

    r = gestor.post("/pessoas/calibrar-ritmo", {"unidade_id": unidade_id, "aplicar": True}).json()
    assert r["aplicado"] and r["aplicadas"] == 3
    ana = _pessoa_api(gestor, ids["Ana"])
    assert (ana["ritmo_pct"], ana["ritmo_origem"], ana["ritmo_amostras"]) == (125.0, "calibrado", 6)
    assert ana["ritmo_calibrado_em"] and ana["ritmo_efetivo"] == 125.0
    logs = db.query(AuditLog).filter(AuditLog.acao == "pessoa.calibrar_ritmo").all()
    assert len(logs) == 3 and {l.entidade_id for l in logs} == set(ids.values())
    assert logs[0].antes["ritmo_pct"] is None and logs[0].depois["ritmo_origem"] == "calibrado"
    db.close()
    # uma vez calibrada, a estimativa passa a normalizar com esses ritmos: 0,8 × 1,25 = 1,0
    e = _estimar(db_factory, admin.usuario, op)
    assert e.tempo_normal == pytest.approx(10.0) and e.amostras_nao_normalizadas == 0


def test_calibracao_nao_sobrescreve_ritmo_informado(admin, gestor, unidade_id, db_factory):
    op, ids = _equipe(admin, gestor, unidade_id, db_factory, {"Ana": 0.8, "Bia": 1.0, "Caio": 1.25})
    assert gestor.patch(f"/pessoas/{ids['Bia']}", {"ritmo_pct": 110}).status_code == 200
    bia = _pessoa_api(gestor, ids["Bia"])
    assert (bia["ritmo_pct"], bia["ritmo_origem"]) == (110, "informado")
    r = gestor.post("/pessoas/calibrar-ritmo", {"aplicar": True}).json()
    por_nome = {p["nome"]: p for p in r["pessoas"]}
    assert por_nome["Bia"]["status"] == "mantido" and not por_nome["Bia"]["aplicado"] and r["aplicadas"] == 2
    assert por_nome["Bia"]["ritmo_atual_origem"] == "informado"
    bia = _pessoa_api(gestor, ids["Bia"])
    assert (bia["ritmo_pct"], bia["ritmo_origem"], bia["ritmo_calibrado_em"]) == (110, "informado", None)
    # reenviar o mesmo valor calibrado (ex.: formulário) não troca a origem; informar outro, sim; null limpa
    assert gestor.patch(f"/pessoas/{ids['Ana']}", {"ritmo_pct": 125.0, "funcao": "Montador"}).status_code == 200
    assert _pessoa_api(gestor, ids["Ana"])["ritmo_origem"] == "calibrado"
    assert gestor.patch(f"/pessoas/{ids['Ana']}", {"ritmo_pct": 120}).json()["ritmo_origem"] == "informado"
    limpo = gestor.patch(f"/pessoas/{ids['Ana']}", {"ritmo_pct": None}).json()
    assert (limpo["ritmo_pct"], limpo["ritmo_origem"], limpo["ritmo_amostras"]) == (None, "", 0)


def test_calibracao_limita_a_50_150_e_respeita_os_minimos(admin, gestor, unidade_id, db_factory, monkeypatch):
    op, ids = _equipe(admin, gestor, unidade_id, db_factory, {"Rapido": 0.1, "N1": 1.0, "N2": 1.0, "Lento": 10.0})
    pouco = _pessoa(gestor, unidade_id, "Pouco")["id"]  # só 4 amostras (< 5)
    _historico(db_factory, admin.usuario, op, unidade_id, [[_n(pouco, 10)] for _ in range(4)])
    por_nome = {p["nome"]: p for p in gestor.post("/pessoas/calibrar-ritmo", {}).json()["pessoas"]}
    assert por_nome["Rapido"]["ritmo_sugerido"] == 150.0 and por_nome["Lento"]["ritmo_sugerido"] == 50.0  # limitado
    assert por_nome["Pouco"]["status"] == "insuficiente" and por_nome["Pouco"]["ritmo_sugerido"] is None
    assert "operações necessárias" in por_nome["Pouco"]["motivo"]
    # mínimo de operações distintas: com 2 exigidas e só 1 operação com dados, ninguém é calibrado
    monkeypatch.setattr(get_settings(), "min_operacoes_ritmo", 2)
    r = gestor.post("/pessoas/calibrar-ritmo", {"aplicar": True}).json()
    assert r["aplicadas"] == 0 and all(p["status"] == "insuficiente" for p in r["pessoas"])
    assert r["criterios"]["min_operacoes"] == 2 and r["criterios"]["min_amostras_pessoa"] == 5
    # com uma 2ª operação, as mesmas pessoas passam a atender ao mínimo
    op2 = _operacao(gestor, unidade_id, nome="Outra")
    _historico(db_factory, admin.usuario, op2, unidade_id,
               [[_n(ids[n], t * 10)] for n, t in {"Rapido": 0.5, "N1": 1.0, "N2": 1.0, "Lento": 2.0}.items() for _ in range(5)])
    r = gestor.post("/pessoas/calibrar-ritmo", {"aplicar": True}).json()
    assert r["operacoes_consideradas"] == 2
    ok = {p["nome"]: p["ritmo_sugerido"] for p in r["pessoas"] if p["status"] == "sugerido"}
    assert ok["Rapido"] == 150.0 and ok["N1"] == 100.0 and ok["Lento"] == 50.0


def test_calibracao_ignora_operacao_de_uma_pessoa_so(admin, gestor, unidade_id, db_factory):
    op, ids = _equipe(admin, gestor, unidade_id, db_factory, {"Sozinha": 1.0})
    r = gestor.post("/pessoas/calibrar-ritmo", {}).json()
    sozinha = next(p for p in r["pessoas"] if p["nome"] == "Sozinha")
    assert r["operacoes_consideradas"] == 0 and sozinha["status"] == "insuficiente"
    assert r["operacoes_ignoradas"] and "só uma pessoa" in r["operacoes_ignoradas"][0]


# ------------------------------------------------------------------ f) isolamento e validação
def test_isolamento_de_perfil_e_pessoa_entre_empresas_e_unidades(client, admin, gestor, unidade_id, db_factory):
    u2 = admin.post("/unidades", {"nome": "Filial"}).json()["id"]
    perfil_u2 = admin.post("/perfis-mao-de-obra", {"unidade_id": u2, "nome": "Filial"}).json()
    perfil_ok = gestor.post("/perfis-mao-de-obra", {"unidade_id": unidade_id, "nome": "Matriz"}).json()
    assert gestor.post("/pessoas", {"unidade_id": unidade_id, "nome": "X", "perfil_id": perfil_u2["id"]}).status_code == 422  # outra unidade
    b = registrar(client, "Empresa B")
    perfil_b = b.post("/perfis-mao-de-obra", {"unidade_id": b.unidade_id, "nome": "B"}).json()
    r = gestor.post("/pessoas", {"unidade_id": unidade_id, "nome": "Y", "perfil_id": perfil_b["id"]})
    assert r.status_code == 422  # outra empresa (como em plano.py)
    assert gestor.post("/pessoas", {"unidade_id": unidade_id, "nome": "Z", "perfil_id": 99999}).status_code == 422
    p = gestor.post("/pessoas", {"unidade_id": unidade_id, "nome": "Ok", "perfil_id": perfil_ok["id"]})
    assert p.status_code == 201 and p.json()["perfil_id"] == perfil_ok["id"]
    pid = p.json()["id"]
    assert gestor.patch(f"/pessoas/{pid}", {"perfil_id": perfil_b["id"]}).status_code == 422
    assert gestor.patch(f"/pessoas/{pid}", {"perfil_id": perfil_u2["id"]}).status_code == 422
    # pessoa de outra empresa: 404
    pb = b.post("/pessoas", {"unidade_id": b.unidade_id, "nome": "PB"}).json()
    assert gestor.get(f"/pessoas/{pb['id']}").status_code == 404
    assert gestor.patch(f"/pessoas/{pb['id']}", {"ritmo_pct": 100}).status_code == 404
    # unidade alheia na calibração: 404; e a calibração de A nunca lista pessoas de B
    assert gestor.post("/pessoas/calibrar-ritmo", {"unidade_id": b.unidade_id}).status_code == 404
    assert gestor.post("/pessoas/calibrar-ritmo", {"unidade_id": u2}).status_code == 404  # gestor só vê a unidade 1
    nomes = [x["nome"] for x in gestor.post("/pessoas/calibrar-ritmo", {}).json()["pessoas"]]
    assert "PB" not in nomes


def test_ritmo_da_pessoa_valida_50_a_150(gestor, unidade_id):
    for v in (49.9, 150.1, 0, -10):
        assert gestor.post("/pessoas", {"unidade_id": unidade_id, "nome": "R", "ritmo_pct": v}).status_code == 422
    p = gestor.post("/pessoas", {"unidade_id": unidade_id, "nome": "R", "ritmo_pct": 150})
    assert p.status_code == 201 and p.json()["ritmo_origem"] == "informado"
    assert gestor.patch(f"/pessoas/{p.json()['id']}", {"ritmo_pct": 151}).status_code == 422
    assert gestor.post("/pessoas", {"unidade_id": unidade_id, "nome": "S", "campo_extra": 1}).status_code == 422  # extra=forbid
    assert gestor.post("/pessoas/calibrar-ritmo", {"aplicar": True, "x": 1}).status_code == 422


def test_ritmo_nao_aparece_no_dashboard_nem_na_comparacao_de_condicoes(admin, gestor, unidade_id, db_factory):
    op, _ = _equipe(admin, gestor, unidade_id, db_factory, {"Ana": 0.8, "Bia": 1.25})
    gestor.post("/pessoas/calibrar-ritmo", {"aplicar": True})
    assert "ritmo" not in gestor.get("/dashboard").text.lower()
    assert "ritmo" not in gestor.get(f"/analise/comparacao?operacao_id={op}").text.lower()


# ------------------------------------------------------------------ h) migração 0006
def test_migracao_0006_sobe_e_desce_no_sqlite(tmp_path):
    db = tmp_path / "mig.db"
    env = {**os.environ, "ERP_DATABASE_URL": f"sqlite:///{db}"}
    raiz = os.path.dirname(os.path.dirname(__file__))

    def alembic(*args):
        r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=raiz, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-2000:]

    def colunas():
        with sqlite3.connect(db) as c:
            return {r[1] for r in c.execute("pragma table_info(pessoas)")}

    novas = {"perfil_id", "ritmo_pct", "ritmo_origem", "ritmo_amostras", "ritmo_calibrado_em"}
    alembic("upgrade", "0005")
    assert not novas & colunas()
    alembic("upgrade", "0006")
    assert novas <= colunas()
    with sqlite3.connect(db) as c:
        fks = [r[2] for r in c.execute("pragma foreign_key_list(pessoas)")]
    assert "perfis_mao_de_obra" in fks
    alembic("downgrade", "-1")
    assert not novas & colunas()
    alembic("upgrade", "head")
    assert novas <= colunas()


def test_calibracao_so_enxerga_operacoes_das_unidades_autorizadas(admin, gestor, unidade_id, db_factory):
    u2 = admin.post("/unidades", {"nome": "Filial"}).json()["id"]
    op2 = _operacao(admin, u2, nome="Operação da Filial")
    ids = {n: _pessoa(admin, u2, n)["id"] for n in ("Ana", "Bia")}
    _historico(db_factory, admin.usuario, op2, u2, [[_n(ids[n], t * 10)] for n, t in {"Ana": 0.8, "Bia": 1.25}.items() for _ in range(6)])
    # gestor só acessa a unidade 1: não vê a operação (nem o nome) nem conta a operação da Filial
    r = gestor.post("/pessoas/calibrar-ritmo", {}).json()
    assert r["operacoes_consideradas"] == 0 and r["operacoes_ignoradas"] == []
    assert all(p["status"] == "insuficiente" for p in r["pessoas"]) and "Filial" not in str(r)
    # o administrador (sem restrição) enxerga; e escolher a unidade limita ao histórico dela
    assert admin.post("/pessoas/calibrar-ritmo", {}).json()["operacoes_consideradas"] == 1
    assert admin.post("/pessoas/calibrar-ritmo", {"unidade_id": unidade_id}).json()["operacoes_consideradas"] == 0
    assert admin.post("/pessoas/calibrar-ritmo", {"unidade_id": u2}).json()["operacoes_consideradas"] == 1
