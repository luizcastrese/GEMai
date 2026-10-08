"""Fatores humanos: perfil de mão de obra, NIOSH, tolerâncias (tempo padrão), ritmo e movimentos MOST."""
import pytest

from app.services import ergonomia as erg
from app.services import modelo_tempo as mt
from tests.conftest import criar_usuario, registrar

FT = 1 / (1 - 0.09)
LEV = {"h_cm": 30, "v_cm": 60, "d_cm": 40, "a_graus": 0, "freq_por_min": 1, "duracao": "ate_1h", "pega": "boa"}


# ------------------------------------------------------------------ métodos (unidade)
def test_niosh_confere_com_a_conta_manual():
    r = erg.niosh(LEV, 20)
    esperado = 23 * (25 / 30) * (1 - 0.003 * 15) * (0.82 + 4.5 / 40) * 1.0 * 0.94 * 1.0
    assert r["rwl_kg"] == pytest.approx(esperado, abs=0.01) and r["li"] == pytest.approx(20 / esperado, abs=0.01)
    assert r["multiplicadores"]["FM"] == 0.94 and r["multiplicadores"]["CM"] == 1.0


def test_niosh_tabelas_e_limites():
    assert erg._fm(0.2, "2_8h", 60) == 0.85 and erg._fm(3, "1_2h", 80) == 0.79
    assert erg._fm(9, "2_8h", 60) == 0.0 and erg._fm(9, "2_8h", 80) == 0.15  # depende de V
    assert erg._fm(1.5, "ate_1h", 60) == 0.91  # entre linhas: usa a frequência imediatamente superior (conservador)
    assert erg._fm(16, "ate_1h", 60) == 0.0
    ruim = erg.niosh({**LEV, "pega": "ruim"}, 10)["multiplicadores"]["CM"]
    assert ruim == 0.90 and erg.niosh({**LEV, "pega": "regular", "v_cm": 80}, 10)["multiplicadores"]["CM"] == 1.0
    fora = erg.niosh({**LEV, "v_cm": 200}, 10)  # fora do domínio da equação
    assert fora["li_infinito"] and fora["rwl_kg"] == 0


def test_niosh_incompleto_nao_inventa():
    r = erg.niosh({"h_cm": 30}, None)
    assert not r["completo"] and "peso da carga" in r["faltantes"] and "li" not in r


def test_murrell_e_tolerancia_por_carga():
    assert erg.murrell_fracao_descanso(6, 4) == pytest.approx(2 / 4.5)  # 26,7 min a cada 60 min
    assert erg.murrell_fracao_descanso(3, 4) == 0 and erg.murrell_fracao_descanso(6, None) == 0
    assert erg.tolerancia_por_li(0.9) == 0 and erg.tolerancia_por_li(1.25) == 0.05 and erg.tolerancia_por_li(5) == 0.15


def test_most_ritmo_e_tolerancias_no_motor():
    c = mt.Contexto(quantidade=10)
    mov = {"nome": "mov", "tipo": "manuseio", "metodo": "indices_most", "por_unidade": True, "indices_most": [1, 0, 1, 1, 0, 1, 0]}
    maq = {"nome": "maq", "tipo": "processamento", "metodo": "fixo", "a_min": 10, "depende_operador": False}
    base = mt.calcular([mov, maq], 1.0, c)
    assert base.exec == pytest.approx(0.24 + 10)  # 4 · 10 TMU · 0,0006 min · 10 un + 10 min de máquina
    rapido = mt.calcular([mov, maq], 1.0, c, ritmo_pct=125)
    assert rapido.exec == pytest.approx(0.24 / 1.25 + 10)  # ritmo só afeta o que depende do operador
    tol = mt.calcular([mov, maq], 1.0, c, [{"categoria": "p", "percentual": 5}, {"categoria": "f", "percentual": 4}])
    assert tol.exec == pytest.approx(10.24 * FT, abs=0.001)
    assert sum(e["minutos"] for e in tol.elementos) == pytest.approx(tol.exec, abs=0.005)  # composição fecha com o total
    muito = mt.calcular([maq], 1.0, c, [{"categoria": "x", "percentual": 90}])
    assert muito.exec == pytest.approx(20, abs=0.001)  # p limitado a 50% (FT máx. = 2)


def test_indices_most_sao_limitados_ao_vocabulario():
    m = mt.sanear_modelo(mt.ModeloTempoIA(elementos=[mt.ElementoTempo(nome="x", metodo="indices_most", indices_most=[2, 7, 100])]))
    assert all(i in mt.INDICES_MOST for i in m.elementos[0].indices_most)


