"""Dashboard do gestor (seção 13), comparação entre condições e auditoria."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..deps import Ctx, requer_admin, requer_gestor
from ..models import Apontamento, AuditLog, Ordem, OrdemOperacao, Pessoa, Recurso
from ..schemas import AuditoriaOut
from ..services import dashboard, timecalc

router = APIRouter(tags=["gestao"])


@router.get("/dashboard")
def painel(ctx: Ctx = Depends(requer_gestor), unidade_id: int | None = None,
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


@router.get("/analise/comparacao")
def comparar_condicoes(operacao_id: int, ctx: Ctx = Depends(requer_gestor)):
    """Compara o tempo por unidade da mesma operação entre recursos e entre pessoas
    (apenas apontamentos aprovados). Mostra diferenças; não afirma causas."""
    rows = ctx.db.execute(
        select(Apontamento, OrdemOperacao.qtd_planejada)
        .join(OrdemOperacao, OrdemOperacao.id == Apontamento.ordem_operacao_id)
        .join(Ordem, Ordem.id == Apontamento.ordem_id)
        .where(Apontamento.empresa_id == ctx.empresa_id, OrdemOperacao.operacao_id == operacao_id,
               Apontamento.status == "aprovado", Apontamento.anulado.is_(False), Apontamento.tipo == "execucao",
               Apontamento.fim.is_not(None),
               *( [Ordem.unidade_id.in_(ctx.unidades or {-1})] if ctx.unidades is not None else [] ))).all()
    por_rec: dict[int | None, list[float]] = {}
    por_pes: dict[int | None, list[float]] = {}
    for a, _ in rows:
        q = a.quantidade_boa + a.quantidade_refugo
        if q <= 0:
            continue
        taxa = (timecalc.duracao_min(a.inicio, a.fim) or 0) / q
        por_rec.setdefault(a.recurso_id, []).append(taxa)
        por_pes.setdefault(a.pessoa_id, []).append(taxa)
    nomes_r = {r.id: r.nome for r in ctx.db.scalars(select(Recurso).where(Recurso.empresa_id == ctx.empresa_id))}
    nomes_p = {p.id: p.nome for p in ctx.db.scalars(select(Pessoa).where(Pessoa.empresa_id == ctx.empresa_id))}

    def resumo(d, nomes):
        return sorted(({"id": k, "nome": nomes.get(k, "Não informado"), "amostras": len(v),
                        "min_por_unidade": timecalc.arred(timecalc.mediana(v), 3)} for k, v in d.items()),
                      key=lambda x: x["min_por_unidade"])

    return {"operacao_id": operacao_id, "por_recurso": resumo(por_rec, nomes_r), "por_pessoa": resumo(por_pes, nomes_p),
            "aviso": "Diferenças observadas no histórico aprovado; não implicam causa. Investigue antes de concluir."}


@router.get("/auditoria", response_model=list[AuditoriaOut])
def auditoria(ctx: Ctx = Depends(requer_admin), entidade: str | None = None, entidade_id: int | None = None,
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
