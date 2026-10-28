"""Catálogo modular de tempos: cada módulo com conta manual, pendências sem chute e IA sem poder escrever tempos."""
import json

import pytest

from app.services import estimativa
from app.services.ia import esquemas as es
from app.services.modulos import catalogo, coeficientes, motor
from app.services.modulos.base import EntradaModulo
from app.models import Operacao
from tests.conftest import criar_usuario

FT = 1 / 0.91  # 5 % pessoais + 4 % fadiga básica


def _calc(chave, **kw):
    return motor.calcular_modulo(catalogo.obter(chave), EntradaModulo(**kw))


def _painel(nome="P", qtd=1, comp=1.0, larg=0.5, **kw):
    return {"nome": nome, "qtd": qtd, "material": "mdf", "grupo": "Corpo", "comp": comp, "larg": larg, "esp": 0.02,
            "peso_kg": 7.0, "furos": 0, "bordas_m": None, **kw}


# ------------------------------------------------------------------ catálogo e coeficientes
def test_todo_coeficiente_tem_valor_fonte_e_status():
    assert len(coeficientes.COEFICIENTES) >= 15
    for c in coeficientes.COEFICIENTES.values():
        assert c.valor > 0 and c.fonte and c.status in ("referencia_generica", "calibrado") and c.versao >= 1 and c.unidade
    assert coeficientes.coef("fixador:parafuso").valor == 0.30 and coeficientes.coef("velocidade_caminhada_m_min").valor == 75
    assert coeficientes.coef_fixador("inexistente").chave == "fixador:outro"  # declarado, não escondido


def test_catalogo_e_fechado_e_nao_expoe_tempos_a_ia():
    assert set(catalogo.CHAVES) == {"movimentacao", "corte", "bordo", "furacao", "montagem", "conferencia"}
    texto = json.dumps(catalogo.resumo_para_ia(), ensure_ascii=False)
    assert "0.3" not in texto and "75" not in texto and "valor" not in texto and "a_min" not in texto
    assert all(m.versao >= 1 and m.parametros for m in catalogo.CATALOGO.values())


# ------------------------------------------------------------------ movimentação
def test_movimentacao_a_pe_conta_a_mao():
    # 10 peças de 5 kg: 20 kg/pessoa ⇒ 4 por viagem ⇒ 3 viagens; 30 m a 75 m/min, ida e volta ⇒ 3 × 0,4 × 2 = 2,4 min
    r = _calc("movimentacao", quantidade=10, distancia_m=30, componentes=[_painel(qtd=10, peso_kg=5.0)])
    assert r.completo and r.exec == pytest.approx(2.4 * FT, abs=0.001) and r.normal == pytest.approx(2.4, abs=0.001)
    assert r.pessoas == 1 and r.parametros["itens_por_viagem"] == 4
    assert {c["chave"] for c in r.coeficientes} == {"velocidade_caminhada_m_min", "carga_manual_max_kg"}
    assert any("Sem meio de movimentação" in p for p in r.premissas)


def test_movimentacao_peca_pesada_exige_mais_pessoas():
    r = _calc("movimentacao", quantidade=1, distancia_m=30, componentes=[_painel(peso_kg=70.0)])
    assert r.pessoas == 4 and r.parametros["itens_por_viagem"] == 1  # ceil(70/20)


def test_movimentacao_com_meio_usa_a_ficha_tecnica():
    # carrinho de 100 kg a 60 m/min: 10 peças de 5 kg cabem todas numa viagem ⇒ 1 × (30/60) × 2 = 1 min
    r = _calc("movimentacao", quantidade=10, distancia_m=30, componentes=[_painel(qtd=10, peso_kg=5.0)], meio_nome="Carrinho",
              ficha_meio={"velocidade_meio_m_min": 60, "capacidade_carga_kg": 100})
    assert r.exec == pytest.approx(1.0 * FT, abs=0.001) and r.parametros["itens_por_viagem"] == 20
    assert r.coeficientes == [] and not any("Sem meio" in p for p in r.premissas)  # nenhum coeficiente genérico entrou
    # meio sem ficha: pendência, nunca a velocidade da caminhada
    r = _calc("movimentacao", quantidade=10, distancia_m=30, componentes=[_painel(peso_kg=5.0)], meio_nome="Carrinho")
    assert r.total is None and any("velocidade do meio" in f for f in r.faltantes) and any("capacidade de carga" in f for f in r.faltantes)
    # peça acima da capacidade do meio
    r = _calc("movimentacao", quantidade=1, distancia_m=30, componentes=[_painel(peso_kg=150.0)], meio_nome="Carrinho",
              ficha_meio={"velocidade_meio_m_min": 60, "capacidade_carga_kg": 100})
    assert r.total is None and any("passa da capacidade" in f for f in r.faltantes)


