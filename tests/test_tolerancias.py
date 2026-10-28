"""Fase 8: tolerâncias como fontes plugáveis. Percentual só com fonte; sem fonte é alerta; faltante é pendência; nada digitado."""
from types import SimpleNamespace

import pytest

from app.services import estimativa, tolerancias as tol
from app.services.modelo_tempo import fator_tolerancia
from app.services.tolerancias import base

LEV = {"h_cm": 25, "v_cm": 75, "d_cm": 25, "a_graus": 0, "freq_por_min": 0.2, "duracao": "ate_1h", "pega": "boa"}  # todos os multiplicadores = 1 → RWL = 23 kg


def _ctx(**kw):
    return tol.ContextoTolerancia(**kw)


def test_so_as_constantes_da_oit_quando_nao_ha_mais_condicoes():
    r = tol.calcular()
    assert [(t["categoria"], t["percentual"]) for t in r.aplicadas] == [("necessidades pessoais", 5.0), ("fadiga básica", 4.0)]
    assert all(t["fonte"] for t in r.aplicadas) and r.percentual_total == 9.0
    ft, _ = fator_tolerancia(r.aplicadas)
    assert ft == pytest.approx(1 / 0.91)
    assert list(tol.FONTES) == ["oit_constantes", "niosh", "murrell", "ambiente", "postura"]


def test_percentual_sem_fonte_nao_existe():
    with pytest.raises(ValueError):
        tol.Tolerancia("qualquer", 3.0)                      # sem fonte: proibido
    with pytest.raises(ValueError):
        tol.Tolerancia("qualquer", -1.0, "norma X")
    assert tol.Tolerancia("só alerta", None, justificativa="x").percentual is None


def test_fonte_plugavel_sem_fonte_vira_erro_e_com_fonte_entra_no_ft(monkeypatch):
    monkeypatch.setitem(base.FONTES, "teste", lambda c: base.Saida(itens=[tol.Tolerancia("ruído", 2.0, "Norma de teste", premissa="conversão hipotética")]))
    r = tol.calcular()
    extra = next(t for t in r.aplicadas if t["categoria"] == "ruído")
    assert extra["percentual"] == 2.0 and extra["premissa"] == "conversão hipotética" and r.percentual_total == 11.0
    monkeypatch.setitem(base.FONTES, "teste", lambda c: base.Saida(itens=[tol.Tolerancia("sem fonte", None, justificativa="só avisa")]))
    r = tol.calcular()
    assert r.percentual_total == 9.0 and any(a["msg"] == "só avisa" for a in r.alertas)   # sem fonte: alerta, o tempo não muda


def test_niosh_calcula_li_e_rotula_a_conversao_como_premissa():
    # RWL = 23 kg (multiplicadores todos 1)
    r = tol.calcular(_ctx(levantamento=LEV, carga_kg=23))
    assert r.percentual_total == 9.0 and r.alertas == []                       # LI = 1,0: nada a acrescentar
    r = tol.calcular(_ctx(levantamento=LEV, carga_kg=34.5))                    # LI = 1,5 → faixa 1–2 → 5 %
    li = next(t for t in r.aplicadas if t["categoria"] == "fadiga por carga (LI)")
    assert li["percentual"] == 5.0 and "premissa do sistema" in li["premissa"] and "NIOSH" in li["fonte"]
    assert r.percentual_total == 14.0 and any("Índice de levantamento 1.5" in a["msg"] for a in r.alertas)
    assert any("premissa do sistema" in p for p in r.premissas)


def test_niosh_incompleto_e_pendencia_nao_valor():
    r = tol.calcular(_ctx(levantamento={"h_cm": 25}, carga_kg=10))
    assert r.percentual_total == 9.0 and any("NIOSH" in p and "incompletos" in p for p in r.pendencias)


def test_murrell_usa_o_limite_do_perfil_e_sem_ele_pede_o_dado():
    perfil = SimpleNamespace(limite_energetico_kcal_min=4.0)
    r = tol.calcular(_ctx(gasto_energetico_kcal_min=5.0, perfil=perfil))
    m = next(t for t in r.aplicadas if "Murrell" in t["categoria"])
    assert m["percentual"] == pytest.approx(round(((5 - 4) / (5 - 1.5)) / (1 + (5 - 4) / (5 - 1.5)) * 100, 2)) == pytest.approx(22.22, abs=0.01)
    sem = tol.calcular(_ctx(gasto_energetico_kcal_min=5.0, perfil=SimpleNamespace(limite_energetico_kcal_min=None)))
    assert sem.percentual_total == 9.0 and any("limite energético" in p for p in sem.pendencias)
    assert tol.calcular(_ctx(gasto_energetico_kcal_min=3.0, perfil=perfil)).percentual_total == 9.0   # abaixo do limite: nada


def test_ambiente_so_alerta_e_nunca_inventa_percentual():
    quente = SimpleNamespace(id=1, nome="Forno", temperatura_c=36, umidade_pct=80, ruido_db=92, iluminancia_lux=80)
    r = tol.calcular(_ctx(locais=[quente, quente]))                            # o mesmo local duas vezes conta uma vez
    assert r.percentual_total == 9.0 and len(r.aplicadas) == 2
    msgs = [a["msg"] for a in r.alertas]
    assert sum("Ruído" in m for m in msgs) == 1 and sum("temperatura" in m for m in msgs) == 1
    assert all(a["fonte"] for a in r.alertas)
    assert any("não alteram o tempo" in p for p in r.premissas)
    assert tol.calcular(_ctx(locais=[SimpleNamespace(id=2, nome="Sala", temperatura_c=22, umidade_pct=None, ruido_db=60, iluminancia_lux=None)])).alertas == []


def test_postura_e_so_ponto_de_extensao_e_fadiga_de_turno_fica_fora():
    from app.services.tolerancias import postura
    assert postura.POSTURA_AVALIADA is False
    r = tol.calcular(_ctx(postura="em_pe"))
    assert r.percentual_total == 9.0 and any("RULA não implementado" in p for p in r.premissas)
    assert tol.FADIGA_DE_TURNO in r.premissas and tol.FADIGA_DE_TURNO in tol.calcular().premissas


def test_operacao_com_levantamento_recebe_a_tolerancia_pelas_fontes(db_factory):
    db = db_factory()
    op = SimpleNamespace(espaco_origem_id=None, espaco_destino_id=None, levantamento=LEV, item_peso_kg=None, gasto_energetico_kcal_min=None, postura_trabalho="")
    t = estimativa.tolerancias_da_operacao(db, 1, op, 34.5, None)
    assert {x["categoria"]: x["percentual"] for x in t} == {"necessidades pessoais": 5.0, "fadiga básica": 4.0, "fadiga por carga (LI)": 5.0}
    sem = SimpleNamespace(espaco_origem_id=None, espaco_destino_id=None, levantamento=None, item_peso_kg=None, gasto_energetico_kcal_min=None, postura_trabalho="")
    assert sum(x["percentual"] for x in estimativa.tolerancias_da_operacao(db, 1, sem, 10, None)) == 9.0
