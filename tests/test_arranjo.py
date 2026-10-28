"""Fase 7: arranjo recomendado — escalonamento com recursos limitados, dependências do produto e candidatos determinísticos."""
import math
from types import SimpleNamespace

import pytest

from app.services.arranjo.agenda import Opcao, Tarefa, escalonar
from app.services.arranjo.avaliar import Config, dominado, melhores
from app.services.arranjo.dependencias import dependencias
from app.services.ia import esquemas as es
from tests.conftest import registrar
from tests.test_plano import FT, _cadastrar_contorno, _ficha, _gerar, _mesa


def T(i, passo, dur, preds=(), pessoas=1, lote=0, maquina=None, **kw):
    ops = [Opcao(m, d, {}) for m, d in (maquina if isinstance(maquina, list) else [(maquina, dur)])]
    return Tarefa(i, passo, lote, f"t{i}", pessoas, ops, list(preds))


def fim(aloc):
    return max(a.fim for a in aloc)


# ------------------------------------------------------------------ escalonador (contas à mão)
def test_equipe_maior_paraleliza_o_que_nao_depende():
    # A(10) → B(5);  C(8) independente
    ts = [T(0, 0, 10), T(1, 1, 5, [0]), T(2, 2, 8)]
    um = escalonar(ts, 1, "plano")
    assert [(a.tarefa.id, a.ini, a.fim) for a in um] == [(0, 0, 10), (1, 10, 15), (2, 15, 23)]  # em série: 10 + 5 + 8
    dois = escalonar(ts, 2, "plano")
    assert fim(dois) == 15 and next(a for a in dois if a.tarefa.id == 2).ini == 0  # C roda junto com A


def test_maquina_so_faz_uma_coisa_por_vez_e_pool_de_maquinas_ajuda():
    ts = [T(0, 0, 5, maquina=1), T(1, 1, 5, maquina=1)]
    assert fim(escalonar(ts, 2, "plano")) == 10  # a mesma máquina serializa, mesmo com gente de sobra
    pool = [T(0, 0, 5, maquina=[(1, 5), (2, 5)]), T(1, 1, 5, maquina=[(1, 5), (2, 5)])]
    assert fim(escalonar(pool, 2, "plano")) == 5  # duas máquinas da mesma função: em paralelo
    # o pool escolhe a máquina que TERMINA primeiro (a 2 é mais rápida)
    r = escalonar([T(0, 0, 5, maquina=[(1, 8), (2, 5)])], 1, "plano")
    assert r[0].opcao.recurso_id == 2 and r[0].fim == 5


def test_tarefa_que_exige_mais_pessoas_que_a_equipe_e_inviavel_e_ocupa_todos():
    assert escalonar([T(0, 0, 5, pessoas=3)], 2, "plano") is None
    ts = [T(0, 0, 5, pessoas=2), T(1, 1, 5)]
    r = escalonar(ts, 2, "plano")
    assert fim(r) == 10 and len(r[0].equipe) == 2  # com 2 pessoas na tarefa 0, a 1 espera


def test_regra_do_caminho_critico_pode_encurtar_o_prazo():
    # a, b, c independentes (5 cada); d(10) depende de c. Equipe de 2.
    ts = [T(0, 0, 5), T(1, 1, 5), T(2, 2, 5), T(3, 3, 10, [2])]
    assert fim(escalonar(ts, 2, "plano")) == 20  # a, b primeiro; c só em t=5; d termina em 20
    assert fim(escalonar(ts, 2, "critico")) == 15  # c e d (caminho crítico) primeiro


def test_lotes_em_pipeline_usam_a_mesma_maquina_em_serie():
    # 2 lotes de (corte 4 na máquina 1 → montagem 6): corte do lote 2 entra enquanto o lote 1 monta
    ts = [T(0, 0, 4, maquina=1, lote=0), T(1, 1, 6, [0], lote=0), T(2, 0, 4, maquina=1, lote=1), T(3, 1, 6, [2], lote=1)]
    r = escalonar(ts, 2, "plano")
    # corte 1: 0–4; montagem 1: 4–10; corte 2 (mesma máquina, só após 4): 4–8; montagem 2: 8–14
    assert [(a.tarefa.id, a.ini, a.fim) for a in sorted(r, key=lambda a: a.tarefa.id)] == [(0, 0, 4), (1, 4, 10), (2, 4, 8), (3, 8, 14)]
    assert fim(escalonar(ts, 1, "plano")) == 20  # com uma pessoa só: 4+6+4+6


