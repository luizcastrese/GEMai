"""Recomendações da IA: listar, editar, aprovar/rejeitar e gerar análises.

Regra principal: IA sugere, sistema valida. Nada daqui altera planos, ordens ou apontamentos:
são textos redigidos a partir de fatos calculados, que uma pessoa valida ou rejeita (auditado).
"""
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import Ctx, get_ctx
from ..models import Ordem, RecomendacaoIA
from ..ratelimit import limite_ia
from ..schemas import AnaliseIn, DecisaoIn, RecomendacaoOut
from ..services import dashboard, ia, metricas

router = APIRouter(tags=["ia"])


def _json(x):
    return json.loads(json.dumps(x, default=str))


@router.get("/recomendacoes", response_model=list[RecomendacaoOut])
def listar(ctx: Ctx = Depends(get_ctx), unidade_id: int | None = None, tipo: str | None = None,
           status: str | None = None, limite: int = Query(50, ge=1, le=200), deslocamento: int = Query(0, ge=0)):
    q = ctx.query(RecomendacaoIA)
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        q = q.where(RecomendacaoIA.unidade_id == unidade_id)
    if tipo:
        q = q.where(RecomendacaoIA.tipo == tipo)
    if status:
        q = q.where(RecomendacaoIA.status == status)
    return ctx.db.scalars(q.order_by(RecomendacaoIA.id.desc()).limit(limite).offset(deslocamento)).all()


@router.get("/recomendacoes/{rid}", response_model=RecomendacaoOut)
def obter(rid: int, ctx: Ctx = Depends(get_ctx)):
    return ctx.obter(RecomendacaoIA, rid)


def _decidir(ctx: Ctx, rec: RecomendacaoIA, status: str, obs: str) -> None:
    if rec.status != "pendente":
        raise HTTPException(409, "Esta sugestão já foi decidida.")
    rec.status, rec.decidida_por, rec.decisao_obs = status, ctx.usuario.id, obs
    rec.decidida_em = datetime.now(timezone.utc)


@router.post("/recomendacoes/{rid}/aprovar", response_model=RecomendacaoOut)
def aprovar(rid: int, dados: DecisaoIn, ctx: Ctx = Depends(get_ctx)):
    rec = ctx.obter(RecomendacaoIA, rid)
    if rec.status != "pendente":
        raise HTTPException(409, "Esta sugestão já foi decidida.")
    _decidir(ctx, rec, "aprovada", dados.observacao)
    ctx.auditar("ia.aprovar", "recomendacao", rec.id, None, {"status": rec.status, "tipo": rec.tipo})
    ctx.db.commit()
    return rec


@router.post("/recomendacoes/{rid}/rejeitar", response_model=RecomendacaoOut)
def rejeitar(rid: int, dados: DecisaoIn, ctx: Ctx = Depends(get_ctx)):
    rec = ctx.obter(RecomendacaoIA, rid)
    _decidir(ctx, rec, "rejeitada", dados.observacao)
    ctx.auditar("ia.rejeitar", "recomendacao", rec.id, None, {"status": rec.status})
    ctx.db.commit()
    return rec


# ------------------------------------------------------------------ análises
@router.post("/ia/analises", response_model=RecomendacaoOut, status_code=201)
def analisar(dados: AnaliseIn, ctx: Ctx = Depends(get_ctx)):
    uni = ctx.exige_unidade(dados.unidade_id)
    limite_ia.checar(f"{ctx.empresa_id}")
    alvo_tipo = alvo_id = None
    if dados.tipo == "analise_desvio":
        if not dados.ordem_id:
            raise HTTPException(422, "Informe ordem_id.")
        ordem = ctx.obter(Ordem, dados.ordem_id)
        if ordem.unidade_id != uni.id:
            raise HTTPException(404, "Registro não encontrado.")
        fatos = metricas.analisar_ordem(ctx.db, ordem)
        alvo_tipo, alvo_id, titulo = "ordem", ordem.id, f"Análise de desvios – {ordem.numero}"
    else:  # analise_gargalo | relatorio_gestor
        ate = dados.ate or date.today()
        de = dados.de or ate - timedelta(days=29)
        fatos = dashboard.calcular(ctx.db, ctx.empresa, [uni.id], de, ate)
        titulo = ("Possíveis gargalos" if dados.tipo == "analise_gargalo" else "Relatório do gestor") + \
                 f" – {uni.nome} ({de:%d/%m} a {ate:%d/%m})"
    fatos = _json(fatos)
    analise, prov, aviso = ia.analisar(ctx.empresa, dados.tipo, fatos)
    rec = RecomendacaoIA(
        empresa_id=ctx.empresa_id, unidade_id=uni.id, tipo=dados.tipo, titulo=titulo, provedor=prov,
        conteudo=analise.model_dump(), evidencias=fatos, alvo_tipo=alvo_tipo, alvo_id=alvo_id,
        justificativa=aviso or "Texto redigido a partir de fatos calculados pelo sistema (ver evidências).",
        criada_por=ctx.usuario.id)
    ctx.db.add(rec)
    ctx.db.flush()
    ctx.auditar("ia.analise", "recomendacao", rec.id, None, {"tipo": dados.tipo, "provedor": prov})
    ctx.db.commit()
    return rec
