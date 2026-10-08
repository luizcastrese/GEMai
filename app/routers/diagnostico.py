"""Telas 1–3: descrição da empresa, diagnóstico adaptativo e proposta de estrutura (IA)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from ..deps import Ctx, get_ctx, requer_gestor
from ..models import DiagnosticoPergunta, RecomendacaoIA
from ..ratelimit import limite_ia
from ..schemas import PerguntaOut, RecomendacaoOut, RespostaIn
from ..services import ia
from ..services.ia import heuristica

router = APIRouter(tags=["diagnostico"])


class PerguntasGeradas(BaseModel):
    perguntas: list[PerguntaOut]
    provedor: str
    aviso: str = ""


def _contexto(ctx: Ctx, uni) -> dict:
    qa = ctx.db.scalars(select(DiagnosticoPergunta).where(
        DiagnosticoPergunta.unidade_id == uni.id).order_by(DiagnosticoPergunta.ordem))
    return {
        "segmento": ctx.empresa.segmento, "unidade": uni.nome, "descricao": uni.descricao_operacao,
        "objetivo": uni.objetivo, "problemas": uni.principais_problemas,
        "informacoes_disponiveis": uni.informacoes_disponiveis,
        "qa": [{"grupo": q.grupo, "texto": q.texto, "resposta": q.resposta} for q in qa],
    }


@router.get("/unidades/{uid}/diagnostico", response_model=list[PerguntaOut])
def listar(uid: int, ctx: Ctx = Depends(get_ctx)):
    ctx.exige_unidade(uid)
    return ctx.db.scalars(select(DiagnosticoPergunta).where(
        DiagnosticoPergunta.unidade_id == uid, DiagnosticoPergunta.empresa_id == ctx.empresa_id
    ).order_by(DiagnosticoPergunta.ordem)).all()


@router.post("/unidades/{uid}/diagnostico/perguntas/gerar", response_model=PerguntasGeradas)
def gerar(uid: int, request: Request, ctx: Ctx = Depends(requer_gestor)):
    """Gera perguntas adaptativas a partir da descrição e das respostas já dadas."""
    uni = ctx.exige_unidade(uid)
    if not (uni.descricao_operacao or "").strip():
        raise HTTPException(422, "Descreva a operação da unidade antes de gerar o diagnóstico (Tela 1).")
    limite_ia.checar(f"{ctx.empresa_id}")
    contexto = _contexto(ctx, uni)
    contexto["max"] = 12
    perguntas, prov, aviso = ia.gerar_perguntas(ctx.empresa, contexto)
    existentes = {heuristica._norm(q["texto"]) for q in contexto["qa"]}
    ordem = ctx.db.scalar(select(func.coalesce(func.max(DiagnosticoPergunta.ordem), 0)).where(
        DiagnosticoPergunta.unidade_id == uid)) or 0
    novas = []
    for p in perguntas:
        if heuristica._norm(p.texto) in existentes:
            continue
        ordem += 1
        q = DiagnosticoPergunta(empresa_id=ctx.empresa_id, unidade_id=uid, grupo=p.grupo, texto=p.texto,
                                ordem=ordem, origem=prov)
        ctx.db.add(q)
        novas.append(q)
    ctx.db.flush()
    ctx.auditar("diagnostico.gerar_perguntas", "unidade", uid, None, {"novas": len(novas), "provedor": prov})
    ctx.db.commit()
    return PerguntasGeradas(perguntas=[PerguntaOut.model_validate(q) for q in novas], provedor=prov, aviso=aviso)


@router.patch("/diagnostico/perguntas/{qid}", response_model=PerguntaOut)
def responder(qid: int, dados: RespostaIn, ctx: Ctx = Depends(requer_gestor)):
    q = ctx.obter(DiagnosticoPergunta, qid)
    antes = {"resposta": q.resposta}
    q.resposta = dados.resposta.strip() or None
    q.respondida_em = datetime.now(timezone.utc) if q.resposta else None
    q.respondida_por = ctx.usuario.id if q.resposta else None
    ctx.auditar("diagnostico.responder", "pergunta", q.id, antes, {"resposta": q.resposta})
    ctx.db.commit()
    return q


@router.post("/unidades/{uid}/diagnostico/estruturar", response_model=RecomendacaoOut, status_code=201)
def estruturar(uid: int, ctx: Ctx = Depends(requer_gestor)):
    """Gera a proposta de estrutura (Tela 3). Fica PENDENTE até revisão e aprovação humana."""
    uni = ctx.exige_unidade(uid)
    if not (uni.descricao_operacao or "").strip():
        raise HTTPException(422, "Descreva a operação da unidade antes de estruturar (Tela 1).")
    limite_ia.checar(f"{ctx.empresa_id}")
    proposta, prov, aviso = ia.estruturar(ctx.empresa, _contexto(ctx, uni))
    rec = RecomendacaoIA(
        empresa_id=ctx.empresa_id, unidade_id=uid, tipo="estrutura_processo", provedor=prov,
        titulo=f"Estrutura sugerida para {uni.nome}", conteudo=proposta.model_dump(),
        justificativa=aviso or "Gerada a partir da descrição da operação e das respostas do diagnóstico.",
        criada_por=ctx.usuario.id)
    ctx.db.add(rec)
    ctx.db.flush()
    ctx.auditar("ia.estruturar", "recomendacao", rec.id, None, {"provedor": prov})
    ctx.db.commit()
    return rec
