"""Generalidade: módulos criados pela EMPRESA por necessidade (a IA delimita, uma pessoa valida) sobre arquétipos de cálculo,
atributos livres das peças e o pacote de marcenaria congelado."""
import pytest

from app.services.ia import esquemas as es
from app.services.modulos import arquetipos as aq
from tests.conftest import registrar
from tests.test_plano import FT, _cadastrar_contorno, _ficha, _gerar, _mesa


# ------------------------------------------------------------------ o pacote de marcenaria fica congelado (regressão)
def test_pacote_marcenaria_congelado(admin, unidade_id):
    """Mesa de referência: os minutos de cada passo NÃO podem mudar com a generalização do motor."""
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    p = _gerar(admin, pid, unidade_id)
    assert [(s["modulo"], s["tempo_padrao_min"], s["tempo_normal_min"]) for s in p["passos"]] == [
        ("movimentacao", 1.758, 1.6), ("corte", 6.015, 5.52), ("movimentacao", 0.879, 0.8), ("montagem", 6.422, 5.844),
        ("conferencia", 10.989, 10.0)]
    assert p["totais"]["tempo_padrao_min"] == 26.06 and p["totais"]["tempo_por_unidade_min"] == 10.284


# ------------------------------------------------------------------ vocabulário: categorias, nunca minutos
def test_acao_manual_vira_tmu_por_categorias():
    a = aq.AcaoManual(nome="Alimentar", alcance="1_2_passos", corpo="curvar_parcial", pegar="leve", levar="1_2_passos", posicionar="ajuste_leve")
    assert a.indices() == [3, 3, 1, 3, 0, 3, 0] and a.minutos() == pytest.approx(13 * 10 * 0.0006)
    with pytest.raises(Exception):
        aq.AcaoManual(nome="x", alcance="longe")  # fora do vocabulário
    with pytest.raises(Exception):
        aq.EspecModulo(chave="x_1", titulo="X", arquetipo="manual", driver="{area_m2} ** 2")  # fórmula fora do interpretador
    assert "a_min" not in es.PropostaModuloIA.model_fields and "minutos" not in es.PropostaModuloIA.model_fields


# ------------------------------------------------------------------ a IA (regra local) delimita a atividade; só vale validada
def _propor(a, nome, descricao=""):
    r = a.post("/modulos/propor", {"nome": nome, "descricao": descricao})
    assert r.status_code == 201, r.text
    return r.json()


def test_propor_fica_pendente_e_so_entra_no_catalogo_depois_de_validado(admin, unidade_id):
    m = _propor(admin, "Lixar peças", "lixadeira orbital nas faces das peças")
    assert m["status"] == "pendente" and m["arquetipo"] == "processamento_meio" and m["espec"]["driver"] == "{area_m2}"
    assert m["espec"]["taxa"]["unidade"] == "m²/min" and m["dados_faltantes"] and m["exemplo"]["tempo_padrao_min"] > 0
    assert m["chave"] not in {x["chave"] for x in admin.get("/modulos").json()}
    # parâmetro de ficha de módulo NÃO validado não é aceito
    rec = admin.post("/recursos", {"unidade_id": unidade_id, "nome": "Lixadeira", "funcao": m["espec"]["funcao_meio"]}).json()
    nome_taxa = m["espec"]["taxa"]["nome"]
    assert admin.post("/parametros", {"escopo_tipo": "recurso", "escopo_id": rec["id"], "nome": nome_taxa, "valor_num": 0.4}).status_code == 422
    v = admin.post(f"/modulos/empresa/{m['id']}/validar", {})
    assert v.status_code == 200 and v.json()["vigente"] is True
    assert m["chave"] in {x["chave"] for x in admin.get("/modulos").json()}
    assert admin.post("/parametros", {"escopo_tipo": "recurso", "escopo_id": rec["id"], "nome": nome_taxa, "valor_num": 0.4}).status_code == 201
    assert admin.post(f"/modulos/empresa/{m['id']}/validar", {}).status_code == 409  # já decidido


def test_regra_local_escolhe_arquetipos_pela_natureza_da_atividade(admin):
    assert _propor(admin, "Secar verniz", "estufa de secagem")["arquetipo"] == "espera"
    assert _propor(admin, "Levar ao estoque")["arquetipo"] == "deslocamento"
    manual = _propor(admin, "Embalar peça", "plástico bolha à mão")
    assert manual["arquetipo"] == "manual" and manual["espec"]["acoes"]