# ------------------------------------------------------------------ dependências do produto
def P(nome, modulo, comps, final=False):
    return SimpleNamespace(nome=nome, modulo=modulo, componentes=comps, final=final)


def test_dependencias_vem_da_estrutura_do_produto():
    passos = [P("levar", "movimentacao", ["Tampo", "Lateral"]), P("cortar tampo", "corte", ["Tampo"]), P("cortar lateral", "corte", ["Lateral"]),
              P("levar", "movimentacao", ["Tampo", "Lateral"]), P("montar corpo", "montagem", ["Tampo", "Lateral"]),
              P("montar gaveta", "montagem", ["Frente"]), P("montagem final", "montagem", ["Corpo", "Frente"], final=True),
              P("conferência", "conferencia", [])]
    d = dependencias(passos)
    assert d[0] == set() and d[1] == {0} and d[2] == {0}   # cortes dependem do transporte, mas NÃO um do outro
    assert d[3] == {1, 2} and d[4] == {3}
    assert d[5] == set()                                   # cadeia sem relação: pode andar em paralelo
    assert {4, 5} <= d[6]                                  # a montagem final espera todas as montagens de grupo
    assert d[7] == {6}                                     # conferência espera o fim da cadeia


# ------------------------------------------------------------------ Pareto
def R(pid, mk, ph, alertas, pessoas):
    return SimpleNamespace(config=Config(pessoas, 1, "plano", None), id=pid,
                           metricas={"makespan_min": mk, "pessoas_hora": ph, "ergonomia": {"alertas_seguranca": alertas}})


def test_pareto_descarta_dominados_e_ordena_por_prazo():
    a, b, c, d = R("a", 30, 1.0, 0, 1), R("b", 20, 1.2, 0, 2), R("c", 25, 1.5, 0, 3), R("d", 20, 1.2, 1, 2)
    assert dominado(c, [a, b, c, d]) and dominado(d, [a, b, c, d])
    assert not dominado(a, [a, b, c, d]) and not dominado(b, [a, b, c, d])
    assert [r.id for r in melhores([a, b, c, d], 5)] == ["b", "a"]
    assert [r.id for r in melhores([a, b, c, d], 1)] == ["b"]


