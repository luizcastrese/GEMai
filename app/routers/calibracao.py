"""Calibração por módulo: prévia, registro de propostas e validação humana (ver services/calibracao_modulos)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from .. import audit
from ..config import get_settings
from ..deps import Ctx, get_ctx
from ..models import CalibracaoModulo, Produto
from ..schemas import CalibracaoModuloOut, CalibrarModulosIn, CalibrarModulosOut, DecisaoIn, SugestaoModuloCalibOut
from ..services import calibracao_modulos as svc
from ..services.modulos import catalogo

router = APIRouter(tags=["calibracao"])

AVISO = ("Fator multiplicativo POR MÓDULO (mediana de tempo normal observado ÷ previsto), calculado do histórico aprovado e "
         "limitado a 0,5–2,0. Não é por pessoa. Para cada produto com amostras suficientes também sugere um fator da FAMÍLIA que "
         "escala com o porte do pedido (o que se aprende dos pedidos maiores informa os menores). É só uma sugestão: nada entra "
         "no cálculo até uma pessoa validar.")


def _mesma_chave(unidade_id: int, modulo: str, produto_id: int | None):
    return (CalibracaoModulo.unidade_id == unidade_id, CalibracaoModulo.modulo == modulo,
            CalibracaoModulo.produto_id.is_(None) if produto_id is None else CalibracaoModulo.produto_id == produto_id)


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
    nomes = {p.id: p.nome for p in ctx.db.scalars(select(Produto).where(Produto.empresa_id == ctx.empresa_id))}
    linhas, criadas = [], 0
    for sg in sugestoes:
        vig = svc.vigente_exato(ctx.db, ctx.empresa_id, sg.unidade_id, sg.modulo, sg.produto_id)
        proposta_id = None
        if dados.aplicar and sg.status in ("sugerido", "preliminar"):
            chave = _mesma_chave(sg.unidade_id, sg.modulo, sg.produto_id)
            for ant in ctx.db.scalars(select(CalibracaoModulo).where(
                    CalibracaoModulo.empresa_id == ctx.empresa_id, CalibracaoModulo.status == "pendente", *chave)):
                ant.status = "rejeitado"  # a proposta nova substitui a pendente anterior
            ultima = ctx.db.scalar(select(func.max(CalibracaoModulo.versao)).where(
                CalibracaoModulo.empresa_id == ctx.empresa_id, *chave)) or 0
            just = (f"Mediana de {sg.amostras} operações aprovadas (tempo normal observado ÷ previsto)." if sg.produto_id is None else
                    f"Ajuste robusto de {sg.amostras} operações aprovadas de «{nomes.get(sg.produto_id, sg.produto_id)}»: fator "
                    f"{sg.fator:g} no porte {sg.porte_ref:g} min/un, expoente {sg.expoente:g}"
                    + (" (fator constante)." if not sg.expoente else
                       f" (dobrar o porte multiplica o fator por {2 ** sg.expoente:.2f}).")) + (f" {sg.nota}" if sg.nota else "")
            c = CalibracaoModulo(empresa_id=ctx.empresa_id, unidade_id=sg.unidade_id, modulo=sg.modulo, produto_id=sg.produto_id,
                                 expoente=sg.expoente, porte_ref=sg.porte_ref, porte_min=sg.porte_min, porte_max=sg.porte_max, fator=sg.fator,
                                 erro_sem_pct=sg.erro_sem_pct, erro_constante_pct=sg.erro_constante_pct, erro_com_pct=sg.erro_com_pct,
                                 mediana_bruta=sg.mediana_bruta, limitado=sg.limitado, amostras=sg.amostras, versao=ultima + 1,
                                 status="pendente", vigente=False, criado_por=ctx.usuario.id, justificativa=just)
            ctx.db.add(c)
            ctx.db.flush()
            ctx.auditar("calibracao_modulo.propor", "calibracao_modulo", c.id, None, audit.snap(c))
            proposta_id, criadas = c.id, criadas + 1
        linhas.append(SugestaoModuloCalibOut(
            unidade_id=sg.unidade_id, modulo=sg.modulo, titulo=_titulo(ctx, sg.modulo), produto_id=sg.produto_id,
            produto_nome=nomes.get(sg.produto_id) if sg.produto_id else None, expoente=sg.expoente, porte_ref=sg.porte_ref,
            porte_min=sg.porte_min, porte_max=sg.porte_max, erro_sem_pct=sg.erro_sem_pct, erro_constante_pct=sg.erro_constante_pct,
            erro_com_pct=sg.erro_com_pct, nota=sg.nota, amostras=sg.amostras, minimo=sg.minimo,
            mediana_bruta=sg.mediana_bruta, fator_sugerido=sg.fator, limitado=sg.limitado, status=sg.status,
            descartadas=sg.descartadas, credibilidade=sg.credibilidade, total_do_pedido=sg.total_do_pedido,
            vigente=svc.como_dict(vig, vig.porte_ref if vig else None), proposta_id=proposta_id))
    ctx.db.commit()
    return CalibrarModulosOut(aplicado=dados.aplicar, aviso=AVISO, propostas=criadas, modulos=linhas,
                              criterios={"min_amostras": s.min_amostras_calibracao, "limites": [svc.FATOR_MIN, svc.FATOR_MAX]})



def _titulo(ctx: Ctx, chave: str) -> str:
    mod = catalogo.obter(chave, ctx.db, ctx.empresa_id)
    return mod.titulo if mod else chave


@router.get("/calibracao/modulos", response_model=list[CalibracaoModuloOut])
def listar(unidade_id: int | None = None, ctx: Ctx = Depends(get_ctx)):
    q = ctx.query(CalibracaoModulo)
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        q = q.where(CalibracaoModulo.unidade_id == unidade_id)
    nomes = {p.id: p.nome for p in ctx.db.scalars(select(Produto).where(Produto.empresa_id == ctx.empresa_id))}
    out = []
    for c in ctx.db.scalars(q.order_by(CalibracaoModulo.modulo, CalibracaoModulo.unidade_id, CalibracaoModulo.versao.desc())):
        mod = catalogo.obter(c.modulo, ctx.db, ctx.empresa_id)
        out.append(CalibracaoModuloOut.model_validate(c).model_copy(update={
            "titulo": mod.titulo if mod else c.modulo, "produto_nome": nomes.get(c.produto_id) if c.produto_id else None}))
    return out


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
            CalibracaoModulo.empresa_id == ctx.empresa_id, CalibracaoModulo.vigente.is_(True),
            *_mesma_chave(c.unidade_id, c.modulo, c.produto_id))):
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
