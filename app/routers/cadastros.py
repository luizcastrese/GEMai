"""Cadastros de apoio: recursos (Tela 4), pessoas, materiais e produtos/serviços.

Não há DELETE: itens são desativados (`ativo=false`) para preservar o histórico.
"""
from datetime import datetime, timezone
from typing import Callable, Type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import audit
from ..deps import Ctx, get_ctx
from ..models import Apontamento, Distancia, Espaco, Material, Pessoa, PerfilMaoDeObra, Produto, Recurso, Usuario
from ..schemas import (CalibrarRitmoIn, CalibrarRitmoOut, RitmoPessoaOut, DistanciaIn, DistanciaOut, EspacoIn, EspacoOut, EspacoUpdate, PerfilIn, PerfilOut, PerfilUpdate, MaterialIn, MaterialOut, MaterialUpdate, PessoaIn, PessoaOut, PessoaUpdate,
                       ProdutoIn, ProdutoOut, ProdutoUpdate, RecursoIn, RecursoOut, RecursoUpdate)
from ..config import get_settings
from ..services import calibracao_ritmo, ritmo, timecalc

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

    def criar(dados: In, ctx: Ctx = Depends(get_ctx)):
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

    def atualizar(id_: int, dados: Upd, ctx: Ctx = Depends(get_ctx)):
        obj = ctx.obter(Model, id_)
        campos = dados.model_dump(exclude_unset=True)
        if validar:
            validar(ctx, campos, obj)
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


def _validar_pessoa(ctx: Ctx, campos: dict, obj: Pessoa | None = None):
    """`obj` é a pessoa existente (edição). Também deriva campos do ritmo (informado/limpo) em `campos`."""
    uid = campos.get("usuario_id")
    if uid is not None:
        u = ctx.db.get(Usuario, uid)
        if not u or u.empresa_id != ctx.empresa_id:
            raise HTTPException(422, "Usuário inválido.")
    perfil_id = campos.get("perfil_id")
    if perfil_id is not None:
        unidade_id = campos.get("unidade_id", obj.unidade_id if obj else None)
        pf = ctx.db.get(PerfilMaoDeObra, perfil_id)
        if pf is None or pf.empresa_id != ctx.empresa_id or pf.unidade_id != unidade_id:
            raise HTTPException(422, "Perfil de mão de obra inválido para esta unidade.")
    if "ritmo_pct" in campos:
        if obj is not None and campos["ritmo_pct"] == obj.ritmo_pct:
            return  # valor reenviado sem mudança (ex.: formulário): não troca a origem calibrada por "informado"
        informado = campos["ritmo_pct"] is not None
        campos.update(ritmo_origem="informado" if informado else "", ritmo_amostras=0, ritmo_calibrado_em=None)


def _ritmos_efetivos(ctx: Ctx, itens, out):
    """Preenche o ritmo efetivo (pessoa > perfil > 100) de cada pessoa listada."""
    efetivos = ritmo.ritmos_das_pessoas(ctx.db, ctx.empresa_id, {p.id for p in itens})
    for o in out:
        r = efetivos.get(o.id)
        if r:
            o.ritmo_efetivo, o.ritmo_efetivo_origem = r.valor, r.origem
    return out


def _validar_recurso(ctx: Ctx, campos: dict, obj=None):
    eid = campos.get("espaco_id")
    if eid is not None:
        e = ctx.db.get(Espaco, eid)
        if not e or e.empresa_id != ctx.empresa_id:
            raise HTTPException(422, "Espaço inválido.")
        if campos.get("unidade_id") is not None and e.unidade_id != campos["unidade_id"]:
            raise HTTPException(422, "O espaço pertence a outra unidade.")


crud("recursos", Recurso, RecursoIn, RecursoUpdate, RecursoOut, "recurso", por_unidade=True,
     pos_leitura=_medias_recursos, validar=_validar_recurso)
crud("espacos", Espaco, EspacoIn, EspacoUpdate, EspacoOut, "espaco", por_unidade=True)
crud("perfis-mao-de-obra", PerfilMaoDeObra, PerfilIn, PerfilUpdate, PerfilOut, "perfil_mao_de_obra", por_unidade=True)
crud("pessoas", Pessoa, PessoaIn, PessoaUpdate, PessoaOut, "pessoa", por_unidade=True, validar=_validar_pessoa,
     pos_leitura=_ritmos_efetivos)


