"""Dashboard do gestor e auditoria."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..deps import Ctx, get_ctx
from ..models import AuditLog
from ..schemas import AuditoriaOut
from ..services import dashboard

router = APIRouter(tags=["gestao"])


@router.get("/dashboard")
def painel(ctx: Ctx = Depends(get_ctx), unidade_id: int | None = None,
           de: date | None = None, ate: date | None = None):
    hoje = datetime.now(timezone.utc).astimezone(dashboard.tz_empresa(ctx.empresa)).date()
    ate = ate or hoje
    de = de or ate - timedelta(days=29)
    if de > ate:
        raise HTTPException(422, "A data inicial deve ser anterior à final.")
    if (ate - de).days > 366:
        raise HTTPException(422, "Período máximo de 366 dias.")
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        ids = [unidade_id]
    else:
        ids = ctx.ids_unidades()
    return dashboard.calcular(ctx.db, ctx.empresa, ids, de, ate)


@router.get("/auditoria", response_model=list[AuditoriaOut])
def auditoria(ctx: Ctx = Depends(get_ctx), entidade: str | None = None, entidade_id: int | None = None,
              acao: str | None = Query(None, max_length=60), usuario_id: int | None = None,
              limite: int = Query(100, ge=1, le=500), deslocamento: int = Query(0, ge=0)):
    q = select(AuditLog).where(AuditLog.empresa_id == ctx.empresa_id)
    if entidade:
        q = q.where(AuditLog.entidade == entidade)
    if entidade_id is not None:
        q = q.where(AuditLog.entidade_id == entidade_id)
    if acao:
        q = q.where(AuditLog.acao.like(f"{acao}%"))
    if usuario_id is not None:
        q = q.where(AuditLog.usuario_id == usuario_id)
    return ctx.db.scalars(q.order_by(AuditLog.id.desc()).limit(limite).offset(deslocamento)).all()
