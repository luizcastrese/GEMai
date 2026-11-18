"""Piloto sem fricção: pedido em dois toques, pedido aberto ao confirmar, preço pela hora, calibração robusta para poucas amostras
(Hampel + credibilidade de flutuação limitada) e indicadores do piloto calculados dos dados que o sistema já guarda."""
import math

import pytest

from app.models import Apontamento, OrdemOperacao
from tests.conftest import criar_usuario
from tests.test_plano import _cadastrar_contorno, _gerar, _mesa


def _pedido(a, pid, u, **kw):
    """Gera o plano, confirma abrindo o pedido e devolve (plano, ordem)."""
    p = _gerar(a, pid, u, **kw)
    r = a.c.post(f"/api/v1/planos/{p['id']}/confirmar?abrir_pedido=true", headers=a.h)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["status"] == "confirmado" and c["ordem_id"]
    return c, a.get(f"/ordens/{c['ordem_id']}").json()


def _previsto_normal(db_factory, ordem_id):
    db = db_factory()
    try:
        return sum(x.previsto_normal_min or 0 for x in db.query(OrdemOperacao).filter(OrdemOperacao.ordem_id == ordem_id))
    finally:
        db.close()


@pytest.fixture
def mesa(admin, unidade_id):
    _cadastrar_contorno(admin, unidade_id)
    pid, _, _ = _mesa(admin)
    return pid


# ------------------------------------------------------------------ dois toques
def test_comecei_terminei_fecha_o_pedido_e_distribui_pelo_previsto(admin, unidade_id, mesa, db_factory):
    _, o = _pedido(admin, mesa, unidade_id)
    assert admin.post(f"/ordens/{o['id']}/terminar", {}).status_code == 422  # sem "Comecei" e sem horas
    assert admin.post(f"/ordens/{o['id']}/comecar").json()["status"] == "em_producao"
    r = admin.post(f"/ordens/{o['id']}/terminar", {"horas": 1.0})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ordem"]["status"] == "concluida" and d["total_min"] == 60.0 and d["conferencia_pendente"] is False
    db = db_factory()
    apts = db.query(Apontamento).filter(Apontamento.ordem_id == o["id"]).all()
    previstos = {x.id: x.previsto_normal_min for x in db.query(OrdemOperacao).filter(OrdemOperacao.ordem_id == o["id"])}
    db.close()
    assert apts and all(a.status == "aprovado" and a.dados_extras["origem"] == "total_do_pedido" for a in apts)
    total_prev = sum(v for v in previstos.values() if v)
    for a in apts:  # cada passo recebe a parte proporcional ao seu previsto, em intervalos consecutivos
        assert (a.fim - a.inicio).total_seconds() / 60 == pytest.approx(60 * previstos[a.ordem_operacao_id] / total_prev, abs=0.01)
    assert admin.post(f"/ordens/{o['id']}/terminar", {"horas": 1.0}).status_code == 409  # já encerrado


def test_equipe_maior_mantem_os_dois_olhos(admin, unidade_id, mesa):
    for i in range(2):
        criar_usuario(admin, f"pessoa{i}@empresaa.com")
    _, o = _pedido(admin, mesa, unidade_id)
    d = admin.post(f"/ordens/{o['id']}/terminar", {"horas": 0.5}).json()
    assert d["conferencia_pendente"] is True


def test_preco_minimo_pela_hora_da_empresa(admin, unidade_id, mesa):
    assert _gerar(admin, mesa, unidade_id)["custo_mao_de_obra"] is None
    assert admin.patch("/empresa", {"valor_hora": 40}).json()["valor_hora"] == 40
    p = _gerar(admin, mesa, unidade_id)
    c = p["custo_mao_de_obra"]
    assert c["total"] == pytest.approx(p["totais"]["horas_homem"] * 40, abs=0.01)
    assert c["por_unidade"] == pytest.approx(c["total"] / p["quantidade"], abs=0.01)


# ------------------------------------------------------------------ calibração robusta para poucos pedidos
def _medir(admin, unidade_id, mesa, db_factory, fator):
    _, o = _pedido(admin, mesa, unidade_id)
    horas = fator * _previsto_normal(db_factory, o["id"]) / 60
    assert admin.post(f"/ordens/{o['id']}/terminar", {"horas": horas}).status_code == 200


def test_poucos_pedidos_ja_geram_proposta_preliminar_e_o_nivel_geral_e_declarado(admin, unidade_id, mesa, db_factory):
    for _ in range(3):
        _medir(admin, unidade_id, mesa, db_factory, 1.5)
    r = admin.post("/calibracao/modulos", {"unidade_id": unidade_id}).json()
    m = next(x for x in r["modulos"] if x["modulo"] == "montagem" and x["produto_id"] is None)
    z = math.sqrt(3 / 10)
    assert m["status"] == "preliminar" and m["credibilidade"] == pytest.approx(z, abs=1e-4)
    assert m["fator_sugerido"] == pytest.approx(1 + z * 0.5, abs=1e-3) and m["total_do_pedido"] == 3
    assert "PRELIMINAR" in m["nota"] and "nível geral" in m["nota"]


def test_identificador_de_hampel_descarta_o_pedido_absurdo(admin, unidade_id, mesa, db_factory):
    for f in (1.2, 1.18, 1.22, 1.2, 1.21, 1.19):
        _medir(admin, unidade_id, mesa, db_factory, f)
    _medir(admin, unidade_id, mesa, db_factory, 20.0)  # pedido esquecido aberto
    m = next(x for x in admin.post("/calibracao/modulos", {"unidade_id": unidade_id}).json()["modulos"]
             if x["modulo"] == "montagem" and x["produto_id"] is None)
    assert m["descartadas"] == 1 and m["amostras"] == 6 and "Hampel" in m["nota"]
    assert m["fator_sugerido"] == pytest.approx(1 + math.sqrt(6 / 10) * 0.2, abs=0.01)


# ------------------------------------------------------------------ indicadores do piloto
def test_indicadores_do_piloto_vem_dos_dados_do_sistema(admin, unidade_id, mesa, db_factory):
    _medir(admin, unidade_id, mesa, db_factory, 1.0)
    _pedido(admin, mesa, unidade_id)  # aberto e não medido
    m = admin.post("/modulos/propor", {"nome": "Lixar peças", "descricao": "lixadeira orbital"}).json()
    admin.post(f"/modulos/empresa/{m['id']}/validar", {})
    d = admin.get("/pesquisa/indicadores").json()
    assert d["uso"]["planos"] == 2 and d["uso"]["planos_com_pedido"] == 2 and d["uso"]["minutos_do_cadastro_ao_primeiro_plano"] is not None
    assert d["medicao"] == {"pedidos_abertos": 2, "pedidos_medidos": 1, "fracao_medida": 0.5, "formas": {"total": 1}}
    px = d["previsto_x_realizado"]
    assert px["pedidos_sem_calibracao"] == 1 and px["pedidos_com_calibracao"] == 0 and px["erro_tipico_sem_calibracao_pct"] is not None
    assert d["atividades"] == {"ia_validadas_sem_edicao": 1}
    csv = admin.c.get("/api/v1/pesquisa/pedidos.csv", headers=admin.h)
    assert csv.status_code == 200 and csv.text.count("\n") == 2 and "previsto_min" in csv.text