def test_movimentacao_sem_distancia_ou_peso_vira_pendencia():
    r = _calc("movimentacao", quantidade=1, componentes=[_painel(peso_kg=None)], origem_nome="A", destino_nome="B")
    assert r.total is None and any("distância entre A e B" in f for f in r.faltantes) and any("peso" in f for f in r.faltantes)
    assert _calc("movimentacao", quantidade=1, distancia_m=10, componentes=[_painel()], piso="epóxi").premissas[0].startswith("O piso")


# ------------------------------------------------------------------ usinagem
def test_corte_metros_sobre_avanco():
    # 3 peças de 1,0 × 0,5 (perímetro 3 m): 9 m de corte a 18 m/min = 0,5 min; preparação 5 min
    r = _calc("corte", quantidade=3, unidades_produto=1, recurso_nome="Serra", ficha={"avanco_corte_m_min": 18},
              componentes=[_painel(qtd=3)])
    assert r.parametros["metros_de_corte"] == 9 and r.exec == pytest.approx(0.5 * FT, abs=0.001) and r.prep == pytest.approx(5 * FT, abs=0.001)
    assert r.composicao[0]["tipo"] == "preparacao" and any(e["depende_operador"] is False for e in r.elementos)


def test_corte_alerta_espessura_acima_do_limite_da_ficha():
    r = _calc("corte", quantidade=1, recurso_nome="Serra", ficha={"avanco_corte_m_min": 18, "espessura_max_corte_mm": 15},
              componentes=[_painel()])  # 20 mm
    assert r.total is not None and any("20 mm" in a and "15 mm" in a for a in r.alertas)


def test_bordo_metros_sobre_velocidade():
    # 2 peças com 3,0 m de borda cada, a 6 m/min ⇒ 1 min
    r = _calc("bordo", quantidade=2, recurso_nome="Coladeira", ficha={"velocidade_bordo_m_min": 6},
              componentes=[_painel(qtd=2, bordas_m=3.0)])
    assert r.parametros["metros_de_borda"] == 6 and r.exec == pytest.approx(1.0 * FT, abs=0.001)


def test_furacao_ciclos_por_cabecotes():
    # 2 peças de 10 furos, 4 cabeçotes ⇒ ceil(10/4)=3 ciclos por peça ⇒ 6 ciclos de 20 mm a 40 mm/min = 3 min
    r = _calc("furacao", quantidade=2, recurso_nome="Furadeira", componentes=[_painel(qtd=2, furos=10)],
              ficha={"cabecotes_furacao": 4, "curso_furacao_mm": 20, "avanco_furacao_mm_min": 40})
    assert r.parametros["ciclos"] == 6 and r.exec == pytest.approx(3.0 * FT, abs=0.001)


def test_usinagem_sem_ficha_ou_equipamento_nao_inventa_taxa():
    r = _calc("corte", quantidade=1, recurso_nome="Serra", componentes=[_painel()])
    assert r.total is None and any("'avanco_corte_m_min' na ficha técnica de 'Serra'" in f for f in r.faltantes) and not r.elementos
    r = _calc("furacao", quantidade=1, recurso_nome="Furadeira", componentes=[_painel(furos=4)], ficha={"cabecotes_furacao": 2})
    assert r.total is None and len([f for f in r.faltantes if "ficha técnica" in f]) == 2
    r = _calc("corte", quantidade=1, componentes=[_painel()])
    assert r.total is None and any("falta o equipamento" in f for f in r.faltantes)
    r = _calc("corte", quantidade=1, recurso_nome="Serra", ficha={"avanco_corte_m_min": 18}, componentes=[_painel(comp=None)])
    assert r.total is None and any("faltam comp" in f for f in r.faltantes)