@router.post("/pessoas/calibrar-ritmo", response_model=CalibrarRitmoOut)
def calibrar_ritmo(dados: CalibrarRitmoIn, ctx: Ctx = Depends(get_ctx)):
    """Sugere o ritmo de cada pessoa RELATIVO À EQUIPE a partir do histórico aprovado (ver `calibracao_ritmo`).

    Com `aplicar=false` é só uma prévia: nada é gravado. Com `aplicar=true` grava `ritmo_pct`, origem
    `calibrado`, nº de amostras e data, com auditoria; ritmo `informado` nunca é sobrescrito."""
    stmt = ctx.query(Pessoa)
    if dados.unidade_id is not None:
        ctx.exige_unidade(dados.unidade_id)
        stmt = stmt.where(Pessoa.unidade_id == dados.unidade_id)
    pessoas = list(ctx.db.scalars(stmt))
    cal = calibracao_ritmo.calibrar(ctx.db, ctx.empresa_id, pessoas)
    atuais = ritmo.ritmos_das_pessoas(ctx.db, ctx.empresa_id, {p.id for p in pessoas})
    s = get_settings()
    agora = datetime.now(timezone.utc)
    linhas, aplicadas = [], 0
    for sg in cal.pessoas:
        p = sg.pessoa
        atual = atuais[p.id]
        origem_atual = (p.ritmo_origem or "informado") if atual.origem == "pessoa" else atual.origem
        gravar = dados.aplicar and sg.status == "sugerido"
        if gravar:
            antes = audit.snap(p)
            p.ritmo_pct, p.ritmo_origem, p.ritmo_amostras, p.ritmo_calibrado_em = sg.ritmo_sugerido, "calibrado", sg.amostras, agora
            ctx.auditar("pessoa.calibrar_ritmo", "pessoa", p.id, antes, audit.snap(p))
            aplicadas += 1
        linhas.append(RitmoPessoaOut(
            pessoa_id=p.id, nome=p.nome, unidade_id=p.unidade_id, status=sg.status, aplicado=gravar,
            ritmo_atual=atual.valor, ritmo_atual_origem=origem_atual, ritmo_sugerido=sg.ritmo_sugerido,
            operacoes_usadas=sg.operacoes, amostras=sg.amostras, motivo=sg.motivo))
    ctx.db.commit()
    return CalibrarRitmoOut(
        aplicado=dados.aplicar, aviso=calibracao_ritmo.AVISO, aplicadas=aplicadas, pessoas=linhas,
        criterios={"min_amostras_operacao": s.min_amostras_historico, "min_amostras_pessoa": s.min_amostras_ritmo,
                   "min_operacoes": s.min_operacoes_ritmo, "limites_pct": [50, 150]},
        operacoes_consideradas=cal.operacoes_consideradas, operacoes_ignoradas=cal.operacoes_ignoradas)
crud("materiais", Material, MaterialIn, MaterialUpdate, MaterialOut, "material", por_unidade=False)
crud("produtos", Produto, ProdutoIn, ProdutoUpdate, ProdutoOut, "produto", por_unidade=False)


# ---------------------------------------------------------------- distâncias entre espaços
@router.get("/distancias", response_model=list[DistanciaOut])
def listar_distancias(unidade_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.exige_unidade(unidade_id)
    return ctx.db.scalars(ctx.query(Distancia).where(Distancia.unidade_id == unidade_id)).all()


@router.put("/distancias", response_model=DistanciaOut)
def definir_distancia(dados: DistanciaIn, ctx: Ctx = Depends(get_ctx)):
    """Cria ou atualiza a distância entre dois espaços da mesma unidade (vale nos dois sentidos)."""
    if dados.origem_id == dados.destino_id:
        raise HTTPException(422, "Origem e destino devem ser diferentes.")
    o, d = ctx.obter(Espaco, dados.origem_id), ctx.obter(Espaco, dados.destino_id)
    if o.unidade_id != d.unidade_id:
        raise HTTPException(422, "Os espaços pertencem a unidades diferentes.")
    a, b = sorted((o.id, d.id))
    existente = ctx.db.scalar(select(Distancia).where(Distancia.empresa_id == ctx.empresa_id,
                                                      Distancia.origem_id == a, Distancia.destino_id == b))
    antes = audit.snap(existente) if existente else None
    if existente:
        existente.metros = dados.metros
        obj = existente
    else:
        obj = Distancia(empresa_id=ctx.empresa_id, unidade_id=o.unidade_id, origem_id=a, destino_id=b, metros=dados.metros)
        ctx.db.add(obj)
    ctx.db.flush()
    ctx.auditar("distancia.definir", "distancia", obj.id, antes, audit.snap(obj))
    ctx.db.commit()
    return obj