# ------------------------------------------------------------------ endpoint
def _arranjos(a, pid, u, **kw):
    r = a.post("/planos/arranjos", {"produto_id": pid, "unidade_id": u, "quantidade": 2, "inicio": "2026-10-14T08:00:00-03:00", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _meio(a, u, *, nome="Carrinho", ficha=True, velocidade=50, capacidade=100):
    r = a.post("/recursos", {"unidade_id": u, "nome": nome, "funcao": "movimentacao"})
    assert r.status_code == 201, r.text
    if ficha:
        _ficha(a, r.json()["id"], velocidade_meio_m_min=velocidade, capacidade_carga_kg=capacidade)
    return r.json()["id"]


def test_arranjos_sao_deterministicos_ordenados_e_nao_gravam_nada(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    r1 = _arranjos(admin, pid, unidade_id, pessoas_max=3)
    r2 = _arranjos(admin, pid, unidade_id, pessoas_max=3)
    assert r1 == r2                                                        # mesma entrada, mesma saída
    cs = r1["candidatos"]
    assert 1 <= len(cs) <= 5 and r1["avaliados"] == 12                      # 3 pessoas × lotes {1,2} × regras {plano, critico}
    assert [c["makespan_min"] for c in cs] == sorted(c["makespan_min"] for c in cs)
    assert admin.get("/planos").json() == []                                # recomendar não grava plano
    um = _arranjos(admin, pid, unidade_id, pessoas_max=1)["candidatos"]
    # com UMA pessoa nada é paralelo: o prazo é a soma dos tempos padrão e a equipe fica 100 % ocupada
    assert len(um) == 1 and um[0]["pessoas"] == 1 and um[0]["lotes"] == 1
    assert um[0]["makespan_min"] == pytest.approx(um[0]["tempo_padrao_min"], abs=0.02) and um[0]["ocupacao_pct"]["Equipe"] == 100
    # o mesmo plano sequencial do gerador clássico: 5 passos, soma conferida à mão no teste do plano
    soma = sum(s["tempo_padrao_min"] for s in _gerar(admin, pid, unidade_id)["passos"])
    assert um[0]["makespan_min"] == pytest.approx(soma, abs=0.05)
    mais = cs[0]
    assert mais["pessoas"] >= 2 and mais["makespan_min"] < um[0]["makespan_min"]   # equipe maior encurta o prazo…
    assert mais["pessoas_hora"] >= um[0]["pessoas_hora"] - 1e-9                     # …e nunca gasta menos pessoas-hora
    assert any(t["lote"] == 2 for t in mais["cronograma"]) or mais["lotes"] == 1


def test_sem_meio_o_transporte_e_a_pe_com_pendencia_e_com_meio_vale_a_ficha(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    sem = _arranjos(admin, pid, unidade_id, pessoas_max=1)
    assert any("Nenhum meio de movimentação cadastrado" in p for p in sem["pendencias"])
    a_pe = next(t for t in sem["candidatos"][0]["cronograma"] if t["tarefa"].startswith("Levar peças até Corte"))
    assert a_pe["duracao_min"] == pytest.approx(2 * (30 / 75) * 2 * FT, abs=0.01)     # 2 viagens a pé (3 peças por viagem)
    _meio(admin, unidade_id)                                                          # carrinho: 50 m/min, 100 kg → 17 peças por viagem
    com = _arranjos(admin, pid, unidade_id, pessoas_max=1)
    assert com["pendencias"] == [] and com["candidatos"][0]["meio"] == "Carrinho"
    leva = next(t for t in com["candidatos"][0]["cronograma"] if t["tarefa"].startswith("Levar peças até Corte"))
    assert leva["duracao_min"] == pytest.approx((30 / 50) * 2 * FT, abs=0.01)         # 1 viagem só: o meio substitui a pessoa carregando
    assert leva["duracao_min"] < a_pe["duracao_min"]


def test_meio_sem_ficha_ou_pequeno_demais_vira_pendencia_nao_valor_escondido(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    _meio(admin, unidade_id, ficha=False)
    r = _arranjos(admin, pid, unidade_id, pessoas_max=1)
    assert any("sem ficha técnica validada" in p for p in r["pendencias"]) and r["candidatos"][0]["meio"] is None   # segue a pé, declarado
    _meio(admin, unidade_id, nome="Carrinho pequeno", capacidade=5)                  # a lateral/tampo pesa 7 kg: não cabe
    r = _arranjos(admin, pid, unidade_id, pessoas_max=2)
    assert r["candidatos"] == [] and any("passa da capacidade" in p for p in r["pendencias"])


def test_produto_incompleto_devolve_pendencias_e_nenhum_candidato(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id, ficha=False, distancias=False)          # sem ficha da seccionadora e sem distâncias
    pid, _, _ = _mesa(admin)
    r = _arranjos(admin, pid, unidade_id)
    assert r["candidatos"] == [] and r["avaliados"] == 0
    txt = " ".join(r["pendencias"])
    assert "distância" in txt and "avanco_corte_m_min" in txt


# ------------------------------------------------------------------ plano a partir da escolha
def test_plano_nasce_do_arranjo_escolhido_com_agenda_em_paralelo(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    meio = _meio(admin, unidade_id)
    cs = _arranjos(admin, pid, unidade_id, pessoas_max=3)["candidatos"]
    esc = next(c for c in cs if c["pessoas"] > 1)
    corpo = {"produto_id": pid, "unidade_id": unidade_id, "quantidade": 2, "inicio": "2026-10-14T08:00:00-03:00",
             "escolha": {"pessoas": esc["pessoas"], "lotes": esc["lotes"], "regra": esc["regra"], "meio_id": meio}}
    r = admin.post("/planos/de-arranjo", corpo)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["totais"]["makespan_min"] == pytest.approx(esc["makespan_min"], abs=0.01)     # o plano é exatamente o candidato escolhido
    assert p["totais"]["arranjo"]["pessoas"] == esc["pessoas"] and p["config"]["arranjo"]["meio"] == "Carrinho"
    assert any("Arranjo escolhido" in x for x in p["premissas"])
    assert len(p["passos"]) == len(esc["cronograma"])
    inicios = sorted(s["inicio_prev"] for s in p["passos"])
    assert inicios[0].startswith("2026-10-14T11:00:00")                  # 08:00 (-03:00) = 11:00 UTC: começa na hora pedida
    assert len(set(inicios)) < len(inicios)                              # há passos simultâneos: a equipe maior trabalha em paralelo
    assert admin.get(f"/planos/{p['id']}").json()["totais"]["makespan_min"] == p["totais"]["makespan_min"]


def test_escolha_invalida_e_recusada(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    base = {"produto_id": pid, "unidade_id": unidade_id, "quantidade": 2}
    assert admin.post("/planos/de-arranjo", {**base, "escolha": {"pessoas": 2, "lotes": 4}}).status_code == 422       # 4 lotes de 2 unidades
    assert admin.post("/planos/de-arranjo", {**base, "escolha": {"pessoas": 9}}).status_code == 422
    assert admin.post("/planos/de-arranjo", {**base, "escolha": {"pessoas": 2, "regra": "aleatoria"}}).status_code == 422
    assert admin.post("/planos/de-arranjo", {**base, "escolha": {"pessoas": 2, "meio_id": 999}}).status_code == 404
    assert admin.post("/planos/de-arranjo", {**base, "escolha": {"pessoas": 2}, "tempo_min": 5}).status_code == 422   # extra=forbid: ninguém digita tempo
    assert admin.post("/planos/arranjos", {**base, "pessoas_max": 20}).status_code == 422


def test_arranjo_nao_vaza_entre_empresas(client, admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    outra = registrar(client, "Empresa B", "b@b.com")
    ub = outra.unidade_id
    assert outra.post("/planos/arranjos", {"produto_id": pid, "unidade_id": unidade_id}).status_code in (403, 404)
    assert outra.post("/planos/arranjos", {"produto_id": pid, "unidade_id": ub}).status_code == 404
    assert outra.post("/planos/de-arranjo", {"produto_id": pid, "unidade_id": ub, "escolha": {"pessoas": 1}}).status_code == 404


# ------------------------------------------------------------------ IA só explica e sugere; o sistema calcula
def test_ia_explica_e_sugere_mas_alternativa_invalida_e_descartada(admin, unidade_id, monkeypatch):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    visto = {}

    def falsa(empresa, fatos):
        visto.update(fatos)
        ex = es.sanear_explicacao(es.ExplicacaoArranjos(texto="Com 2 pessoas o prazo cai.", alternativas=[
            es.AlternativaArranjo(pessoas=2, lotes=2, regra="critico", motivo="x"), es.AlternativaArranjo(pessoas=50, lotes=1, regra="plano", motivo="y")]))
        return ex, "teste", None

    from app.services import ia
    monkeypatch.setattr(ia, "explicar_arranjos", falsa)
    r = _arranjos(admin, pid, unidade_id, pessoas_max=3, explicar=True)
    assert r["explicacao"] == "Com 2 pessoas o prazo cai."
    assert all(c["pessoas"] <= 8 for c in r["candidatos"])                  # pessoas=50 nunca entra
    assert "candidatos" in visto and all(set(c) >= {"rotulo", "makespan_min"} for c in visto["candidatos"])   # a IA recebe FATOS calculados
    assert not any("tempo" in k and "min" in k for c in visto["candidatos"] for k in c if k not in ("makespan_min",))
