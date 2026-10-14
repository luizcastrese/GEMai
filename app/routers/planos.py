"""Produto (componentes + ligações) → plano de trabalho com tempos."""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .. import audit
from ..deps import Ctx, get_ctx
from ..models import Componente, Espaco, Ligacao, Ordem, PerfilMaoDeObra, PlanoPasso, PlanoTrabalho, Produto, Recurso, ReferenciaTempo
from ..schemas import (AplicarEstruturaIn, ComponenteIn, ComponenteOut, ComponenteUpdate, EstruturaOut, InterpretarProdutoIn,
                       InterpretarProdutoOut, LigacaoIn, LigacaoOut, OrdemOut, PlanoGerarIn, PlanoOrdemIn, PlanoOut,
                       PlanoPassoOut, ReferenciaIn, ReferenciaOut)
from ..services import ia, modelo_tempo, plano as svc
from ..services.dashboard import tz_empresa
from .ordens import _numero, ordem_out

router = APIRouter(tags=["planos"])


# ------------------------------------------------------------------ estrutura do produto
def _comp_out(c: Componente) -> ComponenteOut:
    o = ComponenteOut.model_validate(c)
    peso, origem = svc.estimar_peso(c)
    o.peso_estimado_kg = peso if origem == "estimado" else None
    return o


def _estrutura(ctx: Ctx, produto: Produto) -> EstruturaOut:
    comps = ctx.db.scalars(select(Componente).where(Componente.produto_id == produto.id).order_by(Componente.ordem, Componente.id)).all()
    ligs = ctx.db.scalars(select(Ligacao).where(Ligacao.produto_id == produto.id).order_by(Ligacao.ordem, Ligacao.id)).all()
    return EstruturaOut(produto_id=produto.id, componentes=[_comp_out(c) for c in comps],
                        ligacoes=[LigacaoOut.model_validate(l) for l in ligs])


@router.get("/produtos/{pid}/estrutura", response_model=EstruturaOut)
def estrutura(pid: int, ctx: Ctx = Depends(get_ctx)):
    return _estrutura(ctx, ctx.obter(Produto, pid))


@router.post("/produtos/{pid}/componentes", response_model=ComponenteOut, status_code=201)
def criar_componente(pid: int, dados: ComponenteIn, ctx: Ctx = Depends(get_ctx)):
    p = ctx.obter(Produto, pid)
    n = len(ctx.db.scalars(select(Componente.id).where(Componente.produto_id == p.id)).all())
    c = Componente(empresa_id=ctx.empresa_id, produto_id=p.id, ordem=n, **dados.model_dump())
    ctx.db.add(c)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(409, "Já existe um componente com este nome neste produto.")
    ctx.auditar("componente.criar", "componente", c.id, None, audit.snap(c))
    ctx.db.commit()
    return _comp_out(c)


def _componente(ctx: Ctx, pid: int, cid: int) -> Componente:
    p = ctx.obter(Produto, pid)
    c = ctx.db.get(Componente, cid)
    if not c or c.produto_id != p.id or c.empresa_id != ctx.empresa_id:
        raise HTTPException(404, "Registro não encontrado.")
    return c


@router.patch("/produtos/{pid}/componentes/{cid}", response_model=ComponenteOut)
def atualizar_componente(pid: int, cid: int, dados: ComponenteUpdate, ctx: Ctx = Depends(get_ctx)):
    c = _componente(ctx, pid, cid)
    antes = audit.snap(c)
    for k, v in dados.model_dump(exclude_unset=True).items():
        if v is None and k in ("nome", "quantidade", "furos", "grupo", "material"):
            continue
        setattr(c, k, v)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(409, "Já existe um componente com este nome neste produto.")
    ctx.auditar("componente.atualizar", "componente", c.id, antes, audit.snap(c))
    ctx.db.commit()
    return _comp_out(c)


@router.delete("/produtos/{pid}/componentes/{cid}", status_code=204)
def remover_componente(pid: int, cid: int, ctx: Ctx = Depends(get_ctx)):
    c = _componente(ctx, pid, cid)
    ctx.db.execute(delete(Ligacao).where(Ligacao.produto_id == pid, (Ligacao.componente_id == cid) | (Ligacao.ligado_a_id == cid)))
    ctx.auditar("componente.remover", "componente", c.id, audit.snap(c), None)
    ctx.db.delete(c)
    ctx.db.commit()