# ------------------------------------------------------------------ API
def _perfil(gestor, uid, **kw):
    corpo = {"unidade_id": uid, "nome": "Perfil A", **kw}
    r = gestor.post("/perfis-mao-de-obra", corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _op(gestor, uid, perfil_id=None, **extra):
    est = gestor.post("/espacos", {"unidade_id": uid, "nome": f"E{extra.get('_n', 1)}"}).json()
    p = gestor.post("/processos", {"unidade_id": uid, "nome": "P"}).json()
    e = gestor.post(f"/processos/{p['id']}/etapas", {"nome": "E"}).json()
    corpo = {"nome": "Mover chapa", "perfil_id": perfil_id, "item_peso_kg": 20, "num_pessoas": 1,
             "inicio_marco": "pega", "fim_marco": "solta", "funcao_requerida": "Aux"}
    corpo.update({k: v for k, v in extra.items() if k != "_n"})
    r = gestor.post(f"/etapas/{e['id']}/operacoes", corpo)
    assert r.status_code == 201, r.text
    return p["id"], r.json()["id"]


def test_perfil_crud_validacoes_e_isolamento(client, gestor, operador, unidade_id):
    p = _perfil(gestor, unidade_id, sexo="feminino", estatura_cm=160, peso_corporal_kg=58, ritmo_pct=105)
    assert p["sexo"] == "feminino" and p["ritmo_pct"] == 105
    assert gestor.post("/perfis-mao-de-obra", {"unidade_id": unidade_id, "nome": "Perfil A"}).status_code == 409
    assert gestor.post("/perfis-mao-de-obra", {"unidade_id": unidade_id, "nome": "X", "ritmo_pct": 300}).status_code == 422
    assert gestor.post("/perfis-mao-de-obra", {"unidade_id": unidade_id, "nome": "Y", "sexo": "outro"}).status_code == 422
    assert operador.post("/perfis-mao-de-obra", {"unidade_id": unidade_id, "nome": "Z"}).status_code == 403
    assert gestor.delete(f"/perfis-mao-de-obra/{p['id']}").status_code == 405  # só desativa
    b = registrar(client, "Empresa B")
    assert b.get(f"/perfis-mao-de-obra/{p['id']}").status_code == 404
    gb = criar_usuario(b, "gestor", "g@b.com", b.usuario["unidade_ids"])
    pid, _ = _op(gb, b.usuario["unidade_ids"][0])
    et = gb.get(f"/processos/{pid}").json()["etapas"][0]["id"]
    assert gb.post(f"/etapas/{et}/operacoes", {"nome": "X", "perfil_id": p["id"]}).status_code == 422  # perfil alheio


def test_sexo_e_porte_nao_alteram_o_tempo_mas_alteram_alertas_de_carga(gestor, unidade_id):
    fem = _perfil(gestor, unidade_id, nome="Fem", sexo="feminino", estatura_cm=158, peso_corporal_kg=55)
    masc = _perfil(gestor, unidade_id, nome="Masc", sexo="masculino", estatura_cm=185, peso_corporal_kg=95)
    lev = {**LEV, "carga_kg": 22, "duracao": "2_8h"}
    resultados = {}
    for nome, perfil in (("fem", fem), ("masc", masc)):
        _, op = _op(gestor, unidade_id, perfil["id"], item_peso_kg=22, tipo_movimento="levantamento_curvado",
                    levantamento=lev, _n=nome)
        m = gestor.post(f"/operacoes/{op}/modelo-tempo/gerar").json()
        resultados[nome] = (gestor.get(f"/operacoes/{op}/estimativa?quantidade=10").json()["total_min"],
                            gestor.get(f"/operacoes/{op}/ergonomia").json())
    assert resultados["fem"][0] == resultados["masc"][0]  # mesmo ritmo ⇒ mesmo tempo, independente de sexo/porte
    assert any("CLT" in a for a in resultados["fem"][1]["alertas"])  # 22 kg contínuo > 20 kg (a verificar)
    assert not any("art. 390" in a for a in resultados["masc"][1]["alertas"])
    assert any("não alteram o tempo" in p.lower() or "NÃO alteram o tempo" in p for p in m["premissas"])


def test_ritmo_do_perfil_altera_so_o_tempo_do_operador(gestor, unidade_id):
    normal = _perfil(gestor, unidade_id, nome="Normal", ritmo_pct=100)
    rapido = _perfil(gestor, unidade_id, nome="Rapido", ritmo_pct=125)
    tempos = {}
    for nome, pf in (("n", normal), ("r", rapido)):
        _, op = _op(gestor, unidade_id, pf["id"], tipo_movimento="alcance_curto", item_peso_kg=None, _n=nome)
        gestor.post(f"/operacoes/{op}/modelo-tempo/gerar")
        tempos[nome] = gestor.get(f"/operacoes/{op}/estimativa?quantidade=100").json()["execucao_min"]
    # 100 un · (4 índices · 10 TMU · 0,0006 min) = 2,4 min de movimento; ritmo 125% ⇒ 1,92 min; × FT
    assert tempos["n"] == pytest.approx(2.4 * FT, abs=0.01) and tempos["r"] == pytest.approx(2.4 / 1.25 * FT, abs=0.01)


def test_niosh_na_operacao_gera_tolerancia_e_alerta_na_prontidao(gestor, unidade_id):
    pf = _perfil(gestor, unidade_id, sexo="masculino")
    pid, op = _op(gestor, unidade_id, pf["id"], item_peso_kg=20, levantamento=LEV, postura_trabalho="em_pe")
    e = gestor.get(f"/operacoes/{op}/ergonomia").json()
    assert e["niosh"]["completo"] and e["niosh"]["li"] == pytest.approx(1.25, abs=0.01)
    assert e["tolerancias_sugeridas"][0]["percentual"] == 5.0
    m = gestor.post(f"/operacoes/{op}/modelo-tempo/gerar").json()
    cats = {t["categoria"]: t["percentual"] for t in m["tolerancias"]}
    assert cats["trabalho em pé"] == 2.0 and cats["fadiga por carga (LI)"] == 5.0 and cats["necessidades pessoais"] == 5.0
    itens = [i for o in gestor.get(f"/processos/{pid}/prontidao").json()["operacoes"] for i in o["itens"]]
    assert any("Índice de levantamento" in i["detalhe"] for i in itens)  # técnico, para o especialista
    assert any(i["categoria"] == "seguranca" and "limite recomendado" in i["msg"] for i in itens)  # simples, para todos


def test_levantamento_incompleto_e_ruido_geram_pendencias(gestor, unidade_id):
    esp = gestor.post("/espacos", {"unidade_id": unidade_id, "nome": "Prensa", "ruido_db": 92, "temperatura_c": 35}).json()
    pid, op = _op(gestor, unidade_id, None, espaco_origem_id=esp["id"], espaco_destino_id=esp["id"], levantamento={"h_cm": 30})
    itens = [i for o in gestor.get(f"/processos/{pid}/prontidao").json()["operacoes"] for i in o["itens"]]
    msgs = " ".join(i["msg"] + " " + i["detalhe"] for i in itens)
    assert "Sem perfil de mão de obra" in msgs and "levantamento (NIOSH) incompletos" in msgs and "NR-15" in msgs
    assert any(i["categoria"] == "seguranca" and "ruído" in i["msg"] for i in itens)
    m = gestor.post(f"/operacoes/{op}/modelo-tempo/gerar").json()
    assert any("temperatura" in f for f in m["dados_faltantes"])  # não inventa tolerância para ambiente: pede avaliação
    assert gestor.get(f"/operacoes/{op}/ergonomia").json()["niosh"]["completo"] is False


def test_modelo_manual_aceita_tolerancias_e_ritmo(gestor, unidade_id):
    _, op = _op(gestor, unidade_id, None)
    r = gestor.post(f"/operacoes/{op}/modelo-tempo", {
        "elementos": [{"nome": "Montar", "tipo": "processamento", "metodo": "fixo", "por_unidade": True, "a_min": 2}],
        "ritmo_pct": 110, "tolerancias": [{"categoria": "pessoais", "percentual": 5, "fonte": "estudo interno"}]})
    assert r.status_code == 201, r.text
    assert r.json()["ritmo_pct"] == 110 and r.json()["tolerancias"][0]["fonte"] == "estudo interno"
    s = gestor.get(f"/operacoes/{op}/estimativa?quantidade=10").json()
    assert s["execucao_min"] == pytest.approx(20 / 1.10 / 0.95, abs=0.01)


def test_estrutura_e_nova_versao_preservam_fatores_humanos(gestor, unidade_id):
    pf = _perfil(gestor, unidade_id)
    pid, op = _op(gestor, unidade_id, pf["id"], tipo_movimento="alcance_curto", postura_trabalho="sentado",
                  altura_trabalho_m=0.9, gasto_energetico_kcal_min=3.2, levantamento=LEV)
    gestor.post(f"/operacoes/{op}/modelo-tempo/gerar")
    gestor.post(f"/processos/{pid}/publicar")
    v2 = gestor.post(f"/processos/{pid}/nova-versao").json()
    o = v2["etapas"][0]["operacoes"][0]
    assert o["perfil_id"] == pf["id"] and o["tipo_movimento"] == "alcance_curto" and o["levantamento"]["h_cm"] == 30
    assert o["postura_trabalho"] == "sentado" and o["altura_trabalho_m"] == 0.9
    est = gestor.get(f"/operacoes/{o['id']}/estimativa?quantidade=10").json()
    assert est["fonte"] == "modelo_ia" and any(e["tipo"] == "tolerancia" for e in est["elementos"])  # tolerâncias copiadas


def test_mesmo_espaco_nao_gera_deslocamento_nem_alerta_duplicado(gestor, unidade_id):
    esp = gestor.post("/espacos", {"unidade_id": unidade_id, "nome": "Prensa", "ruido_db": 92}).json()
    _, op = _op(gestor, unidade_id, None, espaco_origem_id=esp["id"], espaco_destino_id=esp["id"], tipo_movimento="alcance_curto")
    m = gestor.post(f"/operacoes/{op}/modelo-tempo/gerar").json()
    assert not any(e["metodo"] == "deslocamento" for e in m["elementos"])  # origem == destino: sem deslocamento
    alertas = gestor.get(f"/operacoes/{op}/ergonomia").json()["alertas"]
    assert sum("NR-15" in a for a in alertas) == 1
