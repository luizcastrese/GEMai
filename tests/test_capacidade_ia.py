"""Capacidade do equipamento: a IA só PROPÕE (nada é gravado); medição do usuário prevalece e fica rotulada."""
import base64

from app.services.ia import esquemas
from tests.conftest import registrar

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 32).decode()


def _equip(a, u):
    return a.post("/recursos", {"unidade_id": u, "nome": "Seccionadora", "funcao": "corte"}).json()


def test_estimar_nao_grava_e_sem_dado_nao_chuta(admin, unidade_id):
    r = _equip(admin, unidade_id)
    out = admin.post(f"/recursos/{r['id']}/estimar-capacidade", {"descricao": "Seccionadora Fulano 3200"})
    assert out.status_code == 200
    j = out.json()
    assert j["pecas_por_hora"] is None and j["dados_faltantes"]          # provedor local não inventa número
    assert admin.get(f"/recursos/{r['id']}").json()["capacidade"] is None  # nada foi salvo


def test_estimar_aproveita_numero_do_texto_e_rotula_origem(admin, unidade_id):
    r = _equip(admin, unidade_id)
    j = admin.post(f"/recursos/{r['id']}/estimar-capacidade", {"descricao": "faz uns 45 peças por hora"}).json()
    assert j["pecas_por_hora"] == 45 and j["confianca"] == "baixa"
    ok = admin.patch(f"/recursos/{r['id']}", {"capacidade": j["pecas_por_hora"], "capacidade_unidade": "un/h", "capacidade_origem": "ia"})
    assert ok.status_code == 200 and ok.json()["capacidade_origem"] == "ia"


def test_validacoes_de_entrada(admin, unidade_id):
    r = _equip(admin, unidade_id)
    url = f"/recursos/{r['id']}/estimar-capacidade"
    assert admin.post(url, {"descricao": ""}).status_code == 422
    assert admin.post(url, {"imagem_base64": "@@@", "imagem_tipo": "image/png"}).status_code == 422
    assert admin.post(url, {"imagem_base64": PNG, "imagem_tipo": "image/jpeg"}).status_code == 422  # tipo não confere
    assert admin.post(url, {"imagem_base64": PNG, "imagem_tipo": "image/png"}).status_code == 200


def test_sanear_capacidade_descarta_valores_absurdos():
    c = esquemas.sanear_capacidade(esquemas.CapacidadeIA(pecas_por_hora=-5, minimo=1, maximo=2))
    assert c.pecas_por_hora is None and c.minimo is None
    c = esquemas.sanear_capacidade(esquemas.CapacidadeIA(pecas_por_hora=40, minimo=60, maximo=10))
    assert c.minimo <= 40 <= c.maximo


def test_outra_empresa_nao_ve_o_equipamento(admin, unidade_id, client):
    r = _equip(admin, unidade_id)
    outro = registrar(client, "Outra")
    assert outro.post(f"/recursos/{r['id']}/estimar-capacidade", {"descricao": "x y z"}).status_code == 404