@router.post("/produtos/{pid}/ligacoes", response_model=LigacaoOut, status_code=201)
def criar_ligacao(pid: int, dados: LigacaoIn, ctx: Ctx = Depends(get_ctx)):
    p = ctx.obter(Produto, pid)
    _componente(ctx, pid, dados.componente_id)
    if dados.ligado_a_id is not None:
        _componente(ctx, pid, dados.ligado_a_id)
        if dados.ligado_a_id == dados.componente_id:
            raise HTTPException(422, "Um componente não pode ser ligado a ele mesmo.")
    n = len(ctx.db.scalars(select(Ligacao.id).where(Ligacao.produto_id == p.id)).all())
    l = Ligacao(empresa_id=ctx.empresa_id, produto_id=p.id, ordem=n, **dados.model_dump())
    ctx.db.add(l)
    ctx.db.flush()
    ctx.auditar("ligacao.criar", "ligacao", l.id, None, audit.snap(l))
    ctx.db.commit()
    return l


@router.delete("/produtos/{pid}/ligacoes/{lid}", status_code=204)
def remover_ligacao(pid: int, lid: int, ctx: Ctx = Depends(get_ctx)):
    p = ctx.obter(Produto, pid)
    l = ctx.db.get(Ligacao, lid)
    if not l or l.produto_id != p.id or l.empresa_id != ctx.empresa_id:
        raise HTTPException(404, "Registro não encontrado.")
    ctx.auditar("ligacao.remover", "ligacao", l.id, audit.snap(l), None)
    ctx.db.delete(l)
    ctx.db.commit()


@router.post("/produtos/{pid}/interpretar", response_model=InterpretarProdutoOut)
def interpretar(pid: int, dados: InterpretarProdutoIn, ctx: Ctx = Depends(get_ctx)):
    """A IA lê a descrição e PROPÕE componentes e ligações. Nada é salvo: o usuário confere e aplica."""
    p = ctx.obter(Produto, pid)
    r, provedor, aviso = ia.interpretar_produto(ctx.empresa, {"produto": p.nome, "descricao": dados.descricao,
                                                              "metodos": list(modelo_tempo.METODOS_LIGACAO)})
    return InterpretarProdutoOut(
        componentes=[ComponenteIn(**c.model_dump()) for c in r.componentes],
        ligacoes=[l.model_dump() for l in r.ligacoes], dados_faltantes=r.dados_faltantes, observacoes=r.observacoes,
        provedor=provedor, aviso=aviso)


@router.post("/produtos/{pid}/estrutura", response_model=EstruturaOut)
def aplicar_estrutura(pid: int, dados: AplicarEstruturaIn, ctx: Ctx = Depends(get_ctx)):
    """Grava a estrutura conferida pelo usuário (componentes e ligações por nome)."""
    p = ctx.obter(Produto, pid)
    if dados.substituir:
        ctx.db.execute(delete(Ligacao).where(Ligacao.produto_id == p.id))
        ctx.db.execute(delete(Componente).where(Componente.produto_id == p.id))
        ctx.db.flush()
    existentes = {c.nome.lower(): c for c in ctx.db.scalars(select(Componente).where(Componente.produto_id == p.id))}
    ordem = len(existentes)
    for c in dados.componentes:
        if c.nome.lower() in existentes:
            continue
        obj = Componente(empresa_id=ctx.empresa_id, produto_id=p.id, ordem=ordem, **c.model_dump())
        ordem += 1
        ctx.db.add(obj)
        existentes[c.nome.lower()] = obj
    ctx.db.flush()
    for i, l in enumerate(dados.ligacoes):
        a = existentes.get(str(l.get("componente", "")).lower())
        b = existentes.get(str(l.get("ligado_a") or "").lower())
        metodo = str(l.get("metodo", "outro")).lower()
        if a is None or (l.get("ligado_a") and b is None) or a is b:
            continue
        ctx.db.add(Ligacao(empresa_id=ctx.empresa_id, produto_id=p.id, componente_id=a.id, ligado_a_id=b.id if b else None,
                           metodo=metodo if metodo in modelo_tempo.METODOS_LIGACAO else "outro",
                           fixadores=int(min(max(int(l.get("fixadores") or 0), 0), 10000)), ordem=i))
    ctx.auditar("produto.estrutura", "produto", p.id, None, {"componentes": len(dados.componentes), "ligacoes": len(dados.ligacoes)})
    ctx.db.commit()
    return _estrutura(ctx, p)