# ------------------------------------------------------------------ montagem e conferência
def test_montagem_por_subconjunto_e_final():
    lig = [{"metodo": "parafuso", "fixadores": 8}, {"metodo": "cavilha", "fixadores": 4}]
    r = _calc("montagem", quantidade=2, unidades_produto=2, componentes=[_painel(qtd=3)], ligacoes=lig, extras={"grupo": "Corpo"})
    por_un = 3 * 0.174 + 8 * 0.30 + 4 * 0.20  # pegar/posicionar + parafusos + cavilhas
    assert r.normal == pytest.approx(por_un * 2, abs=0.001) and r.total == pytest.approx(por_un * 2 * FT, abs=0.001)
    # final: 2 subconjuntos ⇒ 1 posicionamento por unidade; o peso do conjunto define o mínimo de pessoas (45 kg ⇒ 3)
    f = _calc("montagem", quantidade=2, unidades_produto=2, componentes=[_painel()], ligacoes=[{"metodo": "minifix", "fixadores": 4}],
              extras={"final": True, "n_pecas": 1.0, "peso_conjunto_kg": 45.0})
    assert f.normal == pytest.approx((0.174 + 4 * 0.45) * 2, abs=0.001) and f.pessoas == 3
    sem = _calc("montagem", quantidade=1, componentes=[_painel()])
    assert any("como se montam" in x for x in sem.faltantes)  # sem ligação: pendência


def test_conferencia_e_tolerancias_e_calibracao():
    r = _calc("conferencia", quantidade=3)
    assert r.total == pytest.approx(5 * 3 * FT, abs=0.001) and r.tolerancia_pct == 9 and r.ft == pytest.approx(FT)
    assert [l["tipo"] for l in r.composicao].count("tolerancia") == 2
    # ritmo só mexe no que depende do operador; o fator de calibração é multiplicativo e limitado a 0,5–2,0
    mais_rapido = motor.calcular_modulo(catalogo.obter("conferencia"), EntradaModulo(quantidade=3), ritmo_pct=125)
    assert mais_rapido.normal == pytest.approx(15 / 1.25, abs=0.001)
    cal = motor.calcular_modulo(catalogo.obter("conferencia"), EntradaModulo(quantidade=3), fator_calibracao=1.2, calibrado=True)
    assert cal.total == pytest.approx(r.total * 1.2, abs=0.001) and cal.calibrado
    assert motor.calcular_modulo(catalogo.obter("conferencia"), EntradaModulo(quantidade=3), fator_calibracao=9).total == pytest.approx(r.total * 2, abs=0.001)


def test_hierarquia_soma_e_separa_preparacao():
    passos = [{"grupo": "Corte", "modulo": "corte", "titulo": "Corte", "nome": "Cortar", "tempo_normal_min": 10.0, "tempo_prep_min": 5.5,
               "tempo_exec_min": 5.5, "tempo_padrao_min": 11.0, "composicao": [{"nome": "a", "tipo": "processamento", "minutos": 10.0},
               {"nome": "tol", "tipo": "tolerancia", "minutos": 1.0}], "faltantes": [], "pessoas": 1},
              {"grupo": "Corpo", "modulo": "montagem", "titulo": "Montagem", "nome": "Montar", "tempo_normal_min": 20.0, "tempo_prep_min": None,
               "tempo_exec_min": 22.0, "tempo_padrao_min": 22.0, "composicao": [], "faltantes": ["x"], "pessoas": 2}]
    h = motor.hierarquia("Mesa", 4, passos)
    assert h["tempo_padrao_min"] == 33.0 and h["tempo_normal_min"] == 30.0 and h["tolerancias_min"] == 1.0 and h["preparacao_min"] == 5.5
    assert h["por_unidade_produto"]["tempo_padrao_min"] == 8.25 and [g["grupo"] for g in h["grupos"]] == ["Corte", "Corpo"]
    assert h["grupos"][1]["modulos"][0]["completo"] is False


# ------------------------------------------------------------------ IA não escreve tempos
def test_ia_nao_tem_onde_escrever_tempo_e_so_escolhe_do_catalogo():
    passo = es.PassoIA.model_validate({"nome": "x", "modulo": "corte", "a_min": 9, "b_min": 1, "tempo_min": 5, "qtd_pecas": 1e9,
                                       "elementos": [{"nome": "z", "metodo": "fixo", "a_min": 99}], "capacidade_un_h": 5000})
    assert not any(hasattr(passo, k) for k in ("a_min", "b_min", "tempo_min", "elementos", "qtd_pecas", "capacidade_un_h"))
    assert set(es.PassoIA.model_fields) == {"nome", "modulo", "grupo", "final", "componentes", "recurso", "espaco_origem",
                                           "espaco_destino", "pessoas", "observacao"}
    with pytest.raises(Exception):
        es.PassoIA(nome="x", modulo="inventado")
    prop = es.sanear_plano(es.PlanoProposta(passos=[es.PassoIA(nome="a", modulo="conferencia", pessoas=9999)]))
    assert prop.passos[0].pessoas == 20


