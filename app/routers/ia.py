"""Recomendações da IA: listar, editar, aprovar/rejeitar e gerar análises.

Regra principal: IA sugere, sistema valida. Nada daqui altera processos, parâmetros ou
ordens sem uma decisão explícita de um gestor, registrada na auditoria.
"""
import json
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import select

from ..deps import Ctx, get_ctx, requer_gestor
from ..models import Etapa, Operacao, Ordem, Processo, RecomendacaoIA
from ..ratelimit import limite_ia
from ..schemas import AnaliseIn, DecisaoIn, RecomendacaoEditIn, RecomendacaoOut
from ..services import dashboard, estruturacao, ia, metricas, prontidao
from ..services.ia.esquemas import EstruturaProposta, sanear_estrutura

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


@router.patch("/recomendacoes/{rid}", response_model=RecomendacaoOut)
def editar(rid: int, dados: RecomendacaoEditIn, ctx: Ctx = Depends(requer_gestor)):
    """Permite corrigir a estrutura sugerida antes de aprová-la."""
    rec = ctx.obter(RecomendacaoIA, rid)
    if rec.status != "pendente":
        raise HTTPException(409, "Apenas sugestões pendentes podem ser editadas.")
    if rec.tipo != "estrutura_processo":
        raise HTTPException(422, "Somente a estrutura sugerida é editável.")
    try:
        nova = sanear_estrutura(EstruturaProposta.model_validate(dados.conteudo))
    except ValidationError as e:
        raise HTTPException(422, f"Estrutura inválida: {e.errors()[0]['loc']} {e.errors()[0]['msg']}")
    antes = rec.conteudo
    rec.conteudo = nova.model_dump()
    ctx.auditar("ia.editar_sugestao", "recomendacao", rec.id, {"conteudo": antes}, {"conteudo": rec.conteudo})
    ctx.db.commit()
    return rec


def _decidir(ctx: Ctx, rec: RecomendacaoIA, status: str, obs: str) -> None:
    if rec.status != "pendente":
        raise HTTPException(409, "Esta sugestão já foi decidida.")
    rec.status, rec.decidida_por, rec.decisao_obs = status, ctx.usuario.id, obs
    rec.decidida_em = datetime.now(timezone.utc)


@router.post("/recomendacoes/{rid}/aprovar", response_model=RecomendacaoOut)
def aprovar(rid: int, dados: DecisaoIn, ctx: Ctx = Depends(requer_gestor)):
    rec = ctx.obter(RecomendacaoIA, rid)
    if rec.status != "pendente":
        raise HTTPException(409, "Esta sugestão já foi decidida.")
    if rec.tipo == "estrutura_processo":
        est = sanear_estrutura(EstruturaProposta.model_validate(rec.conteudo))
        if not est.processos:
            raise HTTPException(422, "A proposta não tem processos para aplicar.")
        resumo = estruturacao.aplicar(ctx, rec, est)
        _decidir(ctx, rec, "aplicada", dados.observacao)
        rec.evidencias = {**(rec.evidencias or {}), "aplicado": resumo}
    else:
        _decidir(ctx, rec, "aprovada", dados.observacao)
    ctx.auditar("ia.aprovar", "recomendacao", rec.id, None, {"status": rec.status, "tipo": rec.tipo})
    ctx.db.commit()
    return rec


@router.post("/recomendacoes/{rid}/rejeitar", response_model=RecomendacaoOut)
def rejeitar(rid: int, dados: DecisaoIn, ctx: Ctx = Depends(requer_gestor)):
    rec = ctx.obter(RecomendacaoIA, rid)
    _decidir(ctx, rec, "rejeitada", dados.observacao)
    ctx.auditar("ia.rejeitar", "recomendacao", rec.id, None, {"status": rec.status})
    ctx.db.commit()
    return rec


# ------------------------------------------------------------------ análises
def _pares_semelhantes(ctx: Ctx, unidade_id: int) -> list[dict]:
    rows = ctx.db.execute(select(Operacao.nome, Etapa.nome, Processo.nome, Processo.id)
                          .join(Etapa, Etapa.id == Operacao.etapa_id).join(Processo, Processo.id == Etapa.processo_id)
                          .where(Operacao.empresa_id == ctx.empresa_id, Processo.unidade_id == unidade_id,
                                 Processo.status == "ativo")).all()
    pares = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            r = SequenceMatcher(None, a[0].lower(), b[0].lower()).ratio()
            if r >= 0.75 and (a[3] != b[3] or a[1] != b[1]):
                pares.append({"a": f"{a[0]} ({a[2]} › {a[1]})", "b": f"{b[0]} ({b[2]} › {b[1]})",
                              "motivo": f"Nomes {round(r * 100)}% semelhantes."})
    return pares[:30]


@router.post("/ia/analises", response_model=RecomendacaoOut, status_code=201)
def analisar(dados: AnaliseIn, ctx: Ctx = Depends(requer_gestor)):
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
    elif dados.tipo in ("analise_gargalo", "relatorio_gestor"):
        ate = dados.ate or date.today()
        de = dados.de or ate - timedelta(days=29)
        fatos = dashboard.calcular(ctx.db, ctx.empresa, [uni.id], de, ate)
        titulo = ("Possíveis gargalos" if dados.tipo == "analise_gargalo" else "Relatório do gestor") + \
                 f" – {uni.nome} ({de:%d/%m} a {ate:%d/%m})"
    elif dados.tipo == "revisao_processo":
        if not dados.processo_id:
            raise HTTPException(422, "Informe processo_id.")
        proc = ctx.obter(Processo, dados.processo_id)
        if proc.unidade_id != uni.id:
            raise HTTPException(404, "Registro não encontrado.")
        fatos = {"processo": proc.nome, "prontidao": prontidao.avaliar(ctx.db, ctx.empresa_id, proc)}
        alvo_tipo, alvo_id, titulo = "processo", proc.id, f"Revisão de prontidão – {proc.nome} v{proc.versao}"
    elif dados.tipo == "indicadores_sugeridos":
        fatos = {"segmento": ctx.empresa.segmento, "descricao": uni.descricao_operacao,
                 "problemas": uni.principais_problemas, "objetivo": uni.objetivo}
        titulo = f"Indicadores sugeridos – {uni.nome}"
    else:  # processos_semelhantes
        fatos = {"pares": _pares_semelhantes(ctx, uni.id)}
        titulo = f"Operações semelhantes – {uni.nome}"
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
