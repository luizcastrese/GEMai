"""Fluxo de propósito geral: pacotes de segmento por empresa, roteiro pela posição padrão das atividades, conferência opcional
e checagem do local de produção derivada das atividades em uso."""
from tests.conftest import SENHA
from tests.test_plano import _cadastrar_contorno, _ficha, _gerar, _mesa
from tests.conftest import Sessao


def _empresa(client, nome, segmento, **extra):
    r = client.post("/api/v1/auth/registrar", json={"empresa_nome": nome, "segmento": segmento, "unidade_nome": "Matriz", "nome": "Ana",
                                                    "email": f"ana@{nome.lower().replace(' ', '')}.com", "senha": SENHA, **extra})
    assert r.status_code == 201, r.text
    d = r.json()
    return Sessao(client, d["access_token"], d["usuario"])


def _chaves(a):
    return [m["chave"] for m in a.get("/modulos").json()]


# ------------------------------------------------------------------ pacotes de segmento
def test_pacote_vem_do_segmento_e_o_base_vale_para_todos(client):
    m = _empresa(client, "Moveis Ana", "Marcenaria e móveis planejados")
    g = _empresa(client, "Grafica Bia", "Gráfica rápida")
    assert m.get("/empresa").json()["pacotes"] == ["marcenaria"]
    eg = g.get("/empresa").json()
    assert eg["pacotes"] == [] and eg["atributos_peca"] == [] and {p["chave"] for p in eg["pacotes_disponiveis"]} == {"marcenaria"}
    assert set(_chaves(g)) == {"movimentacao", "montagem", "conferencia"}
    assert {"corte", "bordo", "furacao"} <= set(_chaves(m))
    assert _chaves(m)[:2] == ["movimentacao", "corte"]  # ordenado pela posição padrão no roteiro


def test_ligar_e_desligar_pacote_muda_o_catalogo_e_a_operacao(client):
    g = _empresa(client, "Grafica Caio", "Gráfica")
    proc = g.post("/processos", {"unidade_id": g.unidade_id, "nome": "P"}).json()
    et = g.post(f"/processos/{proc['id']}/etapas", {"nome": "E"}).json()
    assert g.post(f"/etapas/{et['id']}/operacoes", {"nome": "Cortar", "modulo": "corte"}).status_code == 422
    assert g.patch("/empresa", {"pacotes": ["inexistente"]}).status_code == 422
    e = g.patch("/empresa", {"pacotes": ["marcenaria"]}).json()
    assert e["pacotes"] == ["marcenaria"] and {a["campo"] for a in e["atributos_peca"]} == {"furos", "bordas_m"}
    assert g.post(f"/etapas/{et['id']}/operacoes", {"nome": "Cortar", "modulo": "corte"}).status_code == 201


def test_sem_pacote_de_segmento_o_plano_nao_usa_corte(client):
    g = _empresa(client, "Grafica Davi", "Gráfica")
    _cadastrar_contorno(g, g.unidade_id)
    pid, _, _ = _mesa(g)
    p = _gerar(g, pid, g.unidade_id)
    assert "corte" not in [s["modulo"] for s in p["passos"]] and "montagem" in [s["modulo"] for s in p["passos"]]


# ------------------------------------------------------------------ conferência opcional
def test_conferencia_final_e_opcional_e_o_recalculo_mantem_a_escolha(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id, incluir_conferencia=False)
    assert "conferencia" not in [s["modulo"] for s in p["passos"]] and p["config"]["incluir_conferencia"] is False
    r = admin.post(f"/planos/{p['id']}/recalcular", {"produto_id": pid, "unidade_id": unidade_id, "quantidade": 3})
    assert r.status_code == 200 and "conferencia" not in [s["modulo"] for s in r.json()["passos"]]
    assert "conferencia" in [s["modulo"] for s in _gerar(admin, pid, unidade_id)["passos"]]  # padrão: incluir


# ------------------------------------------------------------------ roteiro pela posição padrão das atividades
def _validar(a, espec):
    r = a.post("/modulos/empresa", {"espec": espec})
    assert r.status_code == 201, r.text
    m = r.json()
    assert a.post(f"/modulos/empresa/{m['id']}/validar", {}).status_code == 200
    return m


def test_roteiro_segue_a_posicao_padrao_de_cada_atividade(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    acao = {"nome": "Passar", "alcance": "ao_alcance", "pegar": "leve", "levar": "ao_alcance", "posicionar": "aproximado"}
    antes = _validar(admin, {"titulo": "Marcar peças", "arquetipo": "manual", "driver": "{qtd}", "acoes": [acao], "ordem": 5})
    depois = _validar(admin, {"titulo": "Embalar", "arquetipo": "manual", "driver": "{unidade}", "unidade_contagem": "unidade_produto",
                              "acoes": [acao], "ordem": 80})
    seq = [s["modulo"] for s in _gerar(admin, pid, unidade_id)["passos"]]
    assert seq.index(antes["chave"]) < seq.index("corte") < seq.index("montagem") < seq.index(depois["chave"]) < seq.index("conferencia")


# ------------------------------------------------------------------ checagem do local de produção pelas atividades em uso
def test_checagem_pede_equipamento_e_ficha_da_atividade_da_empresa(admin, unidade_id):
    est, cor, mon = _cadastrar_contorno(admin, unidade_id)
    _mesa(admin)
    tx = {"nome": "taxa_lixar_m2_min", "unidade": "m²/min", "descricao": "Taxa de lixamento", "minimo": 0.01, "maximo": 50}
    m = _validar(admin, {"titulo": "Lixar", "arquetipo": "processamento_meio", "driver": "{area_m2}", "funcao_meio": "lixar", "taxa": tx})
    c = admin.get(f"/contorno?unidade_id={unidade_id}").json()
    assert any("Lixar" in x for x in c["faltando"]) and c["completo"] is False
    rec = admin.post("/recursos", {"unidade_id": unidade_id, "nome": "Lixadeira", "funcao": "lixar", "espaco_id": cor["id"]}).json()
    c = admin.get(f"/contorno?unidade_id={unidade_id}").json()
    assert any("Lixadeira" in x and "taxa de lixamento" in x.lower() for x in c["faltando"])
    _ficha(admin, rec["id"], taxa_lixar_m2_min=0.5)
    c = admin.get(f"/contorno?unidade_id={unidade_id}").json()
    assert not any("Lixar" in x or "Lixadeira" in x for x in c["faltando"])
    assert m["chave"] in _chaves(admin)