# ------------------------------------------------------------------ referências de tempo
@router.get("/referencias-tempo", response_model=list[ReferenciaOut])
def listar_referencias(ctx: Ctx = Depends(get_ctx)):
    informadas = {r.chave: r.minutos for r in ctx.db.scalars(select(ReferenciaTempo).where(ReferenciaTempo.empresa_id == ctx.empresa_id))}
    out = []
    for k, v in modelo_tempo.REFERENCIAS_MONTAGEM.items():
        out.append(ReferenciaOut(chave=k, minutos=informadas.get(k, v), padrao_minutos=v, informada=k in informadas))
    for k, v in informadas.items():
        if k not in modelo_tempo.REFERENCIAS_MONTAGEM:
            out.append(ReferenciaOut(chave=k, minutos=v, informada=True))
    return out


@router.put("/referencias-tempo", response_model=ReferenciaOut)
def definir_referencia(dados: ReferenciaIn, ctx: Ctx = Depends(get_ctx)):
    r = ctx.db.scalar(select(ReferenciaTempo).where(ReferenciaTempo.empresa_id == ctx.empresa_id, ReferenciaTempo.chave == dados.chave))
    antes = audit.snap(r) if r else None
    if r:
        r.minutos, r.atualizado_em = dados.minutos, datetime.now(timezone.utc)
    else:
        r = ReferenciaTempo(empresa_id=ctx.empresa_id, chave=dados.chave, minutos=dados.minutos)
        ctx.db.add(r)
    ctx.db.flush()
    ctx.auditar("referencia_tempo.definir", "referencia_tempo", r.id, antes, audit.snap(r))
    ctx.db.commit()
    return ReferenciaOut(chave=r.chave, minutos=r.minutos, padrao_minutos=modelo_tempo.REFERENCIAS_MONTAGEM.get(r.chave), informada=True)


@router.delete("/referencias-tempo/{chave}", status_code=204)
def restaurar_referencia(chave: str, ctx: Ctx = Depends(get_ctx)):
    r = ctx.db.scalar(select(ReferenciaTempo).where(ReferenciaTempo.empresa_id == ctx.empresa_id, ReferenciaTempo.chave == chave))
    if r:
        ctx.auditar("referencia_tempo.restaurar", "referencia_tempo", r.id, audit.snap(r), None)
        ctx.db.delete(r)
        ctx.db.commit()


# ------------------------------------------------------------------ planos
def _plano_out(ctx: Ctx, p: PlanoTrabalho, detalhado: bool = True) -> PlanoOut:
    o = PlanoOut.model_validate(p)
    prod = ctx.db.get(Produto, p.produto_id)
    o.produto_nome = prod.nome if prod else None
    if detalhado:
        rec = {r.id: r.nome for r in ctx.db.scalars(select(Recurso).where(Recurso.empresa_id == ctx.empresa_id, Recurso.unidade_id == p.unidade_id))}
        esp = {e.id: e.nome for e in ctx.db.scalars(select(Espaco).where(Espaco.empresa_id == ctx.empresa_id, Espaco.unidade_id == p.unidade_id))}
        passos = []
        for s in p.passos:
            x = PlanoPassoOut.model_validate(s)
            x.recurso_nome, x.origem_nome, x.destino_nome = rec.get(s.recurso_id), esp.get(s.espaco_origem_id), esp.get(s.espaco_destino_id)
            passos.append(x)
        o.passos = passos
    else:
        o.passos = None
    return o


def _plano(ctx: Ctx, pid: int) -> PlanoTrabalho:
    return ctx.obter(PlanoTrabalho, pid)


def _cfg(dados: PlanoGerarIn) -> dict:
    return {"nome": dados.nome, "inicio": dados.inicio, "blocos": dados.blocos, "so_dias_uteis": dados.so_dias_uteis,
            "pessoas": dados.pessoas, "perfil_id": dados.perfil_id, "fadiga_pct_hora": dados.fadiga_pct_hora}


@router.post("/planos", response_model=PlanoOut, status_code=201)
def gerar_plano(dados: PlanoGerarIn, ctx: Ctx = Depends(get_ctx)):
    ctx.exige_unidade(dados.unidade_id)
    produto = ctx.obter(Produto, dados.produto_id)
    plano = svc.gerar(ctx, produto, dados.quantidade, dados.unidade_id, _cfg(dados))
    ctx.auditar("plano.gerar", "plano_trabalho", plano.id, None, {"produto_id": produto.id, "quantidade": dados.quantidade, "provedor": plano.provedor})
    ctx.db.commit()
    return _plano_out(ctx, plano)


@router.get("/planos", response_model=list[PlanoOut])
def listar_planos(ctx: Ctx = Depends(get_ctx), unidade_id: int | None = None, produto_id: int | None = None):
    stmt = ctx.query(PlanoTrabalho)
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        stmt = stmt.where(PlanoTrabalho.unidade_id == unidade_id)
    if produto_id is not None:
        stmt = stmt.where(PlanoTrabalho.produto_id == produto_id)
    return [_plano_out(ctx, p, False) for p in ctx.db.scalars(stmt.order_by(PlanoTrabalho.id.desc()).limit(100))]


