"""Pedido em dois toques: o jeito mais simples de medir o real.

Para o pequeno negócio, apontar cada passo da ordem é fricção demais. Aqui o pedido inteiro é medido de uma vez:
- "Comecei" marca o início do pedido (libera a ordem, se preciso);
- "Terminei" (ou "Levei X horas", sem ter marcado o início) fecha o pedido com o TEMPO CORRIDO total.

O total é distribuído pelos passos na PROPORÇÃO do tempo normal previsto de cada um, em intervalos consecutivos, e cada parte
vira um apontamento rotulado `origem = total_do_pedido`. Consequência declarada (e mostrada na calibração): esses registros informam
o NÍVEL GERAL do previsto (o pedido levou X % a mais), não o erro de cada atividade isolada. Passos sem tempo previsto não recebem
parte do total. Em equipe de até 2 pessoas o registro já vale (não há uma segunda pessoa para conferir); em equipes maiores ele
segue a regra dos dois olhos e aguarda a aprovação de outra pessoa.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select

from .. import audit
from ..models import Apontamento, Ordem, Usuario

EQUIPE_SEM_CONFERENCIA = 2  # até este nº de usuários ativos, o registro do total já vale


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _equipe(ctx) -> int:
    return ctx.db.scalar(select(func.count(Usuario.id)).where(Usuario.empresa_id == ctx.empresa_id, Usuario.ativo.is_(True))) or 0


def comecar(ctx, o: Ordem) -> Ordem:
    if o.status in ("concluida", "cancelada"):
        raise HTTPException(409, "Este pedido já foi encerrado.")
    antes = o.status
    agora = _agora()
    if o.status == "planejada":
        o.liberada_em = agora
    o.status = "em_producao"
    o.iniciada_em = o.iniciada_em or agora
    ctx.auditar("pedido.comecar", "ordem", o.id, {"status": antes}, {"status": o.status, "iniciada_em": o.iniciada_em.isoformat()})
    return o


def terminar(ctx, o: Ordem, horas: float | None = None, pessoa_id: int | None = None) -> dict:
    """Fecha o pedido com o tempo corrido (agora − início, ou `horas` informadas) distribuído pelos passos."""
    if o.status in ("concluida", "cancelada"):
        raise HTTPException(409, "Este pedido já foi encerrado.")
    abertos = ctx.db.scalar(select(func.count(Apontamento.id)).where(Apontamento.ordem_id == o.id, Apontamento.fim.is_(None),
                                                                      Apontamento.anulado.is_(False)))
    if abertos:
        raise HTTPException(409, "Há registros de tempo em aberto neste pedido: encerre-os ou use a fila detalhada.")
    agora = _agora()
    if horas is not None:
        total_min = horas * 60.0
        inicio = agora - timedelta(minutes=total_min)
    else:
        if not o.iniciada_em:
            raise HTTPException(422, "Toque em \"Comecei\" no início, ou informe quantas horas levou.")
        inicio = o.iniciada_em
        total_min = (agora - inicio).total_seconds() / 60.0
    if total_min <= 0:
        raise HTTPException(422, "O tempo do pedido precisa ser maior que zero.")
    ops = [x for x in o.operacoes if x.status in ("pendente", "em_andamento")]
    pesos = {x.id: (x.previsto_normal_min or 0.0) for x in ops}
    soma = sum(pesos.values())
    vale = _equipe(ctx) <= EQUIPE_SEM_CONFERENCIA
    t = inicio
    criados = 0
    for x in ops:
        parte = total_min * pesos[x.id] / soma if soma > 0 else 0.0
        if parte > 0:
            fim = t + timedelta(minutes=parte)
            ctx.db.add(Apontamento(
                empresa_id=ctx.empresa_id, unidade_id=o.unidade_id, ordem_id=o.id, ordem_operacao_id=x.id, tipo="execucao",
                pessoa_id=pessoa_id, inicio=t, fim=fim, quantidade_boa=x.qtd_planejada or 0,
                dados_extras={"origem": "total_do_pedido", "fracao": round(pesos[x.id] / soma, 6), "total_min": round(total_min, 3)},
                observacao="Apontado no total do pedido e distribuído pelo tempo previsto de cada passo.",
                status="aprovado" if vale else "registrado", registrado_por=ctx.usuario.id,
                decidido_por=ctx.usuario.id if vale else None, decidido_em=agora if vale else None))
            criados += 1
            t = fim
        x.status, x.concluida_em, x.concluida_por = "concluida", agora, ctx.usuario.id
    antes = o.status
    o.iniciada_em = o.iniciada_em or inicio
    o.liberada_em = o.liberada_em or inicio
    o.status, o.concluida_em = "concluida", agora
    previsto = o.tempo_estimado_min
    ctx.auditar("pedido.terminar", "ordem", o.id, {"status": antes},
                {"status": "concluida", "total_min": round(total_min, 3), "registros": criados, "conferido": vale})
    return {"total_min": round(total_min, 2), "previsto_min": previsto, "registros": criados, "conferencia_pendente": not vale,
            "desvio_pct": round((total_min / previsto - 1) * 100, 1) if previsto else None}


__all__ = ["comecar", "terminar", "audit"]
