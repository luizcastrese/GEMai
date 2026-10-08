"""Tela 5: ordens de produção/processo, com roteiro, estimativa e controle de status."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..constants import ORDEM_ABERTA, ORDEM_FINAL
from ..deps import Ctx, get_ctx, requer_gestor
from ..models import Apontamento, Empresa, Ocorrencia, Operacao, Ordem, OrdemOperacao, Processo, Produto, Recurso
from ..schemas import CancelarIn, OrdemIn, OrdemOperacaoOut, OrdemOut, OrdemUpdate
from ..services import estimativa, metricas
from ..services.dashboard import tz_empresa

router = APIRouter(tags=["ordens"])


def _hoje(empresa: Empresa):
    return datetime.now(timezone.utc).astimezone(tz_empresa(empresa)).date()


def ordem_out(ctx: Ctx, o: Ordem, detalhado: bool = False) -> OrdemOut:
    out = OrdemOut.model_validate(o, from_attributes=True)
    out.operacoes = None
    out.atrasada = bool(o.prazo and o.status in (*ORDEM_ABERTA, "planejada") and o.prazo < _hoje(ctx.empresa))
    ativas = [x for x in o.operacoes if x.status != "pulada"]
    out.estimativa_parcial = any(x.tempo_exec_est_min is None for x in ativas)
    if detalhado:
        mets = {m["ordem_operacao_id"]: m for m in metricas.metricas_operacoes(ctx.db, [o])[o.id]}
        ops = []
        for x in o.operacoes:
            oo = OrdemOperacaoOut.model_validate(x)
            m = mets.get(x.id, {})
            oo.qtd_boa, oo.qtd_refugo = m.get("qtd_boa", 0), m.get("qtd_refugo", 0)
            oo.tempo_apontado_min = round(m.get("realizado_min", 0) + m.get("espera_min", 0), 2)
            ops.append(oo)
        _preencher_definicoes(ctx.db, ops)
        out.operacoes = ops
    return out


def _preencher_definicoes(db: Session, itens: list[OrdemOperacaoOut]) -> None:
    ids = {i.operacao_id for i in itens if i.operacao_id}
    if not ids:
        return
    defs = {o.id: o for o in db.scalars(select(Operacao).where(Operacao.id.in_(ids)))}
    for i in itens:
        op = defs.get(i.operacao_id)
        if op:
            i.campos_extras, i.dados_medidos = op.campos_extras, op.dados_medidos


def _numero(db: Session, empresa_id: int) -> str:
    from sqlalchemy import update
    db.execute(update(Empresa).where(Empresa.id == empresa_id).values(seq_ordem=Empresa.seq_ordem + 1))
    n = db.scalar(select(Empresa.seq_ordem).where(Empresa.id == empresa_id))
    return f"OP-{n:06d}"


def _abertos(ctx: Ctx, ordem_id: int) -> tuple[int, int]:
    ap = ctx.db.scalar(select(func.count(Apontamento.id)).where(
        Apontamento.ordem_id == ordem_id, Apontamento.fim.is_(None), Apontamento.anulado.is_(False))) or 0
    pa = ctx.db.scalar(select(func.count(Ocorrencia.id)).where(
        Ocorrencia.ordem_id == ordem_id, Ocorrencia.tipo == "parada", Ocorrencia.fim.is_(None),
        Ocorrencia.anulada.is_(False))) or 0
    return ap, pa


def _oo(ctx: Ctx, ordem: Ordem, ooid: int) -> OrdemOperacao:
    oo = ctx.db.get(OrdemOperacao, ooid)
    if not oo or oo.ordem_id != ordem.id or oo.empresa_id != ctx.empresa_id:
        raise HTTPException(404, "Registro não encontrado.")
    return oo


# ------------------------------------------------------------------ CRUD
@router.get("/ordens", response_model=list[OrdemOut])
def listar(ctx: Ctx = Depends(get_ctx), unidade_id: int | None = None, status: str | None = None,
           atrasadas: bool = False, q: str | None = Query(None, max_length=100),
           limite: int = Query(50, ge=1, le=200), deslocamento: int = Query(0, ge=0)):
    stmt = ctx.query(Ordem)
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        stmt = stmt.where(Ordem.unidade_id == unidade_id)
    if status:
        stmt = stmt.where(Ordem.status.in_(status.split(",")))
    if atrasadas:
        stmt = stmt.where(Ordem.status.in_(tuple(ORDEM_ABERTA) + ("planejada",)), Ordem.prazo < _hoje(ctx.empresa))
    if q:
        stmt = stmt.where(Ordem.numero.ilike(f"%{q}%") | Ordem.cliente.ilike(f"%{q}%") | Ordem.descricao.ilike(f"%{q}%"))
    os_ = ctx.db.scalars(stmt.order_by(Ordem.id.desc()).limit(limite).offset(deslocamento)).all()
    return [ordem_out(ctx, o) for o in os_]


@router.post("/ordens", response_model=OrdemOut, status_code=201)
def criar(dados: OrdemIn, ctx: Ctx = Depends(requer_gestor)):
    uni = ctx.exige_unidade(dados.unidade_id)
    proc = ctx.obter(Processo, dados.processo_id)
    if proc.unidade_id != uni.id:
        raise HTTPException(422, "O processo não pertence a esta unidade.")
    if proc.status != "ativo":
        raise HTTPException(409, "Somente processos ativos (publicados) podem gerar ordens.")
    if dados.produto_id is not None:
        pr = ctx.db.get(Produto, dados.produto_id)
        if not pr or pr.empresa_id != ctx.empresa_id:
            raise HTTPException(422, "Produto inválido.")
    ops_proc = [op for e in proc.etapas for op in e.operacoes]
    ids_validos = {op.id for op in ops_proc}
    recursos_sel = {}
    for r in dados.recursos:
        if r.operacao_id not in ids_validos:
            raise HTTPException(422, "Operação não pertence ao processo.")
        rec = ctx.db.get(Recurso, r.recurso_id)
        if not rec or rec.empresa_id != ctx.empresa_id or rec.unidade_id != uni.id or not rec.ativo:
            raise HTTPException(422, "Recurso inválido para esta unidade.")
        recursos_sel[r.operacao_id] = rec.id
    opcionais = {op.id for e in proc.etapas if e.opcional for op in e.operacoes}
    for pid in dados.pular_operacoes:
        if pid not in opcionais:
            raise HTTPException(422, "Só é possível pular operações de etapas opcionais.")

    o = Ordem(empresa_id=ctx.empresa_id, unidade_id=uni.id, numero=_numero(ctx.db, ctx.empresa_id),
              cliente=dados.cliente or "", produto_id=dados.produto_id, descricao=dados.descricao,
              quantidade=dados.quantidade, prazo=dados.prazo, processo_id=proc.id, observacoes=dados.observacoes,
              status="planejada", criada_por=ctx.usuario.id)
    ctx.db.add(o)
    ctx.db.flush()
    total, algum = 0.0, False
    seq = 0
    for e in proc.etapas:
        for op in e.operacoes:
            seq += 1
            pulada = op.id in dados.pular_operacoes
            est = estimativa.estimar_operacao(ctx.db, ctx.empresa_id, op, dados.quantidade)
            if not pulada and est.exec is not None:
                total += (est.prep or 0.0) + est.exec
                algum = True
            ctx.db.add(OrdemOperacao(
                empresa_id=ctx.empresa_id, ordem_id=o.id, operacao_id=op.id, sequencia=seq, etapa_nome=e.nome,
                nome=op.nome, recurso_id=recursos_sel.get(op.id, op.recurso_padrao_id),
                qtd_planejada=dados.quantidade, formula_tipo=op.formula_tipo,
                tempo_prep_est_min=est.prep if est.exec is not None else None, tempo_exec_est_min=est.exec,
                fonte_estimativa=est.fonte, amostras=est.amostras, opcional=e.opcional,
                status="pulada" if pulada else "pendente"))
    o.tempo_estimado_min = round(total, 2) if algum else None
    ctx.db.flush()
    ctx.db.refresh(o)
    ctx.auditar("ordem.criar", "ordem", o.id, None, audit.snap(o))
    ctx.db.commit()
    return ordem_out(ctx, o, True)


@router.get("/ordens/{oid}", response_model=OrdemOut)
def obter(oid: int, ctx: Ctx = Depends(get_ctx)):
    return ordem_out(ctx, ctx.obter(Ordem, oid), True)


@router.patch("/ordens/{oid}", response_model=OrdemOut)
def atualizar(oid: int, dados: OrdemUpdate, ctx: Ctx = Depends(requer_gestor)):
    o = ctx.obter(Ordem, oid)
    if o.status in ORDEM_FINAL:
        raise HTTPException(409, "Ordem encerrada não pode ser alterada.")
    antes = audit.snap(o)
    for k, v in dados.model_dump(exclude_unset=True).items():
        if v is not None or k == "prazo":
            setattr(o, k, v)
    ctx.auditar("ordem.atualizar", "ordem", o.id, antes, audit.snap(o))
    ctx.db.commit()
    return ordem_out(ctx, o, True)


# ------------------------------------------------------------------ status
@router.post("/ordens/{oid}/liberar", response_model=OrdemOut)
def liberar(oid: int, ctx: Ctx = Depends(requer_gestor)):
    o = ctx.obter(Ordem, oid)
    if o.status != "planejada":
        raise HTTPException(409, "Somente ordens planejadas podem ser liberadas.")
    o.status, o.liberada_em = "liberada", datetime.now(timezone.utc)
    ctx.auditar("ordem.liberar", "ordem", o.id, {"status": "planejada"}, {"status": "liberada"})
    ctx.db.commit()
    return ordem_out(ctx, o, True)


@router.post("/ordens/{oid}/cancelar", response_model=OrdemOut)
def cancelar(oid: int, dados: CancelarIn, ctx: Ctx = Depends(requer_gestor)):
    o = ctx.obter(Ordem, oid)
    if o.status in ORDEM_FINAL:
        raise HTTPException(409, "A ordem já está encerrada.")
    ap, _ = _abertos(ctx, o.id)
    if ap:
        raise HTTPException(409, "Finalize os apontamentos em aberto antes de cancelar.")
    agora = datetime.now(timezone.utc)
    for oc in ctx.db.scalars(select(Ocorrencia).where(Ocorrencia.ordem_id == o.id, Ocorrencia.fim.is_(None),
                                                      Ocorrencia.anulada.is_(False))):
        oc.fim = max(agora, oc.inicio)
    antes = o.status
    o.status, o.cancelamento_motivo = "cancelada", dados.motivo
    ctx.auditar("ordem.cancelar", "ordem", o.id, {"status": antes}, {"status": "cancelada", "motivo": dados.motivo})
    ctx.db.commit()
    return ordem_out(ctx, o, True)


@router.post("/ordens/{oid}/concluir", response_model=OrdemOut)
def concluir(oid: int, ctx: Ctx = Depends(requer_gestor)):
    o = ctx.obter(Ordem, oid)
    if o.status not in ("liberada", "em_producao"):
        raise HTTPException(409, "Somente ordens liberadas ou em produção podem ser concluídas "
                                 "(encerre antes as paradas em aberto).")
    ap, pa = _abertos(ctx, o.id)
    if ap or pa:
        raise HTTPException(409, "Há apontamentos ou paradas em aberto nesta ordem.")
    pendentes = [x.nome for x in o.operacoes if x.status in ("pendente", "em_andamento")]
    if pendentes:
        raise HTTPException(409, "Operações não concluídas: " + ", ".join(pendentes))
    o.status, o.concluida_em = "concluida", datetime.now(timezone.utc)
    ctx.auditar("ordem.concluir", "ordem", o.id, None, {"status": "concluida"})
    ctx.db.commit()
    return ordem_out(ctx, o, True)


@router.get("/ordens/{oid}/analise")
def analise(oid: int, ctx: Ctx = Depends(requer_gestor)):
    """Planejado x realizado da ordem (cálculo determinístico, sem IA)."""
    return metricas.analisar_ordem(ctx.db, ctx.obter(Ordem, oid))


# ------------------------------------------------------------------ operações da ordem
@router.post("/ordens/{oid}/operacoes/{ooid}/concluir", response_model=OrdemOut)
def concluir_operacao(oid: int, ooid: int, ctx: Ctx = Depends(get_ctx)):
    o = ctx.obter(Ordem, oid)
    oo = _oo(ctx, o, ooid)
    if o.status not in ("liberada", "em_producao"):
        raise HTTPException(409, "A ordem não está em execução.")
    if oo.status not in ("pendente", "em_andamento"):
        raise HTTPException(409, "A operação já foi encerrada.")
    aberto = ctx.db.scalar(select(func.count(Apontamento.id)).where(
        Apontamento.ordem_operacao_id == oo.id, Apontamento.fim.is_(None), Apontamento.anulado.is_(False)))
    if aberto:
        raise HTTPException(409, "Finalize os apontamentos em aberto desta operação.")
    antes = oo.status
    oo.status, oo.concluida_em, oo.concluida_por = "concluida", datetime.now(timezone.utc), ctx.usuario.id
    ctx.auditar("ordem_operacao.concluir", "ordem_operacao", oo.id, {"status": antes}, {"status": "concluida"})
    ctx.db.commit()
    return ordem_out(ctx, o, True)


@router.post("/ordens/{oid}/operacoes/{ooid}/reabrir", response_model=OrdemOut)
def reabrir_operacao(oid: int, ooid: int, ctx: Ctx = Depends(requer_gestor)):
    o = ctx.obter(Ordem, oid)
    oo = _oo(ctx, o, ooid)
    if o.status not in ("liberada", "em_producao"):
        raise HTTPException(409, "A ordem não está em execução.")
    if oo.status not in ("concluida", "pulada"):
        raise HTTPException(409, "A operação não está encerrada.")
    antes = oo.status
    oo.status, oo.concluida_em, oo.concluida_por = "em_andamento" if oo.iniciada_em else "pendente", None, None
    ctx.auditar("ordem_operacao.reabrir", "ordem_operacao", oo.id, {"status": antes}, {"status": oo.status})
    ctx.db.commit()
    return ordem_out(ctx, o, True)


@router.post("/ordens/{oid}/operacoes/{ooid}/pular", response_model=OrdemOut)
def pular_operacao(oid: int, ooid: int, ctx: Ctx = Depends(requer_gestor)):
    o = ctx.obter(Ordem, oid)
    oo = _oo(ctx, o, ooid)
    if not oo.opcional or oo.status != "pendente" or o.status in ORDEM_FINAL:
        raise HTTPException(409, "Só é possível pular operações opcionais ainda não iniciadas.")
    oo.status = "pulada"
    ctx.auditar("ordem_operacao.pular", "ordem_operacao", oo.id, {"status": "pendente"}, {"status": "pulada"})
    ctx.db.commit()
    return ordem_out(ctx, o, True)


# ------------------------------------------------------------------ interface do operador
@router.get("/operador/fila", response_model=list[OrdemOperacaoOut])
def fila_operador(ctx: Ctx = Depends(get_ctx), unidade_id: int | None = None):
    """Operações disponíveis para apontar (visão simplificada do chão de fábrica)."""
    stmt = (select(OrdemOperacao, Ordem.numero).join(Ordem, Ordem.id == OrdemOperacao.ordem_id)
            .where(Ordem.empresa_id == ctx.empresa_id, Ordem.status.in_(("liberada", "em_producao")),
                   OrdemOperacao.status.in_(("pendente", "em_andamento"))))
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        stmt = stmt.where(Ordem.unidade_id == unidade_id)
    elif ctx.unidades is not None:
        stmt = stmt.where(Ordem.unidade_id.in_(ctx.unidades or {-1}))
    rows = ctx.db.execute(stmt.order_by(Ordem.prazo.is_(None), Ordem.prazo, Ordem.id, OrdemOperacao.sequencia)
                          .limit(200)).all()
    saida = []
    for oo, numero in rows:
        x = OrdemOperacaoOut.model_validate(oo)
        x.ordem_numero = numero
        saida.append(x)
    _preencher_definicoes(ctx.db, saida)
    return saida
