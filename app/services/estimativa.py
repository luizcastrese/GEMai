"""Estimativa de tempo por operação.

Prioridade da base de cálculo (sempre explicitada em `fonte`):
1. `historico`  – mediana de apontamentos APROVADOS, se houver amostras suficientes;
2. `parametro`  – parâmetros vigentes e validados (informados/medidos/calculados);
3. `sem_base`   – nada validado: o sistema não inventa tempo.
Parâmetros sugeridos pela IA e ainda não validados nunca entram no cálculo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Apontamento, Ordem, OrdemOperacao, Parametro
from . import timecalc


@dataclass
class Estimativa:
    prep: float | None
    exec: float | None
    fonte: str
    amostras: int = 0
    avisos: list[str] = field(default_factory=list)

    @property
    def total(self) -> float | None:
        return None if self.exec is None else (self.prep or 0.0) + self.exec


def parametros_vigentes(db: Session, empresa_id: int, escopo_tipo: str, escopo_id: int) -> dict[str, Parametro]:
    rows = db.scalars(select(Parametro).where(
        Parametro.empresa_id == empresa_id, Parametro.escopo_tipo == escopo_tipo,
        Parametro.escopo_id == escopo_id, Parametro.vigente.is_(True),
        Parametro.status_validacao == "validado"))
    return {p.nome: p for p in rows}


def historico_operacao(db: Session, empresa_id: int, operacao_id: int, formula: str,
                       tamanho_lote: float | None) -> tuple[list[float], list[float]]:
    """(amostras de tempo de execução por unidade/lote/execução, amostras de preparação)."""
    ops = db.execute(
        select(OrdemOperacao.id, OrdemOperacao.qtd_planejada)
        .join(Ordem, Ordem.id == OrdemOperacao.ordem_id)
        .where(OrdemOperacao.empresa_id == empresa_id, OrdemOperacao.operacao_id == operacao_id,
               OrdemOperacao.status == "concluida", Ordem.status != "cancelada")
    ).all()
    if not ops:
        return [], []
    plan = {i: q for i, q in ops}
    apts = db.scalars(select(Apontamento).where(
        Apontamento.empresa_id == empresa_id, Apontamento.ordem_operacao_id.in_(plan),
        Apontamento.status == "aprovado", Apontamento.anulado.is_(False),
        Apontamento.fim.is_not(None), Apontamento.tipo.in_(("execucao", "preparacao"))))
    exec_min: dict[int, float] = {}
    qtd: dict[int, float] = {}
    prep_min: dict[int, float] = {}
    for a in apts:
        d = timecalc.duracao_min(a.inicio, a.fim) or 0.0
        if a.tipo == "execucao":
            exec_min[a.ordem_operacao_id] = exec_min.get(a.ordem_operacao_id, 0.0) + d
            qtd[a.ordem_operacao_id] = qtd.get(a.ordem_operacao_id, 0.0) + a.quantidade_boa + a.quantidade_refugo
        else:
            prep_min[a.ordem_operacao_id] = prep_min.get(a.ordem_operacao_id, 0.0) + d
    amostras = []
    for oo_id, dur in exec_min.items():
        if dur <= 0:
            continue
        if formula == "fixo":
            amostras.append(dur)
        elif formula == "lote":
            lote = tamanho_lote if tamanho_lote and tamanho_lote > 0 else 1.0
            amostras.append(dur / max(math.ceil(plan[oo_id] / lote), 1))
        elif qtd.get(oo_id, 0) > 0:
            amostras.append(dur / qtd[oo_id])
    return amostras, [v for v in prep_min.values() if v > 0]


def estimar_operacao(db: Session, empresa_id: int, operacao, quantidade: float) -> Estimativa:
    s = get_settings()
    params = parametros_vigentes(db, empresa_id, "operacao", operacao.id)
    val = lambda n: params[n].valor_num if n in params else None  # noqa: E731
    lote = val("tamanho_lote")
    aviso: list[str] = []
    amostras, preps = historico_operacao(db, empresa_id, operacao.id, operacao.formula_tipo, lote)

    unit, fonte = None, "sem_base"
    if len(amostras) >= s.min_amostras_historico:
        unit, fonte = timecalc.mediana(amostras), "historico"
    elif val("tempo_unitario_min") is not None:
        unit, fonte = val("tempo_unitario_min"), "parametro"
        if amostras:
            aviso.append(f"Histórico insuficiente ({len(amostras)}/{s.min_amostras_historico} amostras aprovadas).")
    else:
        aviso.append("Sem parâmetro validado nem histórico suficiente: tempo não estimado.")
    prep = val("tempo_preparacao_min")
    if len(preps) >= s.min_amostras_historico:
        prep = timecalc.mediana(preps)
    p, e = timecalc.estimar(operacao.formula_tipo, quantidade, prep, unit, lote)
    return Estimativa(prep=p, exec=e, fonte=fonte, amostras=len(amostras), avisos=aviso)
