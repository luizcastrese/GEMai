from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from .. import audit
from ..deps import Ctx, get_ctx, requer_admin, requer_gestor
from ..models import Unidade
from ..schemas import EmpresaOut, EmpresaUpdate, UnidadeIn, UnidadeOut, UnidadeUpdate
from ..services import ia

router = APIRouter(tags=["empresa"])


def _empresa_out(ctx: Ctx) -> EmpresaOut:
    from ..services.ia import claude
    o = EmpresaOut.model_validate(ctx.empresa)
    o.ia_disponivel = claude.disponivel()
    o.ia_provedor_ativo = ia.provedor_ativo(ctx.empresa)
    return o


@router.get("/empresa", response_model=EmpresaOut)
def obter_empresa(ctx: Ctx = Depends(get_ctx)):
    return _empresa_out(ctx)


@router.patch("/empresa", response_model=EmpresaOut)
def atualizar_empresa(dados: EmpresaUpdate, ctx: Ctx = Depends(requer_admin)):
    if dados.fuso:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(dados.fuso)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, "Fuso horário inválido (ex.: America/Sao_Paulo).")
    antes = audit.snap(ctx.empresa)
    for k, v in dados.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(ctx.empresa, k, v)
    ctx.auditar("empresa.atualizar", "empresa", ctx.empresa_id, antes, audit.snap(ctx.empresa))
    ctx.db.commit()
    return _empresa_out(ctx)


@router.get("/unidades", response_model=list[UnidadeOut])
def listar_unidades(ctx: Ctx = Depends(get_ctx)):
    q = select(Unidade).where(Unidade.empresa_id == ctx.empresa_id).order_by(Unidade.nome)
    if ctx.unidades is not None:
        q = q.where(Unidade.id.in_(ctx.unidades or {-1}))
    return ctx.db.scalars(q).all()


@router.post("/unidades", response_model=UnidadeOut, status_code=201)
def criar_unidade(dados: UnidadeIn, ctx: Ctx = Depends(requer_admin)):
    if ctx.db.scalar(select(Unidade.id).where(Unidade.empresa_id == ctx.empresa_id, Unidade.nome == dados.nome)):
        raise HTTPException(409, "Já existe uma unidade com este nome.")
    u = Unidade(empresa_id=ctx.empresa_id, **dados.model_dump())
    ctx.db.add(u)
    ctx.db.flush()
    ctx.auditar("unidade.criar", "unidade", u.id, None, audit.snap(u))
    ctx.db.commit()
    return u


@router.get("/unidades/{uid}", response_model=UnidadeOut)
def obter_unidade(uid: int, ctx: Ctx = Depends(get_ctx)):
    return ctx.exige_unidade(uid)


@router.patch("/unidades/{uid}", response_model=UnidadeOut)
def atualizar_unidade(uid: int, dados: UnidadeUpdate, ctx: Ctx = Depends(requer_gestor)):
    u = ctx.exige_unidade(uid)
    campos = dados.model_dump(exclude_unset=True)
    if ("nome" in campos or "ativa" in campos) and not ctx.eh_admin:
        raise HTTPException(403, "Somente administradores alteram nome ou situação da unidade.")
    if campos.get("nome") and campos["nome"] != u.nome and ctx.db.scalar(
            select(Unidade.id).where(Unidade.empresa_id == ctx.empresa_id, Unidade.nome == campos["nome"])):
        raise HTTPException(409, "Já existe uma unidade com este nome.")
    antes = audit.snap(u)
    for k, v in campos.items():
        if v is not None:
            setattr(u, k, v)
    ctx.auditar("unidade.atualizar", "unidade", u.id, antes, audit.snap(u))
    ctx.db.commit()
    return u
