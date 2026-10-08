"""Cálculos determinísticos de tempo (sem IA, sem acesso a banco).

Convenções (seção 10 do documento):
- tempo apontado de uma operação = soma das durações dos apontamentos válidos;
- tempo_realizado = preparação + execução + retrabalho (tempo de trabalho);
- tempo_total     = tempo_realizado + espera;
- desvio          = realizado - estimado (positivo = demorou mais que o previsto);
- eficiência (%)  = estimado / realizado * 100 (acima de 100 = mais rápido que o previsto).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Iterable


def duracao_min(inicio: datetime, fim: datetime | None) -> float | None:
    if fim is None:
        return None
    return max((fim - inicio).total_seconds() / 60.0, 0.0)


def estimar(formula: str, quantidade: float, prep: float | None, unitario: float | None,
            tamanho_lote: float | None = None) -> tuple[float, float | None]:
    """Retorna (preparação, execução). Execução None quando não há base de tempo."""
    prep = prep or 0.0
    if unitario is None:
        return prep, None
    if formula == "fixo":
        return prep, unitario
    if formula == "lote":
        lote = tamanho_lote if tamanho_lote and tamanho_lote > 0 else 1.0
        return prep, unitario * math.ceil(quantidade / lote)
    return prep, unitario * quantidade  # linear


def desvio(realizado: float | None, estimado: float | None) -> float | None:
    if realizado is None or estimado is None:
        return None
    return realizado - estimado


def desvio_pct(realizado: float | None, estimado: float | None) -> float | None:
    if realizado is None or not estimado:
        return None
    return (realizado - estimado) / estimado * 100.0


def eficiencia(estimado: float | None, realizado: float | None) -> float | None:
    if not estimado or not realizado or realizado <= 0:
        return None
    return estimado / realizado * 100.0


def mediana(valores: list[float]) -> float | None:
    if not valores:
        return None
    v = sorted(valores)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def uniao_minutos(intervalos: Iterable[tuple[datetime, datetime]]) -> float:
    """Minutos cobertos por uma lista de intervalos, sem contar sobreposições duas vezes."""
    ordenados = sorted(i for i in intervalos if i[1] > i[0])
    total, atual = 0.0, None
    for ini, fim in ordenados:
        if atual is None:
            atual = [ini, fim]
        elif ini <= atual[1]:
            atual[1] = max(atual[1], fim)
        else:
            total += (atual[1] - atual[0]).total_seconds()
            atual = [ini, fim]
    if atual:
        total += (atual[1] - atual[0]).total_seconds()
    return total / 60.0


def dias_uteis(de: date, ate: date) -> int:
    """Dias úteis (seg-sex) entre as datas, inclusive."""
    if ate < de:
        return 0
    n = 0
    d = de
    while d <= ate:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def arred(v: float | None, casas: int = 1) -> float | None:
    return None if v is None else round(v, casas)
