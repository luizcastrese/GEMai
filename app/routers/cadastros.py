"""Cadastros de apoio: recursos (Tela 4), pessoas, materiais e produtos/serviços.

Não há DELETE: itens são desativados (`ativo=false`) para preservar o histórico.
"""
from typing import Callable, Type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import audit
from ..deps import Ctx, get_ctx, requer_gestor
from ..models import Apontamento, Material, Pessoa, Produto, Recurso, Usuario
from ..schemas import (MaterialIn, MaterialOut, MaterialUpdate, PessoaIn, PessoaOut, PessoaUpdate,
                       ProdutoIn, ProdutoOut, ProdutoUpdate, RecursoIn, RecursoOut, RecursoUpdate)
from ..services import timecalc

router = APIRouter(tags=["cadastros"])


def crud(caminho: str, Model: Type, In, Upd, Out, entidade: str, *, por_unidade: bool,
         pos_leitura: Callable | None = None, validar: Callable | None = None):
    def lista(ctx: Ctx = Depends(get_ctx), unidade_id: int | None = None, ativo: bool | None = None,
              q: str | None = Query(None, max_length=100), limite: int = Query(100, ge=1, le=200),
              deslocamento: int = Query(0, ge=0)):
        stmt = ctx.query(Model)
        if unidade_id is not None and por_unidade:
            ctx.exige_unidade(unidade_id)
            stmt = stmt.where(Model.unidade_id == unidade_id)
        if ativo is not None:
            stmt = stmt.where(Model.ativo.is_(ativo))
        if q:
            stmt = stmt.where(Model.nome.ilike(f"%{q}%"))
        itens = ctx.db.scalars(stmt.order_by(Model.nome).limit(limite).offset(deslocamento)).all()
        out = [Out.model_validate(i) for i in itens]
        return pos_leitura(ctx, itens, out) if pos_leitura else out

    def criar(dados: In, ctx: Ctx = Depends(requer_gestor)):
        campos = dados.model_dump()
        if por_unidade:
            ctx.exige_unidade(campos["unidade_id"])
        if validar:
            validar(ctx, campos)
        obj = Model(empresa_id=ctx.empresa_id, **campos)
        ctx.db.add(obj)
        try:
            ctx.db.flush()
        except IntegrityError:
            ctx.db.rollback()
            raise HTTPException(409, "Já existe um registro com este nome.")
        ctx.auditar(f"{entidade}.criar", entidade, obj.id, None, audit.snap(obj))
        ctx.db.commit()
        return Out.model_validate(obj)

    def obter(id_: int, ctx: Ctx = Depends(get_ctx)):
        obj = ctx.obter(Model, id_)
        o = Out.model_validate(obj)
        return pos_leitura(ctx, [obj], [o])[0] if pos_leitura else o

    def atualizar(id_: int, dados: Upd, ctx: Ctx = Depends(requer_gestor)):
        obj = ctx.obter(Model, id_)
        campos = dados.model_dump(exclude_unset=True)
        if validar:
            validar(ctx, campos)
        antes = audit.snap(obj)
        for k, v in campos.items():
            if v is None and k in ("nome", "tipo"):
                continue
            setattr(obj, k, v)
        try:
            ctx.db.flush()
        except IntegrityError:
            ctx.db.rollback()
            raise HTTPException(409, "Já existe um registro com este nome.")
        ctx.auditar(f"{entidade}.atualizar", entidade, obj.id, antes, audit.snap(obj))
        ctx.db.commit()
        return Out.model_validate(obj)

    # anotações dinâmicas para o OpenAPI/validação do FastAPI
    criar.__annotations__["dados"] = In
    atualizar.__annotations__["dados"] = Upd
    router.add_api_route(f"/{caminho}", lista, methods=["GET"], response_model=list[Out], name=f"listar_{caminho}")
    router.add_api_route(f"/{caminho}", criar, methods=["POST"], response_model=Out, status_code=201,
                         name=f"criar_{caminho}")
    router.add_api_route(f"/{caminho}/{{id_}}", obter, methods=["GET"], response_model=Out, name=f"obter_{caminho}")
    router.add_api_route(f"/{caminho}/{{id_}}", atualizar, methods=["PATCH"], response_model=Out,
                         name=f"atualizar_{caminho}")


def _medias_recursos(ctx: Ctx, itens, out):
    """Tempo médio e de preparação atuais, calculados só com apontamentos APROVADOS."""
    ids = [r.id for r in itens]
    if not ids:
        return out
    apts = ctx.db.scalars(select(Apontamento).where(
        Apontamento.empresa_id == ctx.empresa_id, Apontamento.recurso_id.in_(ids),
        Apontamento.status == "aprovado", Apontamento.anulado.is_(False), Apontamento.fim.is_not(None)))
    ex: dict[int, list[float]] = {}
    prep: dict[int, list[float]] = {}
    for a in apts:
        d = timecalc.duracao_min(a.inicio, a.fim) or 0.0
        if a.tipo == "execucao":
            e = ex.setdefault(a.recurso_id, [0.0, 0.0])
            e[0] += d
            e[1] += a.quantidade_boa + a.quantidade_refugo
        elif a.tipo == "preparacao":
            prep.setdefault(a.recurso_id, []).append(d)
    for o in out:
        if o.id in ex and ex[o.id][1] > 0:
            o.tempo_medio_min = timecalc.arred(ex[o.id][0] / ex[o.id][1], 2)
        if o.id in prep:
            o.tempo_preparacao_medio_min = timecalc.arred(timecalc.mediana(prep[o.id]), 1)
    return out


def _validar_pessoa(ctx: Ctx, campos: dict):
    uid = campos.get("usuario_id")
    if uid is not None:
        u = ctx.db.get(Usuario, uid)
        if not u or u.empresa_id != ctx.empresa_id:
            raise HTTPException(422, "Usuário inválido.")


crud("recursos", Recurso, RecursoIn, RecursoUpdate, RecursoOut, "recurso", por_unidade=True,
     pos_leitura=_medias_recursos)
crud("pessoas", Pessoa, PessoaIn, PessoaUpdate, PessoaOut, "pessoa", por_unidade=True, validar=_validar_pessoa)
crud("materiais", Material, MaterialIn, MaterialUpdate, MaterialOut, "material", por_unidade=False)
crud("produtos", Produto, ProdutoIn, ProdutoUpdate, ProdutoOut, "produto", por_unidade=False)
