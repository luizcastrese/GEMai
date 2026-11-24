"""Efeito de uma intervenção de método: pedidos do mesmo produto ANTES × DEPOIS do ajuste.

Fecha o ciclo padrão ↔ fluxo com evidência: se o ajuste do fluxo funcionou, os pedidos seguintes ficam mais perto do tempo padrão.
Por pedido concluído do produto, r = realizado ÷ previsto (tempo padrão da ordem; ou, quando a intervenção é de uma atividade e há
medição passo a passo, a razão daquela etapa). Resumo de cada lado: desvio típico (mediana de ln r, em %) e erro típico
(mediana de |ln r|, em %). O efeito é a variação do erro típico. Com menos de 2 pedidos de cada lado, o resultado é "inconclusivo":
o sistema não declara efeito sem dado.
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Apontamento, Intervencao, Ordem
from . import timecalc

MIN_LADO = 2


def _razoes_por_pedido(db: Session, empresa_id: int, produto_id: int, modulo: str | None) -> list[tuple[object, float]]:
    """[(concluído em, realizado ÷ previsto)] dos pedidos concluídos do produto."""
    ordens = list(db.scalars(select(Ordem).where(Ordem.empresa_id == empresa_id, Ordem.produto_id == produto_id,
                                                 Ordem.status == "concluida", Ordem.concluida_em.is_not(None))))
    if not ordens:
        return []
    apts = list(db.scalars(select(Apontamento).where(
        Apontamento.empresa_id == empresa_id, Apontamento.ordem_id.in_([o.id for o in ordens]), Apontamento.status == "aprovado",
        Apontamento.anulado.is_(False), Apontamento.fim.is_not(None), Apontamento.tipo.in_(("execucao", "preparacao")))))
    por_ordem: dict[int, list] = {}
    for a in apts:
        por_ordem.setdefault(a.ordem_id, []).append(a)
    out = []
    for o in ordens:
        lista = por_ordem.get(o.id)
        if not lista:
            continue
        passo = not any((a.dados_extras or {}).get("origem") == "total_do_pedido" for a in lista)
        if modulo and passo:
            ops = [x for x in o.operacoes if x.modulo == modulo]
            prev = sum((x.tempo_prep_est_min or 0.0) + (x.tempo_exec_est_min or 0.0) for x in ops)
            real = timecalc.uniao_minutos((a.inicio, a.fim) for a in lista if a.ordem_operacao_id in {x.id for x in ops})
        else:
            prev, real = o.tempo_estimado_min or 0.0, timecalc.uniao_minutos((a.inicio, a.fim) for a in lista)
        if prev > 0 and real > 0:
            out.append((o.concluida_em, real / prev))
    return out


def _lado(rs: list[float]) -> dict:
    if not rs:
        return {"pedidos": 0, "desvio_tipico_pct": None, "erro_tipico_pct": None}
    ls = [math.log(r) for r in rs]
    return {"pedidos": len(rs), "desvio_tipico_pct": round((math.exp(timecalc.mediana(ls)) - 1) * 100, 1),
            "erro_tipico_pct": round((math.exp(timecalc.mediana([abs(v) for v in ls])) - 1) * 100, 1)}


def efeito(db: Session, i: Intervencao) -> dict:
    pares = _razoes_por_pedido(db, i.empresa_id, i.produto_id, i.modulo)
    antes = _lado([r for quando, r in pares if quando < i.criado_em])
    depois = _lado([r for quando, r in pares if quando >= i.criado_em])
    ok = antes["pedidos"] >= MIN_LADO and depois["pedidos"] >= MIN_LADO
    delta = round(depois["erro_tipico_pct"] - antes["erro_tipico_pct"], 1) if ok else None
    if not ok:
        texto = f"Inconclusivo: {antes['pedidos']} pedido(s) antes e {depois['pedidos']} depois (são precisos {MIN_LADO} de cada lado)."
    elif delta < 0:
        texto = f"O ajuste aproximou o real do padrão: erro típico de {antes['erro_tipico_pct']:g} % para {depois['erro_tipico_pct']:g} %."
    else:
        texto = f"Sem melhora: erro típico de {antes['erro_tipico_pct']:g} % para {depois['erro_tipico_pct']:g} %."
    return {"antes": antes, "depois": depois, "variacao_erro_pp": delta, "conclusivo": ok, "texto": texto}


def como_dict(db: Session, i: Intervencao) -> dict:
    return {"id": i.id, "produto_id": i.produto_id, "plano_id": i.plano_id, "modulo": i.modulo, "principio": i.principio,
            "descricao": i.descricao, "criado_em": i.criado_em.isoformat() if i.criado_em else None, "efeito": efeito(db, i)}


def do_produto(db: Session, empresa_id: int, produto_id: int) -> list[dict]:
    rows = db.scalars(select(Intervencao).where(Intervencao.empresa_id == empresa_id, Intervencao.produto_id == produto_id)
                      .order_by(Intervencao.criado_em.desc()))
    return [como_dict(db, i) for i in rows]
