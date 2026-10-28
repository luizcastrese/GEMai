"""Calibração por módulo: prévia, registro de propostas e validação humana (ver services/calibracao_modulos)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from .. import audit
from ..config import get_settings
from ..deps import Ctx, get_ctx
from ..models import CalibracaoModulo
from ..schemas import CalibracaoModuloOut, CalibrarModulosIn, CalibrarModulosOut, DecisaoIn, SugestaoModuloCalibOut
from ..services import calibracao_modulos as svc
from ..services.modulos import catalogo

router = APIRouter(tags=["calibracao"])

AVISO = ("Fator multiplicativo POR MÓDULO (mediana de tempo normal observado ÷ previsto), calculado do histórico aprovado e "
         "limitado a 0,5–2,0. Não é por pessoa. É só uma sugestão: nada entra no cálculo até uma pessoa validar.")


def _escopo(ctx: Ctx, unidade_id: int | None) -> list[int]:
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        return [unidade_id]
    return ctx.ids_unidades()


@router.post("/calibracao/modulos", response_model=CalibrarModulosOut)
def calibrar(dados: CalibrarModulosIn, ctx: Ctx = Depends(get_ctx)):
    """Prévia (aplicar=false, não grava) ou registro de PROPOSTAS pendentes (aplicar=true, com auditoria)."""
    s = get_settings()
    sugestoes = svc.previa(ctx.db, ctx.empresa_id, _escopo(ctx, dados.unidade_id))
    linhas, criadas = [], 0
    for sg in sugestoes:
        vig = svc.fator_vigente(ctx.db, ctx.empresa_id, sg.unidade_id, sg.modulo)
        proposta_id = None
        if dados.aplicar and sg.status == "sugerido":
            for ant in ctx.db.scalars(select(CalibracaoModulo).where(
                    CalibracaoModulo.empresa_id == ctx.empresa_id, CalibracaoModulo.unidade_id == sg.unidade_id,
                    CalibracaoModulo.modulo == sg.modulo, CalibracaoModulo.status == "pendente")):
                ant.status = "rejeitado"  # a proposta nova substitui a pendente anterior
            ultima = ctx.db.scalar(select(func.max(CalibracaoModulo.versao)).where(
                CalibracaoModulo.empresa_id == ctx.empresa_id, CalibracaoModulo.unidade_id == sg.unidade_id,
                CalibracaoModulo.modulo == sg.modulo)) or 0
            c = CalibracaoModulo(empresa_id=ctx.empresa_id, unidade_id=sg.unidade_id, modulo=sg.modulo, fator=sg.fator,
                                 mediana_bruta=sg.mediana_bruta, limitado=sg.limitado, amostras=sg.amostras, versao=ultima + 1,
                                 status="pendente", vigente=False, criado_por=ctx.usuario.id,
                                 justificativa=f"Mediana de {sg.amostras} operações aprovadas (tempo normal observado ÷ previsto).")
            ctx.db.add(c)
            ctx.db.flush()
            ctx.auditar("calibracao_modulo.propor", "calibracao_modulo", c.id, None, audit.snap(c))
            proposta_id, criadas = c.id, criadas + 1
        linhas.append(SugestaoModuloCalibOut(
            unidade_id=sg.unidade_id, modulo=sg.modulo, titulo=catalogo.obter(sg.modulo).titulo, amostras=sg.amostras, minimo=sg.minimo,
            mediana_bruta=sg.mediana_bruta, fator_sugerido=sg.fator, limitado=sg.limitado, status=sg.status,
            vigente=svc.como_dict(vig), proposta_id=proposta_id))
    ctx.db.commit()
    return CalibrarModulosOut(aplicado=dados.aplicar, aviso=AVISO, propostas=criadas, modulos=linhas,
                              criterios={"min_amostras": s.min_amostras_calibracao, "limites": [svc.FATOR_MIN, svc.FATOR_MAX]})


@router.get("/calibracao/modulos", response_model=list[CalibracaoModuloOut])
def listar(unidade_id: int | None = None, ctx: Ctx = Depends(get_ctx)):
    q = ctx.query(CalibracaoModulo)
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        q = q.where(CalibracaoModulo.unidade_id == unidade_id)
    return ctx.db.scalars(q.order_by(CalibracaoModulo.modulo, CalibracaoModulo.unidade_id, CalibracaoModulo.versao.desc())).all()


def _pendente(ctx: Ctx, cid: int) -> CalibracaoModulo:
    c = ctx.obter(CalibracaoModulo, cid)
    if c.status != "pendente":
        raise HTTPException(409, "Calibração já decidida.")
    return c


@router.post("/calibracao/modulos/{cid}/validar", response_model=CalibracaoModuloOut)
def validar(cid: int, dados: DecisaoIn, ctx: Ctx = Depends(get_ctx)):
    c = _pendente(ctx, cid)
    antes = audit.snap(c)
    for ant in ctx.db.scalars(select(CalibracaoModulo).where(
            CalibracaoModulo.empresa_id == ctx.empresa_id, CalibracaoModulo.unidade_id == c.unidade_id,
            CalibracaoModulo.modulo == c.modulo, CalibracaoModulo.vigente.is_(True))):
        ant.vigente = False
    c.status, c.vigente = "validado", True
    c.validado_por, c.validado_em = ctx.usuario.id, datetime.now(timezone.utc)
    if dados.observacao:
        c.justificativa = (c.justificativa + "\n" if c.justificativa else "") + f"Validação: {dados.observacao}"
    ctx.auditar("calibracao_modulo.validar", "calibracao_modulo", c.id, antes, audit.snap(c))
    ctx.db.commit()
    return c


@router.post("/calibracao/modulos/{cid}/rejeitar", response_model=CalibracaoModuloOut)
def rejeitar(cid: int, dados: DecisaoIn, ctx: Ctx = Depends(get_ctx)):
    c = _pendente(ctx, cid)
    antes = audit.snap(c)
    c.status, c.vigente = "rejeitado", False
    c.validado_por, c.validado_em = ctx.usuario.id, datetime.now(timezone.utc)
    ctx.auditar("calibracao_modulo.rejeitar", "calibracao_modulo", c.id, antes, audit.snap(c))
    ctx.db.commit()
    return c