@router.get("/planos/{pid}", response_model=PlanoOut)
def obter_plano(pid: int, ctx: Ctx = Depends(get_ctx)):
    return _plano_out(ctx, _plano(ctx, pid))


@router.post("/planos/{pid}/recalcular", response_model=PlanoOut)
def recalcular(pid: int, dados: PlanoGerarIn, ctx: Ctx = Depends(get_ctx)):
    """Regera o plano (novos dados do contorno, quantidade ou jornada). Volta a ser rascunho."""
    p = _plano(ctx, pid)
    if p.status != "rascunho":
        raise HTTPException(409, "Só planos em rascunho podem ser recalculados.")
    if dados.produto_id != p.produto_id or dados.unidade_id != p.unidade_id:
        raise HTTPException(422, "Produto e unidade não podem mudar ao recalcular.")
    svc.gerar(ctx, ctx.obter(Produto, p.produto_id), dados.quantidade, p.unidade_id, _cfg(dados), plano=p)
    ctx.auditar("plano.recalcular", "plano_trabalho", p.id, None, {"quantidade": dados.quantidade, "provedor": p.provedor})
    ctx.db.commit()
    return _plano_out(ctx, p)


@router.post("/planos/{pid}/confirmar", response_model=PlanoOut)
def confirmar(pid: int, ctx: Ctx = Depends(get_ctx)):
    """Confirmação MANUAL. Não acontece sozinha: a IA só sugere."""
    p = _plano(ctx, pid)
    if p.status != "rascunho":
        raise HTTPException(409, "O plano já foi decidido.")
    p.status, p.confirmado_por, p.confirmado_em = "confirmado", ctx.usuario.id, datetime.now(timezone.utc)
    ctx.auditar("plano.confirmar", "plano_trabalho", p.id, {"status": "rascunho"}, {"status": "confirmado", "completo": p.totais.get("completo")})
    ctx.db.commit()
    return _plano_out(ctx, p)


@router.post("/planos/{pid}/cancelar", response_model=PlanoOut)
def cancelar(pid: int, ctx: Ctx = Depends(get_ctx)):
    p = _plano(ctx, pid)
    if p.status == "cancelado" or p.ordem_id:
        raise HTTPException(409, "Este plano não pode ser cancelado.")
    antes = p.status
    p.status = "cancelado"
    ctx.auditar("plano.cancelar", "plano_trabalho", p.id, {"status": antes}, {"status": "cancelado"})
    ctx.db.commit()
    return _plano_out(ctx, p)


@router.post("/planos/{pid}/gerar-ordem", response_model=OrdemOut, status_code=201)
def gerar_ordem(pid: int, dados: PlanoOrdemIn, ctx: Ctx = Depends(get_ctx)):
    p = _plano(ctx, pid)
    o = svc.gerar_ordem(ctx, p, dados.cliente or "", dados.prazo, _numero)
    ctx.auditar("plano.gerar_ordem", "plano_trabalho", p.id, None, {"ordem_id": o.id})
    ctx.db.commit()
    return ordem_out(ctx, o, True)


@router.get("/planos/{pid}/exportar.csv")
def exportar_csv(pid: int, ctx: Ctx = Depends(get_ctx)):
    p = _plano(ctx, pid)
    det = _plano_out(ctx, p)
    tz = tz_empresa(ctx.empresa)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["#", "Passo", "Tipo", "Pessoas", "Equipamento", "De", "Para", "Início previsto", "Fim previsto", "Tempo padrão (min)", "Tempo agendado (min)", "Pendências"])

    def _cel(v):  # evita injeção de fórmulas em planilhas
        v = "" if v is None else str(v)
        return "'" + v if v and v[0] in "=+-@\t\r" else v

    for s in det.passos or []:
        f = lambda d: d.astimezone(tz).strftime("%d/%m/%Y %H:%M") if d else ""  # noqa: E731
        w.writerow([s.sequencia, _cel(s.nome), s.tipo, s.pessoas, _cel(s.recurso_nome), _cel(s.origem_nome), _cel(s.destino_nome),
                    f(s.inicio_prev), f(s.fim_prev), "" if s.tempo_padrao_min is None else f"{s.tempo_padrao_min:.2f}".replace(".", ","),
                    "" if s.tempo_agendado_min is None else f"{s.tempo_agendado_min:.2f}".replace(".", ","), _cel("; ".join(s.faltantes))])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="plano-{p.id}.csv"'})
