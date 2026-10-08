"""Estimativa de tempo por operação (o "tempo planejado" do gêmeo digital).

Prioridade da base de cálculo (sempre explicitada em `fonte`):
1. `historico`  – mediana de apontamentos APROVADOS, se houver amostras suficientes;
2. `parametro`  – parâmetros vigentes e validados por uma pessoa (informados/medidos/calculados);
3. `modelo_ia`  – modelo de tempo (elementos + contorno físico) proposto pela IA e calculado pelo
                  sistema; vem rotulado como validado ou não (`validada`);
4. `sem_base`   – nada disponível ou dados físicos faltando: o sistema não chuta.
Dado medido/validado por pessoa sempre prevalece sobre a estimativa da IA.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Apontamento, Ordem, OrdemOperacao, Parametro
from . import modelo_tempo, timecalc


@dataclass
class Estimativa:
    prep: float | None
    exec: float | None
    fonte: str
    amostras: int = 0
    avisos: list[str] = field(default_factory=list)
    detalhe: list | None = None  # elementos do modelo, em minutos
    validada: bool = True  # False = estimativa da IA ainda não validada por uma pessoa

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


def estimar_operacao(db: Session, empresa_id: int, operacao, quantidade: float, produto=None, recurso=None) -> Estimativa:
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
    if fonte != "sem_base":
        prep = val("tempo_preparacao_min")
        if len(preps) >= s.min_amostras_historico:
            prep = timecalc.mediana(preps)
        p, e = timecalc.estimar(operacao.formula_tipo, quantidade, prep, unit, lote)
        return Estimativa(prep=p, exec=e, fonte=fonte, amostras=len(amostras), avisos=aviso)

    # sem histórico nem parâmetro: tenta o modelo de tempo (gêmeo digital)
    m = modelo_tempo.modelo_ativo(db, empresa_id, operacao.id)
    if m and (m.status_validacao == "validado" or s.usar_modelo_ia_nao_validado):
        ctx = modelo_tempo.montar_contexto(db, empresa_id, operacao, quantidade, produto, recurso)
        r = modelo_tempo.calcular(m.elementos, m.fator_ambiente, ctx)
        if r.completo:
            if m.status_validacao != "validado":
                aviso.append("Tempo estimado pela IA e ainda não validado por um gestor.")
            prep = r.prep
            if len(preps) >= s.min_amostras_historico:
                prep = timecalc.mediana(preps)
            return Estimativa(prep=prep, exec=r.exec, fonte="modelo_ia", amostras=len(amostras), avisos=aviso,
                              detalhe=r.elementos, validada=m.status_validacao == "validado")
        aviso.append("Modelo de tempo incompleto: " + "; ".join(r.faltantes or ["modelo sem elementos"]))
        return Estimativa(prep=None, exec=None, fonte="sem_base", amostras=len(amostras), avisos=aviso,
                          detalhe=r.elementos, validada=False)
    aviso.append("Sem parâmetro validado, histórico suficiente ou modelo de tempo: tempo não estimado.")
    return Estimativa(prep=None, exec=None, fonte="sem_base", amostras=len(amostras), avisos=aviso)
