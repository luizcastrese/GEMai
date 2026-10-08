from datetime import datetime, timedelta, timezone

from app.services import timecalc as t


def dt(h, m=0):
    return datetime(2026, 1, 5, h, m, tzinfo=timezone.utc)


def test_formulas():
    assert t.estimar("linear", 10, 5, 2) == (5, 20)
    assert t.estimar("fixo", 10, 5, 30) == (5, 30)
    assert t.estimar("lote", 25, 0, 10, tamanho_lote=10) == (0, 30)  # 3 lotes
    assert t.estimar("linear", 10, 5, None) == (5, None)  # sem base: não inventa tempo


def test_desvio_eficiencia():
    assert t.desvio(12, 10) == 2
    assert t.desvio_pct(12, 10) == 20
    assert t.eficiencia(10, 12) == 10 / 12 * 100
    assert t.eficiencia(None, 5) is None and t.desvio_pct(5, 0) is None


def test_mediana_e_duracao():
    assert t.mediana([3, 1, 2]) == 2 and t.mediana([1, 2, 3, 4]) == 2.5 and t.mediana([]) is None
    assert t.duracao_min(dt(8), dt(9, 30)) == 90 and t.duracao_min(dt(8), None) is None


def test_uniao_nao_conta_sobreposicao():
    assert t.uniao_minutos([(dt(8), dt(10)), (dt(9), dt(11)), (dt(13), dt(14))]) == 240


def test_dias_uteis():
    from datetime import date
    assert t.dias_uteis(date(2026, 1, 5), date(2026, 1, 11)) == 5  # seg a dom
    assert t.dias_uteis(date(2026, 1, 11), date(2026, 1, 5)) == 0