# ------------------------------------------------------------------ operação com módulo (decisão: Processos também usam o catálogo)
def _op_com_modulo(gestor, uid, **corpo):
    p = gestor.post("/processos", {"unidade_id": uid, "nome": "P"}).json()
    e = gestor.post(f"/processos/{p['id']}/etapas", {"nome": "E"}).json()
    r = gestor.post(f"/etapas/{e['id']}/operacoes", {"nome": "Levar", **corpo})
    assert r.status_code == 201, r.text
    return r.json()


def test_operacao_com_modulo_estima_sem_tempo_digitado(gestor, unidade_id):
    op = _op_com_modulo(gestor, unidade_id, modulo="movimentacao", distancia_m=30, item_peso_kg=5)
    assert op["modulo"] == "movimentacao" and op["modulo_parametros"] == {}
    s = gestor.get(f"/operacoes/{op['id']}/estimativa?quantidade=10").json()
    assert s["fonte"] == "modulo" and s["execucao_min"] == pytest.approx(2.4 * FT, abs=0.01)
    assert any("Coeficientes de referência genéricos" in a for a in s["avisos"])
    assert {e["tipo"] for e in s["elementos"]} == {"deslocamento", "tolerancia"}
    # sem a distância: o módulo fica incompleto e o sistema diz o que falta (não chuta)
    sem = _op_com_modulo(gestor, unidade_id, modulo="movimentacao", item_peso_kg=5)
    s = gestor.get(f"/operacoes/{sem['id']}/estimativa?quantidade=10").json()
    assert s["fonte"] == "sem_base" and any("distância" in a for a in s["avisos"])


def test_operacao_valida_modulo_e_condicoes(gestor, unidade_id):
    op = _op_com_modulo(gestor, unidade_id, modulo="montagem",
                        modulo_parametros={"pecas_por_unidade": 3, "ligacoes": [{"metodo": "parafuso", "fixadores": 8}]})
    s = gestor.get(f"/operacoes/{op['id']}/estimativa?quantidade=2").json()
    assert s["fonte"] == "modulo" and s["execucao_min"] == pytest.approx((3 * 0.174 + 8 * 0.30) * 2 * FT, abs=0.01)
    p = gestor.post("/processos", {"unidade_id": unidade_id, "nome": "Q"}).json()
    e = gestor.post(f"/processos/{p['id']}/etapas", {"nome": "E"}).json()
    for ruim in ({"modulo": "inventado"}, {"modulo": "corte", "modulo_parametros": {"tempo_min": 5}},
                 {"modulo": "montagem", "modulo_parametros": {"ligacoes": [{"metodo": "magia", "fixadores": 1}]}}):
        assert gestor.post(f"/etapas/{e['id']}/operacoes", {"nome": "x", **ruim}).status_code == 422


def test_historico_calibra_o_modulo_e_aplica_as_tolerancias_dele(admin, gestor, unidade_id, db_factory):
    from tests.test_ritmo_historico import _historico, _n, _pessoa  # monta ordens concluídas com apontamentos aprovados
    op = _op_com_modulo(gestor, unidade_id, modulo="movimentacao", distancia_m=30, item_peso_kg=5)
    p = _pessoa(gestor, unidade_id, "Normal", ritmo_pct=100)
    _historico(db_factory, admin.usuario, op["id"], unidade_id, [[_n(p["id"], 30)] for _ in range(3)])  # 3 min/un observados
    db = db_factory()
    try:
        e = estimativa.estimar_operacao(db, admin.usuario["empresa_id"], db.get(Operacao, op["id"]), 10)
    finally:
        db.close()
    ft = FT
    assert e.fonte == "historico" and e.tempo_normal == pytest.approx(30.0) and e.exec == pytest.approx(30.0 * ft)
    assert e.tolerancia_pct == 9 and not any("Sem tolerâncias" in a for a in e.avisos)  # as tolerâncias vêm do módulo, sem modelo
    assert any("módulo" in a and "revise as premissas" in a for a in e.avisos)  # módulo previu 2,4 min/10 un contra 30 do histórico


