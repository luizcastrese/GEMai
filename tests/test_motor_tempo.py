"""Motor de cálculo de tempo (vocabulário fechado, sem eval), limites de segurança da IA e perfil de mão de obra."""
import pytest

from app.services import ergonomia as erg
from app.services import modelo_tempo as mt
from tests.conftest import criar_usuario, registrar

FT = 1 / (1 - 0.09)  # tolerâncias padrão: 5% pessoais + 4% fadiga básica (OIT)


def test_motor_calcula_e_acusa_dado_faltante():
    els = [
        {"nome": "prep", "tipo": "preparacao", "metodo": "fixo", "por_unidade": False, "driver": "nenhum", "a_min": 5, "b_min": 0},
        {"nome": "desl", "tipo": "deslocamento", "metodo": "deslocamento", "velocidade_m_min": 60, "itens_por_viagem": 5,
         "ida_e_volta": True, "a_min": 0, "b_min": 0},
        {"nome": "manu", "tipo": "manuseio", "metodo": "linear_driver", "por_unidade": True, "driver": "peso_kg",
         "a_min": 0.1, "b_min": 0.01, "paralelizavel": True},
        {"nome": "maq", "tipo": "processamento", "metodo": "capacidade_recurso", "a_min": 0, "b_min": 0},
    ]
    r = mt.calcular(els, 1.0, mt.Contexto(quantidade=10, num_pessoas=2, peso_kg=8, distancia_m=30, capacidade_un_h=60))
    assert (r.prep, r.exec, r.completo) == (5.0, 12.9, True)  # 2 viagens·(30/60)·2 + 0,9 + 10
    r2 = mt.calcular(els, 1.0, mt.Contexto(quantidade=10))
    assert not r2.completo and len(r2.faltantes) == 3  # nunca vira zero em silêncio
    assert mt.calcular(els, 2.0, mt.Contexto(quantidade=10, num_pessoas=2, peso_kg=8, distancia_m=30, capacidade_un_h=60)).exec == 25.8


def test_vocabulario_fechado_e_saneamento():
    s = mt.sanear_elementos([mt.ElementoTempo.model_validate({"nome": "x", "metodo": "fixo", "a_min": 1e12, "velocidade_m_min": -5})])
    assert s[0].a_min == 100_000
    with pytest.raises(Exception):  # nada que a IA escreva vira código: método fora do vocabulário é recusado
        mt.ElementoTempo.model_validate({"nome": "x", "metodo": "__import__('os').system('id')"})


def test_capacidade_normalizada():
    assert mt.capacidade_por_hora(30, "un/h") == 30 and mt.capacidade_por_hora(2, "un/min") == 120
    assert mt.capacidade_por_hora(100, "un/dia") is None and mt.capacidade_por_hora(None, "un/h") is None


def test_murrell():
    assert erg.murrell_fracao_descanso(6, 4) == pytest.approx(2 / 4.5)  # 26,7 min a cada 60 min
    assert erg.murrell_fracao_descanso(3, 4) == 0 and erg.murrell_fracao_descanso(6, None) == 0


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
    s = mt.sanear_elementos([mt.ElementoTempo(nome="x", metodo="indices_most", indices_most=[2, 7, 100])])
    assert all(i in mt.INDICES_MOST for i in s[0].indices_most)


def test_perfil_crud_validacoes_e_isolamento(client, gestor, unidade_id):
    corpo = {"unidade_id": unidade_id, "nome": "Perfil A", "sexo": "feminino", "estatura_cm": 160, "peso_corporal_kg": 58, "ritmo_pct": 105}
    p = gestor.post("/perfis-mao-de-obra", corpo).json()
    assert p["sexo"] == "feminino" and p["ritmo_pct"] == 105
    assert gestor.post("/perfis-mao-de-obra", {"unidade_id": unidade_id, "nome": "Perfil A"}).status_code == 409
    assert gestor.post("/perfis-mao-de-obra", {"unidade_id": unidade_id, "nome": "X", "ritmo_pct": 300}).status_code == 422
    assert gestor.post("/perfis-mao-de-obra", {"unidade_id": unidade_id, "nome": "Y", "sexo": "outro"}).status_code == 422
    assert gestor.delete(f"/perfis-mao-de-obra/{p['id']}").status_code == 405  # só desativa
    b = registrar(client, "Empresa B")
    assert b.get(f"/perfis-mao-de-obra/{p['id']}").status_code == 404
    gb = criar_usuario(b, "g@b.com", [b.unidade_id])
    assert gb.patch(f"/unidades/{b.unidade_id}", {"perfil_equipe_id": p["id"]}).status_code == 422  # perfil alheio