# ------------------------------------------------------------------ módulo da empresa no plano: tempo pelos construtos
def test_plano_usa_modulo_de_processamento_da_empresa(admin, unidade_id):
    est, cor, mon = _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    m = _propor(admin, "Lixar peças", "lixadeira orbital")
    admin.post(f"/modulos/empresa/{m['id']}/validar", {})
    rec = admin.post("/recursos", {"unidade_id": unidade_id, "nome": "Lixadeira", "funcao": m["espec"]["funcao_meio"], "espaco_id": cor["id"]}).json()
    _ficha(admin, rec["id"], **{m["espec"]["taxa"]["nome"]: 0.4})
    p = _gerar(admin, pid, unidade_id)
    lixar = next(s for s in p["passos"] if s["modulo"] == m["chave"])
    # área: (Tampo 0,5 + 2 Laterais × 0,35) m² × 2 mesas = 2,4 m² a 0,4 m²/min = 6 min de máquina (sem tolerância)
    # + preparo 5 min e manuseio de 6 peças × (13 + 6) × 10 TMU (operador, com ritmo e FT)
    manuseio = 6 * 19 * 10 * 0.0006
    assert lixar["tempo_padrao_min"] == pytest.approx(6.0 + (5.0 + manuseio) * FT, abs=0.01)
    assert lixar["recurso_id"] == rec["id"] and p["totais"]["completo"] is True
    assert [s["modulo"] for s in p["passos"]].index(m["chave"]) < [s["modulo"] for s in p["passos"]].index("montagem")


def test_modulo_manual_com_atributo_livre_so_entra_nas_pecas_que_o_tem(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, tampo, _ = _mesa(admin)
    acao = {"nome": "Passar pincel", "alcance": "ao_alcance", "pegar": "leve", "levar": "ao_alcance", "posicionar": "aproximado"}
    r = admin.post("/modulos/empresa", {"espec": {"titulo": "Envernizar", "arquetipo": "manual", "driver": "{area_m2} * {demaos}",
                                                   "unidade_driver": "m²·demão", "acoes": [acao]}})
    assert r.status_code == 201, r.text
    m = r.json()
    assert admin.post(f"/modulos/empresa/{m['id']}/validar", {}).status_code == 200
    assert admin.patch(f"/produtos/{pid}/componentes/{tampo['id']}", {"atributos": {"demaos": 2}}).json()["atributos"] == {"demaos": 2}
    p = _gerar(admin, pid, unidade_id)
    passo = next(s for s in p["passos"] if s["modulo"] == m["chave"])
    assert passo["componentes"] == ["Tampo"]
    # 0,5 m² × 2 demãos × 2 mesas = 2 unidades do driver × 40 TMU (0,024 min) × FT
    assert passo["tempo_padrao_min"] == pytest.approx(2 * 0.024 * FT, abs=0.002)
    assert admin.patch(f"/produtos/{pid}/componentes/{tampo['id']}", {"atributos": {"Demãos": 2}}).status_code == 422


def test_atividade_sem_modulo_vira_pendencia_e_nao_tempo(admin, unidade_id, monkeypatch):
    from app.services import ia
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    monkeypatch.setattr(ia, "provedor_ativo", lambda empresa: "claude")
    monkeypatch.setattr(ia.claude, "planejar", lambda ctx: es.PlanoProposta.model_validate({
        "passos": [{"nome": "Cortar", "modulo": "corte", "componentes": ["Tampo", "Lateral"], "recurso": "Seccionadora"},
                   {"nome": "Montar", "modulo": "montagem", "grupo": "Corpo", "componentes": ["Tampo", "Lateral"]},
                   {"nome": "Pintar", "modulo": "pintura_epoxi"}],
        "atividades_sem_modulo": ["Aplicar selador"], "confianca": "media"}))
    p = _gerar(admin, pid, unidade_id)
    texto = " | ".join(p["faltantes"])
    assert "Pintar" in texto and "Aplicar selador" in texto and p["totais"]["completo"] is False
    assert all(s["modulo"] != "pintura_epoxi" for s in p["passos"])


# ------------------------------------------------------------------ operação de processo e isolamento
def test_operacao_so_aceita_modulo_do_catalogo_da_empresa(client, admin, unidade_id):
    proc = admin.post("/processos", {"unidade_id": unidade_id, "nome": "P"}).json()
    et = admin.post(f"/processos/{proc['id']}/etapas", {"nome": "E"}).json()
    assert admin.post(f"/etapas/{et['id']}/operacoes", {"nome": "Embalar", "modulo": "embalar_peca"}).status_code == 422
    m = _propor(admin, "Embalar peça", "à mão")
    admin.post(f"/modulos/empresa/{m['id']}/validar", {})
    r = admin.post(f"/etapas/{et['id']}/operacoes", {"nome": "Embalar", "modulo": m["chave"], "item_comprimento_m": 1, "item_largura_m": 0.5})
    assert r.status_code == 201, r.text
    e = admin.get(f"/operacoes/{r.json()['id']}/estimativa?quantidade=10").json()
    assert e["fonte"] == "modulo" and e["execucao_min"] > 0
    b = registrar(client, "Empresa B")
    assert m["chave"] not in {x["chave"] for x in b.get("/modulos").json()}
    assert b.get("/modulos/empresa").json() == []
    assert b.post(f"/modulos/empresa/{m['id']}/rejeitar", {}).status_code == 404


def test_modulo_embutido_nao_pode_ser_sobrescrito(admin):
    m = _propor(admin, "Corte")  # mesma chave de um módulo do pacote embutido
    assert m["chave"] != "corte" and m["chave"].startswith("x_")