def test_migracao_0007_sobe_e_desce_no_sqlite(tmp_path):
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

    alembic("upgrade", "0006")
    assert "modulo" not in colunas("plano_passos") and "modulo" not in colunas("operacoes")
    alembic("upgrade", "0007")
    assert {"modulo", "modulo_versao", "parametros_modulo", "coeficientes", "tempo_normal_min"} <= colunas("plano_passos")
    assert {"modulo", "modulo_parametros"} <= colunas("operacoes")
    alembic("downgrade", "-1")
    assert "modulo" not in colunas("plano_passos") and "modulo_parametros" not in colunas("operacoes")
    alembic("upgrade", "head")
    assert "modulo" in colunas("plano_passos")


# ------------------------------------------------------------------ Fase 5: a IA sugere o módulo; a pessoa aplica
def test_ia_sugere_modulo_sem_gravar_e_lista_o_que_falta(gestor, unidade_id):
    op = _op_com_modulo(gestor, unidade_id, item_peso_kg=5)
    r = gestor.post(f"/operacoes/{op['id']}/modulo/sugerir", {})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["modulo"] == "movimentacao" and d["titulo"] and d["provedor"] == "heuristica"  # "Levar…" é movimentação
    assert any("distância" in f for f in d["faltantes"])  # as condições que faltam; nenhum tempo na resposta
    assert set(d) == {"modulo", "titulo", "justificativa", "faltantes", "provedor", "aviso", "aplicar_com"}  # nenhum campo de tempo
    assert gestor.get(f"/processos/{gestor.get('/processos').json()[0]['id']}").json()["etapas"][0]["operacoes"][0]["modulo"] is None  # nada gravado
    assert gestor.patch(f"/operacoes/{op['id']}", {"modulo": d["modulo"], "distancia_m": 30}).json()["modulo"] == "movimentacao"
    assert gestor.get(f"/operacoes/{op['id']}/estimativa?quantidade=10").json()["fonte"] == "modulo"
    assert {m["chave"] for m in gestor.get("/modulos").json()} == set(catalogo.CHAVES)


def test_ia_externa_so_escolhe_chave_do_catalogo(gestor, unidade_id, monkeypatch):
    from app.services import ia
    monkeypatch.setattr(ia, "provedor_ativo", lambda empresa: "claude")
    monkeypatch.setattr(ia.claude, "sugerir_modulo", lambda ctx: es.SugestaoModulo.model_validate(
        {"modulo": "corte", "justificativa": "corte de chapas\x00" + "x" * 900, "a_min": 5, "tempo_min": 9}))
    op = _op_com_modulo(gestor, unidade_id)
    d = gestor.post(f"/operacoes/{op['id']}/modulo/sugerir", {}).json()
    assert d["modulo"] == "corte" and len(d["justificativa"]) == 400 and "\x00" not in d["justificativa"] and d["provedor"].startswith("claude")
    monkeypatch.setattr(ia.claude, "sugerir_modulo", lambda ctx: es.SugestaoModulo(modulo=None))
    assert gestor.post(f"/operacoes/{op['id']}/modulo/sugerir", {}).json()["modulo"] is None
    with pytest.raises(Exception):
        es.SugestaoModulo.model_validate({"modulo": "executar_codigo"})


def test_entradas_de_tempo_obsoletas_estao_marcadas(gestor, unidade_id):
    """Rotas/campos que digitavam tempo seguem na API (dados antigos), mas marcados como obsoletos no OpenAPI."""
    esquema = gestor.c.get("/openapi.json").json() if gestor.c.get("/openapi.json").status_code == 200 else None
    if esquema is None:  # em produção o /docs fica desligado; aqui o ambiente é de desenvolvimento
        pytest.skip("OpenAPI indisponível")
    caminhos = esquema["paths"]
    for rota, metodo in (("/api/v1/referencias-tempo", "put"), ("/api/v1/operacoes/{oid}/modelo-tempo/gerar", "post"),
                         ("/api/v1/operacoes/{oid}/modelo-tempo", "post"), ("/api/v1/operacoes/{oid}/parametros/atualizar-historico", "post")):
        assert caminhos[rota][metodo].get("deprecated") is True, rota
