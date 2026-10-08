"""Apontamentos de produção e ocorrências (paradas, retrabalho, falta de material…).

Apontamentos nunca são apagados: só anulados com motivo, ficando na trilha de auditoria.
Somente apontamentos APROVADOS por um gestor alimentam o histórico de estimativas.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .. import audit
from ..deps import Ctx, get_ctx, requer_gestor
from ..models import Apontamento, Ocorrencia, Operacao, Ordem, OrdemOperacao, Pessoa, Recurso
from ..schemas import (AnularIn, ApontamentoManualIn, ApontamentoOut, DecisaoIn, FecharOcorrenciaIn,
                       FinalizarApontamentoIn, IniciarApontamentoIn, OcorrenciaIn, OcorrenciaOut)
from ..services import timecalc

router = APIRouter(tags=["apontamentos"])
TOLERANCIA_FUTURO = timedelta(minutes=5)
DURACAO_MAXIMA = timedelta(hours=24)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def apt_out(a: Apontamento, avisos: list[str] | None = None) -> ApontamentoOut:
    o = ApontamentoOut.model_validate(a)
    o.duracao_min = timecalc.arred(timecalc.duracao_min(a.inicio, a.fim), 2)
    o.avisos = avisos or []
    return o


def apts_out(ctx: Ctx, apts: list[Apontamento]) -> list[ApontamentoOut]:
    """Versão em lote com número da ordem e nome da operação (para telas de lista)."""
    ids = {a.ordem_operacao_id for a in apts}
    nomes = {}
    if ids:
        nomes = {i: (num, nome) for i, num, nome in ctx.db.execute(
            select(OrdemOperacao.id, Ordem.numero, OrdemOperacao.nome)
            .join(Ordem, Ordem.id == OrdemOperacao.ordem_id).where(OrdemOperacao.id.in_(ids)))}
    saida = []
    for a in apts:
        o = apt_out(a)
        o.ordem_numero, o.operacao_nome = nomes.get(a.ordem_operacao_id, (None, None))
        saida.append(o)
    return saida


def oc_out(c: Ocorrencia) -> OcorrenciaOut:
    o = OcorrenciaOut.model_validate(c)
    o.duracao_min = timecalc.arred(timecalc.duracao_min(c.inicio, c.fim), 2)
    return o


def _pessoa_do_usuario(ctx: Ctx, unidade_id: int) -> Pessoa | None:
    return ctx.db.scalar(select(Pessoa).where(
        Pessoa.empresa_id == ctx.empresa_id, Pessoa.usuario_id == ctx.usuario.id,
        Pessoa.unidade_id == unidade_id, Pessoa.ativo.is_(True)))


def _resolver_pessoa(ctx: Ctx, unidade_id: int, pessoa_id: int | None) -> int | None:
    if not ctx.eh_gestor:  # operador só registra por si mesmo
        p = _pessoa_do_usuario(ctx, unidade_id)
        return p.id if p else None
    if pessoa_id is None:
        return None
    p = ctx.db.get(Pessoa, pessoa_id)
    if not p or p.empresa_id != ctx.empresa_id or p.unidade_id != unidade_id:
        raise HTTPException(422, "Pessoa inválida para esta unidade.")
    return p.id


def _recurso(ctx: Ctx, recurso_id: int | None, unidade_id: int) -> Recurso | None:
    if recurso_id is None:
        return None
    r = ctx.db.get(Recurso, recurso_id)
    if not r or r.empresa_id != ctx.empresa_id or r.unidade_id != unidade_id:
        raise HTTPException(422, "Recurso inválido para esta unidade.")
    return r


def _contexto_operacao(ctx: Ctx, ooid: int) -> tuple[OrdemOperacao, Ordem]:
    oo = ctx.db.get(OrdemOperacao, ooid)
    if not oo or oo.empresa_id != ctx.empresa_id:
        raise HTTPException(404, "Registro não encontrado.")
    return oo, ctx.obter(Ordem, oo.ordem_id)


def _validar_extras(ctx: Ctx, oo: OrdemOperacao, extras: dict) -> dict:
    """Valida campos personalizados definidos na operação (seção 4, passo 6–7)."""
    op = ctx.db.get(Operacao, oo.operacao_id) if oo.operacao_id else None
    defs = {c["nome"]: c for c in (op.campos_extras if op else [])}
    desconhecidos = set(extras) - set(defs)
    if desconhecidos:
        raise HTTPException(422, "Campos não definidos para esta operação: " + ", ".join(sorted(desconhecidos)))
    limpo = {}
    for nome, d in defs.items():
        v = extras.get(nome)
        if v is None or v == "":
            if d.get("obrigatorio"):
                raise HTTPException(422, f"Campo obrigatório: {nome}")
            continue
        ok = {"numero": isinstance(v, (int, float)) and not isinstance(v, bool),
              "texto": isinstance(v, str) and len(v) <= 500, "booleano": isinstance(v, bool)}[d["tipo"]]
        if not ok:
            raise HTTPException(422, f"Valor inválido para '{nome}' (esperado {d['tipo']}).")
        limpo[nome] = v
    return limpo


def _checar_quantidades(tipo: str, boa: float, refugo: float) -> None:
    if tipo in ("preparacao", "espera") and (boa or refugo):
        raise HTTPException(422, "Quantidades só se aplicam a execução e retrabalho.")


def _checar_periodo(inicio: datetime, fim: datetime) -> None:
    if fim <= inicio:
        raise HTTPException(422, "O fim deve ser posterior ao início.")
    if fim > _agora() + TOLERANCIA_FUTURO:
        raise HTTPException(422, "O fim não pode estar no futuro.")
    if fim - inicio > DURACAO_MAXIMA:
        raise HTTPException(422, "Duração acima de 24h: divida em mais de um apontamento.")


def _aberto_do_executor(ctx: Ctx, pessoa_id: int | None) -> Apontamento | None:
    q = select(Apontamento).where(Apontamento.empresa_id == ctx.empresa_id, Apontamento.fim.is_(None),
                                  Apontamento.anulado.is_(False))
    q = q.where(Apontamento.pessoa_id == pessoa_id) if pessoa_id else q.where(
        Apontamento.registrado_por == ctx.usuario.id, Apontamento.pessoa_id.is_(None))
    return ctx.db.scalar(q)


def _avisos_habilitacao(ctx: Ctx, pessoa_id: int | None, rec: Recurso | None) -> list[str]:
    if not (pessoa_id and rec and rec.equipes_habilitadas):
        return []
    p = ctx.db.get(Pessoa, pessoa_id)
    if p and p.equipe not in rec.equipes_habilitadas:
        return [f"A equipe '{p.equipe or 'sem equipe'}' não consta entre as habilitadas para '{rec.nome}'."]
    return []


def _aplicar_inicio(oo: OrdemOperacao, o: Ordem, inicio: datetime) -> None:
    if oo.status == "pendente":
        oo.status = "em_andamento"
    oo.iniciada_em = oo.iniciada_em or inicio
    if o.status == "liberada":
        o.status = "em_producao"
    o.iniciada_em = o.iniciada_em or inicio


def _exigir_operacao_ativa(oo: OrdemOperacao, o: Ordem, manual: bool = False) -> None:
    if o.status == "parada" and not manual:
        raise HTTPException(409, "A ordem está parada. Encerre a parada para continuar apontando.")
    if o.status not in ("liberada", "em_producao", "parada"):
        raise HTTPException(409, "A ordem não está liberada para produção.")
    if oo.status in ("concluida", "pulada"):
        raise HTTPException(409, "A operação já foi encerrada. Peça a um gestor para reabri-la.")


# ------------------------------------------------------------------ apontamentos
@router.post("/apontamentos/iniciar", response_model=ApontamentoOut, status_code=201)
def iniciar(dados: IniciarApontamentoIn, ctx: Ctx = Depends(get_ctx)):
    oo, o = _contexto_operacao(ctx, dados.ordem_operacao_id)
    _exigir_operacao_ativa(oo, o)
    pessoa_id = _resolver_pessoa(ctx, o.unidade_id, dados.pessoa_id)
    rec = _recurso(ctx, dados.recurso_id or oo.recurso_id, o.unidade_id)
    if _aberto_do_executor(ctx, pessoa_id):
        raise HTTPException(409, "Já existe um apontamento em aberto para este executor. Finalize-o primeiro.")
    agora = _agora()
    a = Apontamento(empresa_id=ctx.empresa_id, unidade_id=o.unidade_id, ordem_id=o.id, ordem_operacao_id=oo.id,
                    tipo=dados.tipo, pessoa_id=pessoa_id, recurso_id=rec.id if rec else None, inicio=agora,
                    observacao=dados.observacao, registrado_por=ctx.usuario.id)
    ctx.db.add(a)
    _aplicar_inicio(oo, o, agora)
    ctx.db.flush()
    ctx.auditar("apontamento.iniciar", "apontamento", a.id, None, audit.snap(a))
    ctx.db.commit()
    return apt_out(a, _avisos_habilitacao(ctx, pessoa_id, rec))


def _meu_ou_gestor(ctx: Ctx, a: Apontamento) -> None:
    if not ctx.eh_gestor and a.registrado_por != ctx.usuario.id:
        raise HTTPException(404, "Registro não encontrado.")


@router.post("/apontamentos/{aid}/finalizar", response_model=ApontamentoOut)
def finalizar(aid: int, dados: FinalizarApontamentoIn, ctx: Ctx = Depends(get_ctx)):
    a = ctx.obter(Apontamento, aid)
    _meu_ou_gestor(ctx, a)
    if a.fim is not None or a.anulado:
        raise HTTPException(409, "Este apontamento já foi finalizado ou anulado.")
    fim = dados.fim or _agora()
    _checar_periodo(a.inicio, fim)
    _checar_quantidades(a.tipo, dados.quantidade_boa, dados.quantidade_refugo)
    oo = ctx.db.get(OrdemOperacao, a.ordem_operacao_id)
    extras = _validar_extras(ctx, oo, dados.dados_extras)
    antes = audit.snap(a)
    a.fim, a.quantidade_boa, a.quantidade_refugo, a.dados_extras = fim, dados.quantidade_boa, dados.quantidade_refugo, extras
    if dados.observacao is not None:
        a.observacao = dados.observacao
    ctx.auditar("apontamento.finalizar", "apontamento", a.id, antes, audit.snap(a))
    ctx.db.commit()
    return apt_out(a)


@router.post("/apontamentos", response_model=ApontamentoOut, status_code=201)
def registrar_manual(dados: ApontamentoManualIn, ctx: Ctx = Depends(requer_gestor)):
    """Lançamento retroativo (ex.: dado de papel). Exige gestor."""
    oo, o = _contexto_operacao(ctx, dados.ordem_operacao_id)
    _exigir_operacao_ativa(oo, o, manual=True)
    _checar_periodo(dados.inicio, dados.fim)
    _checar_quantidades(dados.tipo, dados.quantidade_boa, dados.quantidade_refugo)
    pessoa_id = _resolver_pessoa(ctx, o.unidade_id, dados.pessoa_id)
    rec = _recurso(ctx, dados.recurso_id or oo.recurso_id, o.unidade_id)
    extras = _validar_extras(ctx, oo, dados.dados_extras)
    a = Apontamento(empresa_id=ctx.empresa_id, unidade_id=o.unidade_id, ordem_id=o.id, ordem_operacao_id=oo.id,
                    tipo=dados.tipo, pessoa_id=pessoa_id, recurso_id=rec.id if rec else None, inicio=dados.inicio,
                    fim=dados.fim, quantidade_boa=dados.quantidade_boa, quantidade_refugo=dados.quantidade_refugo,
                    dados_extras=extras, observacao=dados.observacao, registrado_por=ctx.usuario.id)
    ctx.db.add(a)
    if o.status in ("liberada", "em_producao"):
        _aplicar_inicio(oo, o, dados.inicio)
    ctx.db.flush()
    ctx.auditar("apontamento.manual", "apontamento", a.id, None, audit.snap(a))
    ctx.db.commit()
    return apt_out(a, _avisos_habilitacao(ctx, pessoa_id, rec))


@router.get("/apontamentos", response_model=list[ApontamentoOut])
def listar(ctx: Ctx = Depends(get_ctx), ordem_id: int | None = None, ordem_operacao_id: int | None = None,
           status: str | None = None, abertos: bool | None = None, incluir_anulados: bool = False,
           limite: int = Query(100, ge=1, le=200), deslocamento: int = Query(0, ge=0)):
    q = ctx.query(Apontamento)
    if not ctx.eh_gestor:
        q = q.where(Apontamento.registrado_por == ctx.usuario.id)
    if ordem_id is not None:
        q = q.where(Apontamento.ordem_id == ordem_id)
    if ordem_operacao_id is not None:
        q = q.where(Apontamento.ordem_operacao_id == ordem_operacao_id)
    if status:
        q = q.where(Apontamento.status == status)
    if abertos is not None:
        q = q.where(Apontamento.fim.is_(None) if abertos else Apontamento.fim.is_not(None))
    if not incluir_anulados:
        q = q.where(Apontamento.anulado.is_(False))
    return apts_out(ctx, list(ctx.db.scalars(
        q.order_by(Apontamento.inicio.desc()).limit(limite).offset(deslocamento))))


@router.get("/apontamentos/abertos", response_model=list[ApontamentoOut])
def meus_abertos(ctx: Ctx = Depends(get_ctx)):
    q = ctx.query(Apontamento).where(Apontamento.fim.is_(None), Apontamento.anulado.is_(False),
                                     Apontamento.registrado_por == ctx.usuario.id)
    return apts_out(ctx, list(ctx.db.scalars(q)))


def _decidir(ctx: Ctx, a: Apontamento, status: str, obs: str) -> None:
    if a.anulado or a.fim is None:
        raise HTTPException(409, "Só apontamentos finalizados e não anulados podem ser decididos.")
    if a.status != "registrado":
        raise HTTPException(409, "Este apontamento já foi decidido.")
    antes = audit.snap(a)
    a.status, a.decidido_por, a.decidido_em = status, ctx.usuario.id, _agora()
    if obs:
        a.observacao = (a.observacao + "\n" if a.observacao else "") + f"[{status}] {obs}"
    ctx.auditar(f"apontamento.{status}", "apontamento", a.id, antes, audit.snap(a))


@router.post("/apontamentos/{aid}/aprovar", response_model=ApontamentoOut)
def aprovar(aid: int, dados: DecisaoIn, ctx: Ctx = Depends(requer_gestor)):
    a = ctx.obter(Apontamento, aid)
    _decidir(ctx, a, "aprovado", dados.observacao)
    ctx.db.commit()
    return apt_out(a)


@router.post("/apontamentos/{aid}/rejeitar", response_model=ApontamentoOut)
def rejeitar(aid: int, dados: DecisaoIn, ctx: Ctx = Depends(requer_gestor)):
    a = ctx.obter(Apontamento, aid)
    _decidir(ctx, a, "rejeitado", dados.observacao)
    ctx.db.commit()
    return apt_out(a)


class LoteIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


@router.post("/apontamentos/aprovar-lote", response_model=list[ApontamentoOut])
def aprovar_lote(dados: LoteIn, ctx: Ctx = Depends(requer_gestor)):
    saida = []
    for i in dict.fromkeys(dados.ids):
        a = ctx.obter(Apontamento, i)
        _decidir(ctx, a, "aprovado", "")
        saida.append(a)
    ctx.db.commit()
    return apts_out(ctx, saida)


@router.post("/apontamentos/{aid}/anular", response_model=ApontamentoOut)
def anular(aid: int, dados: AnularIn, ctx: Ctx = Depends(requer_gestor)):
    a = ctx.obter(Apontamento, aid)
    if a.anulado:
        raise HTTPException(409, "Apontamento já anulado.")
    antes = audit.snap(a)
    a.anulado, a.anulado_motivo, a.anulado_por, a.anulado_em = True, dados.motivo, ctx.usuario.id, _agora()
    ctx.auditar("apontamento.anular", "apontamento", a.id, antes, audit.snap(a))
    ctx.db.commit()
    return apt_out(a)


# ------------------------------------------------------------------ ocorrências
def _status_pos_parada(o: Ordem) -> str:
    return "em_producao" if o.iniciada_em else "liberada"


def _paradas_abertas(ctx: Ctx, ordem_id: int, exceto: int | None = None) -> int:
    q = select(func.count(Ocorrencia.id)).where(
        Ocorrencia.ordem_id == ordem_id, Ocorrencia.tipo == "parada", Ocorrencia.fim.is_(None),
        Ocorrencia.anulada.is_(False))
    if exceto:
        q = q.where(Ocorrencia.id != exceto)
    return ctx.db.scalar(q) or 0


@router.post("/ocorrencias", response_model=OcorrenciaOut, status_code=201)
def criar_ocorrencia(dados: OcorrenciaIn, ctx: Ctx = Depends(get_ctx)):
    ordem = oo = None
    if dados.ordem_id is not None:
        ordem = ctx.obter(Ordem, dados.ordem_id)
        unidade_id = ordem.unidade_id
        if dados.unidade_id not in (None, unidade_id):
            raise HTTPException(422, "A unidade não corresponde à ordem.")
    elif dados.unidade_id is not None:
        unidade_id = ctx.exige_unidade(dados.unidade_id).id
    else:
        raise HTTPException(422, "Informe ordem_id ou unidade_id.")
    if dados.ordem_operacao_id is not None:
        oo = ctx.db.get(OrdemOperacao, dados.ordem_operacao_id)
        if not oo or oo.empresa_id != ctx.empresa_id or (ordem and oo.ordem_id != ordem.id):
            raise HTTPException(422, "Operação inválida para esta ordem.")
        if ordem is None:
            ordem = ctx.obter(Ordem, oo.ordem_id)
            unidade_id = ordem.unidade_id
    _recurso(ctx, dados.recurso_id, unidade_id)
    inicio = dados.inicio or _agora()
    if inicio > _agora() + TOLERANCIA_FUTURO:
        raise HTTPException(422, "O início não pode estar no futuro.")
    if dados.fim is not None:
        _checar_periodo(inicio, dados.fim)
    if ordem and ordem.status in ("concluida", "cancelada"):
        raise HTTPException(409, "A ordem está encerrada.")
    c = Ocorrencia(empresa_id=ctx.empresa_id, unidade_id=unidade_id, ordem_id=ordem.id if ordem else None,
                   ordem_operacao_id=oo.id if oo else None, recurso_id=dados.recurso_id, tipo=dados.tipo,
                   causa=dados.causa, descricao=dados.descricao, impacto=dados.impacto, inicio=inicio, fim=dados.fim,
                   registrada_por=ctx.usuario.id)
    ctx.db.add(c)
    if c.tipo == "parada" and c.fim is None and ordem and ordem.status in ("liberada", "em_producao"):
        ordem.status = "parada"
    ctx.db.flush()
    ctx.auditar("ocorrencia.criar", "ocorrencia", c.id, None, audit.snap(c))
    ctx.db.commit()
    return oc_out(c)


@router.get("/ocorrencias", response_model=list[OcorrenciaOut])
def listar_ocorrencias(ctx: Ctx = Depends(get_ctx), unidade_id: int | None = None, ordem_id: int | None = None,
                       abertas: bool | None = None, tipo: str | None = None,
                       limite: int = Query(100, ge=1, le=200), deslocamento: int = Query(0, ge=0)):
    q = ctx.query(Ocorrencia).where(Ocorrencia.anulada.is_(False))
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        q = q.where(Ocorrencia.unidade_id == unidade_id)
    if ordem_id is not None:
        q = q.where(Ocorrencia.ordem_id == ordem_id)
    if tipo:
        q = q.where(Ocorrencia.tipo == tipo)
    if abertas is not None:
        q = q.where(Ocorrencia.fim.is_(None) if abertas else Ocorrencia.fim.is_not(None))
    return [oc_out(c) for c in ctx.db.scalars(q.order_by(Ocorrencia.inicio.desc()).limit(limite).offset(deslocamento))]


@router.post("/ocorrencias/{cid}/fechar", response_model=OcorrenciaOut)
def fechar_ocorrencia(cid: int, dados: FecharOcorrenciaIn, ctx: Ctx = Depends(get_ctx)):
    c = ctx.obter(Ocorrencia, cid)
    if c.fim is not None or c.anulada:
        raise HTTPException(409, "A ocorrência já foi encerrada ou anulada.")
    fim = dados.fim or _agora()
    _checar_periodo(c.inicio, fim)
    antes = audit.snap(c)
    c.fim = fim
    if c.tipo == "parada" and c.ordem_id and not _paradas_abertas(ctx, c.ordem_id, exceto=c.id):
        o = ctx.db.get(Ordem, c.ordem_id)
        if o.status == "parada":
            o.status = _status_pos_parada(o)
    ctx.auditar("ocorrencia.fechar", "ocorrencia", c.id, antes, audit.snap(c))
    ctx.db.commit()
    return oc_out(c)


@router.post("/ocorrencias/{cid}/anular", response_model=OcorrenciaOut)
def anular_ocorrencia(cid: int, dados: AnularIn, ctx: Ctx = Depends(requer_gestor)):
    c = ctx.obter(Ocorrencia, cid)
    if c.anulada:
        raise HTTPException(409, "Ocorrência já anulada.")
    antes = audit.snap(c)
    c.anulada, c.anulada_motivo = True, dados.motivo
    if c.tipo == "parada" and c.ordem_id and not _paradas_abertas(ctx, c.ordem_id):
        o = ctx.db.get(Ordem, c.ordem_id)
        if o.status == "parada":
            o.status = _status_pos_parada(o)
    ctx.auditar("ocorrencia.anular", "ocorrencia", c.id, antes, audit.snap(c))
    ctx.db.commit()
    return oc_out(c)
