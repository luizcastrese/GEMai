"""Processos, etapas, operações (Tela 3) e parâmetros versionados.

Versionamento: cada versão de processo é uma linha. Só rascunhos têm a estrutura editada;
ao publicar, a versão anterior vira 'substituido'. Ordens ficam presas à versão com que
foram criadas. Parâmetros têm versionamento próprio (origem + validação), pois são
calibrados continuamente sem exigir nova versão do processo.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from .. import audit
from ..constants import PARAMETROS_PADRAO
from ..deps import Ctx, get_ctx, requer_gestor
from ..models import Espaco, Etapa, ModeloTempo, Operacao, Parametro, Processo, Recurso
from ..schemas import (DecisaoIn, EtapaIn, EtapaOut, EtapaUpdate, OperacaoIn, OperacaoOut, OperacaoUpdate,
                       ParametroIn, ParametroOut, ProcessoIn, ProcessoOut, ProcessoUpdate)
from ..services import estimativa, timecalc
from ..services.dashboard import alerta_ergonomia

router = APIRouter(tags=["processos"])


# ------------------------------------------------------------------ serialização
def op_out(op: Operacao) -> OperacaoOut:
    o = OperacaoOut.model_validate(op)
    o.alerta_ergonomia = alerta_ergonomia(op.ergonomia)
    return o


def etapa_out(e: Etapa) -> EtapaOut:
    o = EtapaOut.model_validate(e, from_attributes=True)
    o.operacoes = [op_out(op) for op in e.operacoes]
    return o


def processo_out(p: Processo, detalhado: bool = True, avisos: list[str] | None = None) -> ProcessoOut:
    o = ProcessoOut.model_validate(p)
    o.etapas = [etapa_out(e) for e in p.etapas] if detalhado else None
    o.avisos = avisos or []
    return o


# ------------------------------------------------------------------ helpers
def _rascunho(p: Processo) -> None:
    if p.status != "rascunho":
        raise HTTPException(409, "A estrutura só pode ser editada em rascunho. "
                                 "Crie uma nova versão (POST /processos/{id}/nova-versao).")


def _renumerar(itens: list, mover=None, para: int | None = None) -> None:
    itens = [i for i in itens if i is not mover]
    if mover is not None:
        pos = min(max((para or len(itens) + 1) - 1, 0), len(itens))
        itens.insert(pos, mover)
    for n, i in enumerate(itens, 1):
        i.sequencia = n


def _recurso_da_unidade(ctx: Ctx, recurso_id: int | None, unidade_id: int) -> None:
    if recurso_id is None:
        return
    r = ctx.db.get(Recurso, recurso_id)
    if not r or r.empresa_id != ctx.empresa_id or r.unidade_id != unidade_id:
        raise HTTPException(422, "Recurso inválido para esta unidade.")


def _espacos_da_unidade(ctx: Ctx, campos: dict, unidade_id: int) -> None:
    for k in ("espaco_origem_id", "espaco_destino_id"):
        if campos.get(k) is not None:
            e = ctx.db.get(Espaco, campos[k])
            if not e or e.empresa_id != ctx.empresa_id or e.unidade_id != unidade_id:
                raise HTTPException(422, "Espaço inválido para esta unidade.")


def _etapa(ctx: Ctx, eid: int) -> tuple[Etapa, Processo]:
    e = ctx.obter_filho(Etapa, eid, Processo, "processo_id")
    return e, e.processo


def _operacao(ctx: Ctx, oid: int) -> tuple[Operacao, Etapa, Processo]:
    op = ctx.db.get(Operacao, oid)
    if not op or op.empresa_id != ctx.empresa_id:
        raise HTTPException(404, "Registro não encontrado.")
    e, p = _etapa(ctx, op.etapa_id)
    return op, e, p


# ------------------------------------------------------------------ processos
@router.get("/processos", response_model=list[ProcessoOut])
def listar_processos(ctx: Ctx = Depends(get_ctx), unidade_id: int | None = None, status: str | None = None,
                     limite: int = Query(100, ge=1, le=200), deslocamento: int = Query(0, ge=0)):
    q = ctx.query(Processo)
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        q = q.where(Processo.unidade_id == unidade_id)
    if status:
        q = q.where(Processo.status == status)
    ps = ctx.db.scalars(q.order_by(Processo.nome, Processo.versao.desc()).limit(limite).offset(deslocamento))
    return [processo_out(p, detalhado=False) for p in ps]


@router.post("/processos", response_model=ProcessoOut, status_code=201)
def criar_processo(dados: ProcessoIn, ctx: Ctx = Depends(requer_gestor)):
    ctx.exige_unidade(dados.unidade_id)
    p = Processo(empresa_id=ctx.empresa_id, codigo=str(uuid.uuid4()), versao=1, status="rascunho",
                 criado_por=ctx.usuario.id, **dados.model_dump())
    ctx.db.add(p)
    ctx.db.flush()
    ctx.auditar("processo.criar", "processo", p.id, None, audit.snap(p))
    ctx.db.commit()
    return processo_out(p)


@router.get("/processos/{pid}", response_model=ProcessoOut)
def obter_processo(pid: int, ctx: Ctx = Depends(get_ctx)):
    return processo_out(ctx.obter(Processo, pid))


@router.patch("/processos/{pid}", response_model=ProcessoOut)
def atualizar_processo(pid: int, dados: ProcessoUpdate, ctx: Ctx = Depends(requer_gestor)):
    p = ctx.obter(Processo, pid)
    _rascunho(p)
    antes = audit.snap(p)
    for k, v in dados.model_dump(exclude_unset=True).items():
        if v is not None or k == "responsavel_id":
            setattr(p, k, v)
    ctx.auditar("processo.atualizar", "processo", p.id, antes, audit.snap(p))
    ctx.db.commit()
    return processo_out(p)


@router.post("/processos/{pid}/nova-versao", response_model=ProcessoOut, status_code=201)
def nova_versao(pid: int, ctx: Ctx = Depends(requer_gestor)):
    origem = ctx.obter(Processo, pid)
    if origem.status == "rascunho":
        raise HTTPException(409, "Este processo já é um rascunho.")
    if ctx.db.scalar(select(Processo.id).where(Processo.empresa_id == ctx.empresa_id,
                                               Processo.codigo == origem.codigo, Processo.status == "rascunho")):
        raise HTTPException(409, "Já existe um rascunho desta versão em andamento.")
    ultima = ctx.db.scalar(select(func.max(Processo.versao)).where(
        Processo.empresa_id == ctx.empresa_id, Processo.codigo == origem.codigo))
    novo = Processo(empresa_id=ctx.empresa_id, unidade_id=origem.unidade_id, codigo=origem.codigo,
                    versao=ultima + 1, nome=origem.nome, macroprocesso=origem.macroprocesso,
                    descricao=origem.descricao, status="rascunho", responsavel_id=origem.responsavel_id,
                    origem=origem.origem, criado_por=ctx.usuario.id)
    ctx.db.add(novo)
    ctx.db.flush()
    for e in origem.etapas:
        ne = Etapa(empresa_id=ctx.empresa_id, processo_id=novo.id, sequencia=e.sequencia, nome=e.nome,
                   descricao=e.descricao, entradas=list(e.entradas), saidas=list(e.saidas),
                   opcional=e.opcional, condicao=e.condicao)
        ctx.db.add(ne)
        ctx.db.flush()
        for op in e.operacoes:
            nop = Operacao(empresa_id=ctx.empresa_id, etapa_id=ne.id, sequencia=op.sequencia, nome=op.nome,
                           descricao=op.descricao, formula_tipo=op.formula_tipo, unidade_medida=op.unidade_medida,
                           recurso_padrao_id=op.recurso_padrao_id, dados_medidos=list(op.dados_medidos),
                           campos_extras=list(op.campos_extras), ergonomia=dict(op.ergonomia),
                           funcao_requerida=op.funcao_requerida, num_pessoas=op.num_pessoas,
                           espaco_origem_id=op.espaco_origem_id, espaco_destino_id=op.espaco_destino_id,
                           distancia_m=op.distancia_m, item_peso_kg=op.item_peso_kg,
                           item_comprimento_m=op.item_comprimento_m, item_largura_m=op.item_largura_m,
                           item_altura_m=op.item_altura_m, inicio_marco=op.inicio_marco, fim_marco=op.fim_marco)
            ctx.db.add(nop)
            ctx.db.flush()
            from ..services.modelo_tempo import modelo_ativo
            mt = modelo_ativo(ctx.db, ctx.empresa_id, op.id)
            if mt:
                ctx.db.add(ModeloTempo(
                    empresa_id=ctx.empresa_id, unidade_id=novo.unidade_id, operacao_id=nop.id, versao=1,
                    elementos=list(mt.elementos), fator_ambiente=mt.fator_ambiente, premissas=list(mt.premissas),
                    dados_faltantes=list(mt.dados_faltantes), padrao_apontamento=dict(mt.padrao_apontamento),
                    confianca=mt.confianca, justificativa=mt.justificativa, origem=mt.origem, provedor=mt.provedor,
                    status_validacao=mt.status_validacao, contexto=dict(mt.contexto), criado_por=ctx.usuario.id,
                    validado_por=mt.validado_por, validado_em=mt.validado_em))
            for pr in estimativa.parametros_vigentes(ctx.db, ctx.empresa_id, "operacao", op.id).values():
                ctx.db.add(Parametro(
                    empresa_id=ctx.empresa_id, unidade_id=novo.unidade_id, escopo_tipo="operacao",
                    escopo_id=nop.id, nome=pr.nome, valor_num=pr.valor_num, valor_texto=pr.valor_texto,
                    unidade=pr.unidade, origem=pr.origem, status_validacao="validado", versao=1, vigente=True,
                    justificativa=f"Copiado da versão {origem.versao} do processo.",
                    criado_por=ctx.usuario.id, validado_por=pr.validado_por, validado_em=pr.validado_em))
    ctx.db.flush()
    ctx.auditar("processo.nova_versao", "processo", novo.id, {"origem_id": origem.id}, audit.snap(novo))
    ctx.db.commit()
    return processo_out(novo)


@router.post("/processos/{pid}/publicar", response_model=ProcessoOut)
def publicar(pid: int, ctx: Ctx = Depends(requer_gestor)):
    p = ctx.obter(Processo, pid)
    _rascunho(p)
    if not p.etapas:
        raise HTTPException(422, "O processo precisa ter ao menos uma etapa.")
    vazias = [e.nome for e in p.etapas if not e.operacoes]
    if vazias:
        raise HTTPException(422, "Etapas sem operação: " + ", ".join(vazias))
    avisos = []
    for e in p.etapas:
        for op in e.operacoes:
            if "tempo_unitario_min" not in estimativa.parametros_vigentes(ctx.db, ctx.empresa_id, "operacao", op.id):
                avisos.append(f"'{op.nome}' sem tempo unitário validado: a estimativa dependerá do histórico.")
    anterior = ctx.db.scalars(select(Processo).where(
        Processo.empresa_id == ctx.empresa_id, Processo.codigo == p.codigo, Processo.status == "ativo"))
    for a in anterior:
        a.status = "substituido"
    p.status, p.publicado_em, p.publicado_por = "ativo", datetime.now(timezone.utc), ctx.usuario.id
    ctx.auditar("processo.publicar", "processo", p.id, None, {"versao": p.versao, "avisos": avisos})
    ctx.db.commit()
    return processo_out(p, avisos=avisos)


@router.post("/processos/{pid}/arquivar", response_model=ProcessoOut)
def arquivar(pid: int, ctx: Ctx = Depends(requer_gestor)):
    p = ctx.obter(Processo, pid)
    antes = p.status
    p.status = "arquivado"
    ctx.auditar("processo.arquivar", "processo", p.id, {"status": antes}, {"status": p.status})
    ctx.db.commit()
    return processo_out(p, detalhado=False)


# ------------------------------------------------------------------ etapas
@router.post("/processos/{pid}/etapas", response_model=EtapaOut, status_code=201)
def criar_etapa(pid: int, dados: EtapaIn, ctx: Ctx = Depends(requer_gestor)):
    p = ctx.obter(Processo, pid)
    _rascunho(p)
    campos = dados.model_dump()
    seq = campos.pop("sequencia")
    e = Etapa(empresa_id=ctx.empresa_id, processo_id=p.id, sequencia=0, **campos)
    ctx.db.add(e)
    ctx.db.flush()
    ctx.db.refresh(p)
    _renumerar(list(p.etapas), mover=e, para=seq)
    ctx.auditar("etapa.criar", "etapa", e.id, None, audit.snap(e))
    ctx.db.commit()
    return etapa_out(e)


@router.patch("/etapas/{eid}", response_model=EtapaOut)
def atualizar_etapa(eid: int, dados: EtapaUpdate, ctx: Ctx = Depends(requer_gestor)):
    e, p = _etapa(ctx, eid)
    _rascunho(p)
    antes = audit.snap(e)
    campos = dados.model_dump(exclude_unset=True)
    seq = campos.pop("sequencia", None)
    for k, v in campos.items():
        if v is not None:
            setattr(e, k, v)
    if seq is not None:
        _renumerar(list(p.etapas), mover=e, para=seq)
    ctx.auditar("etapa.atualizar", "etapa", e.id, antes, audit.snap(e))
    ctx.db.commit()
    return etapa_out(e)


@router.delete("/etapas/{eid}", status_code=204)
def remover_etapa(eid: int, ctx: Ctx = Depends(requer_gestor)):
    e, p = _etapa(ctx, eid)
    _rascunho(p)
    antes = audit.snap(e)
    for op in list(e.operacoes):
        _apagar_parametros_op(ctx, op.id)
    ctx.db.delete(e)
    ctx.db.flush()
    ctx.db.refresh(p)
    _renumerar(list(p.etapas))
    ctx.auditar("etapa.remover", "etapa", eid, antes, None)
    ctx.db.commit()


# ------------------------------------------------------------------ operações
def _campos_operacao(dados) -> dict:
    campos = dados.model_dump(exclude_unset=True)
    if "ergonomia" in campos and dados.ergonomia is not None:
        campos["ergonomia"] = dados.ergonomia.model_dump(exclude_none=True)
    if "campos_extras" in campos and dados.campos_extras is not None:
        campos["campos_extras"] = [c.model_dump() for c in dados.campos_extras]
    return campos


@router.post("/etapas/{eid}/operacoes", response_model=OperacaoOut, status_code=201)
def criar_operacao(eid: int, dados: OperacaoIn, ctx: Ctx = Depends(requer_gestor)):
    e, p = _etapa(ctx, eid)
    _rascunho(p)
    campos = _campos_operacao(dados)
    _recurso_da_unidade(ctx, campos.get("recurso_padrao_id"), p.unidade_id)
    _espacos_da_unidade(ctx, campos, p.unidade_id)
    seq = campos.pop("sequencia", None)
    op = Operacao(empresa_id=ctx.empresa_id, etapa_id=e.id, sequencia=0, **campos)
    ctx.db.add(op)
    ctx.db.flush()
    ctx.db.refresh(e)
    _renumerar(list(e.operacoes), mover=op, para=seq)
    ctx.auditar("operacao.criar", "operacao", op.id, None, audit.snap(op))
    ctx.db.commit()
    return op_out(op)


@router.patch("/operacoes/{oid}", response_model=OperacaoOut)
def atualizar_operacao(oid: int, dados: OperacaoUpdate, ctx: Ctx = Depends(requer_gestor)):
    op, e, p = _operacao(ctx, oid)
    _rascunho(p)
    campos = _campos_operacao(dados)
    _recurso_da_unidade(ctx, campos.get("recurso_padrao_id"), p.unidade_id)
    _espacos_da_unidade(ctx, campos, p.unidade_id)
    antes = audit.snap(op)
    seq = campos.pop("sequencia", None)
    anulaveis = ("recurso_padrao_id", "espaco_origem_id", "espaco_destino_id", "distancia_m", "item_peso_kg",
                 "item_comprimento_m", "item_largura_m", "item_altura_m")
    for k, v in campos.items():
        if v is not None or k in anulaveis:
            setattr(op, k, v)
    if seq is not None:
        _renumerar(list(e.operacoes), mover=op, para=seq)
    ctx.auditar("operacao.atualizar", "operacao", op.id, antes, audit.snap(op))
    ctx.db.commit()
    return op_out(op)


def _apagar_parametros_op(ctx: Ctx, oid: int) -> None:
    for pr in ctx.db.scalars(select(Parametro).where(
            Parametro.empresa_id == ctx.empresa_id, Parametro.escopo_tipo == "operacao", Parametro.escopo_id == oid)):
        ctx.db.delete(pr)


@router.delete("/operacoes/{oid}", status_code=204)
def remover_operacao(oid: int, ctx: Ctx = Depends(requer_gestor)):
    op, e, p = _operacao(ctx, oid)
    _rascunho(p)
    antes = audit.snap(op)
    _apagar_parametros_op(ctx, op.id)
    ctx.db.delete(op)
    ctx.db.flush()
    ctx.db.refresh(e)
    _renumerar(list(e.operacoes))
    ctx.auditar("operacao.remover", "operacao", oid, antes, None)
    ctx.db.commit()


# ------------------------------------------------------------------ parâmetros
def _unidade_do_escopo(ctx: Ctx, tipo: str, id_: int) -> int:
    if tipo == "operacao":
        _, _, p = _operacao(ctx, id_)
        return p.unidade_id
    if tipo == "processo":
        return ctx.obter(Processo, id_).unidade_id
    return ctx.obter(Recurso, id_).unidade_id


@router.get("/parametros", response_model=list[ParametroOut])
def listar_parametros(escopo_tipo: str, escopo_id: int, historico: bool = False, ctx: Ctx = Depends(get_ctx)):
    _unidade_do_escopo(ctx, escopo_tipo, escopo_id)
    q = select(Parametro).where(Parametro.empresa_id == ctx.empresa_id, Parametro.escopo_tipo == escopo_tipo,
                                Parametro.escopo_id == escopo_id)
    if not historico:
        q = q.where((Parametro.vigente.is_(True)) | (Parametro.status_validacao == "pendente"))
    return ctx.db.scalars(q.order_by(Parametro.nome, Parametro.versao.desc())).all()


def _nova_versao_parametro(ctx: Ctx, uni: int, dados: dict, *, origem: str, status: str,
                           vigente: bool) -> Parametro:
    ultima = ctx.db.scalar(select(func.max(Parametro.versao)).where(
        Parametro.empresa_id == ctx.empresa_id, Parametro.escopo_tipo == dados["escopo_tipo"],
        Parametro.escopo_id == dados["escopo_id"], Parametro.nome == dados["nome"])) or 0
    if vigente:
        for ant in ctx.db.scalars(select(Parametro).where(
                Parametro.empresa_id == ctx.empresa_id, Parametro.escopo_tipo == dados["escopo_tipo"],
                Parametro.escopo_id == dados["escopo_id"], Parametro.nome == dados["nome"],
                Parametro.vigente.is_(True))):
            ant.vigente = False
    p = Parametro(empresa_id=ctx.empresa_id, unidade_id=uni, versao=ultima + 1, origem=origem,
                  status_validacao=status, vigente=vigente, criado_por=ctx.usuario.id,
                  validado_por=ctx.usuario.id if status == "validado" else None,
                  validado_em=datetime.now(timezone.utc) if status == "validado" else None, **dados)
    ctx.db.add(p)
    ctx.db.flush()
    return p


@router.post("/parametros", response_model=ParametroOut, status_code=201)
def criar_parametro(dados: ParametroIn, ctx: Ctx = Depends(requer_gestor)):
    """Cria nova versão do parâmetro. Valor informado/medido por um gestor já nasce validado."""
    uni = _unidade_do_escopo(ctx, dados.escopo_tipo, dados.escopo_id)
    if dados.valor_num is None and dados.valor_texto is None:
        raise HTTPException(422, "Informe valor_num ou valor_texto.")
    campos = dados.model_dump(exclude={"origem"})
    if not campos["unidade"] and campos["nome"] in PARAMETROS_PADRAO:
        campos["unidade"] = PARAMETROS_PADRAO[campos["nome"]][0]
    p = _nova_versao_parametro(ctx, uni, campos, origem=dados.origem, status="validado", vigente=True)
    ctx.auditar("parametro.criar", "parametro", p.id, None, audit.snap(p))
    ctx.db.commit()
    return p


def _param(ctx: Ctx, pid: int) -> Parametro:
    p = ctx.obter(Parametro, pid)
    return p


@router.post("/parametros/{pid}/validar", response_model=ParametroOut)
def validar_parametro(pid: int, dados: DecisaoIn, ctx: Ctx = Depends(requer_gestor)):
    p = _param(ctx, pid)
    if p.status_validacao != "pendente":
        raise HTTPException(409, "Parâmetro já decidido.")
    if p.valor_num is None and p.valor_texto is None:
        raise HTTPException(422, "Sugestão sem valor: informe o valor medido criando uma nova versão do parâmetro.")
    antes = audit.snap(p)
    for ant in ctx.db.scalars(select(Parametro).where(
            Parametro.empresa_id == ctx.empresa_id, Parametro.escopo_tipo == p.escopo_tipo,
            Parametro.escopo_id == p.escopo_id, Parametro.nome == p.nome, Parametro.vigente.is_(True))):
        ant.vigente = False
    p.status_validacao, p.vigente = "validado", True
    p.validado_por, p.validado_em = ctx.usuario.id, datetime.now(timezone.utc)
    if dados.observacao:
        p.justificativa = (p.justificativa + "\n" if p.justificativa else "") + f"Validação: {dados.observacao}"
    ctx.auditar("parametro.validar", "parametro", p.id, antes, audit.snap(p))
    ctx.db.commit()
    return p


@router.post("/parametros/{pid}/rejeitar", response_model=ParametroOut)
def rejeitar_parametro(pid: int, dados: DecisaoIn, ctx: Ctx = Depends(requer_gestor)):
    p = _param(ctx, pid)
    if p.status_validacao != "pendente":
        raise HTTPException(409, "Parâmetro já decidido.")
    antes = audit.snap(p)
    p.status_validacao, p.vigente = "rejeitado", False
    p.validado_por, p.validado_em = ctx.usuario.id, datetime.now(timezone.utc)
    ctx.auditar("parametro.rejeitar", "parametro", p.id, antes, audit.snap(p))
    ctx.db.commit()
    return p


@router.post("/operacoes/{oid}/parametros/atualizar-historico", response_model=list[ParametroOut])
def atualizar_parametros_do_historico(oid: int, ctx: Ctx = Depends(requer_gestor)):
    """Recalcula tempos da operação a partir do histórico APROVADO e grava como nova versão
    (origem 'calculado'), validada pelo gestor que executou a ação."""
    op, _, p = _operacao(ctx, oid)
    from ..config import get_settings
    minimo = get_settings().min_amostras_historico
    params = estimativa.parametros_vigentes(ctx.db, ctx.empresa_id, "operacao", op.id)
    lote = params["tamanho_lote"].valor_num if "tamanho_lote" in params else None
    amostras, preps = estimativa.historico_operacao(ctx.db, ctx.empresa_id, op.id, op.formula_tipo, lote)
    criados = []
    if len(amostras) < minimo:
        raise HTTPException(409, f"Histórico aprovado insuficiente ({len(amostras)}/{minimo} amostras).")
    novos = [("tempo_unitario_min", timecalc.mediana(amostras), "min/un", len(amostras))]
    if len(preps) >= minimo:
        novos.append(("tempo_preparacao_min", timecalc.mediana(preps), "min", len(preps)))
    for nome, valor, un, n in novos:
        atual = params.get(nome)
        if atual and atual.valor_num is not None and abs(atual.valor_num - valor) < 1e-9:
            continue
        pr = _nova_versao_parametro(
            ctx, p.unidade_id,
            {"escopo_tipo": "operacao", "escopo_id": op.id, "nome": nome, "valor_num": round(valor, 4),
             "valor_texto": None, "unidade": un,
             "justificativa": f"Mediana de {n} amostras aprovadas do histórico."},
            origem="calculado", status="validado", vigente=True)
        ctx.auditar("parametro.atualizar_historico", "parametro", pr.id, audit.snap(atual) if atual else None,
                    audit.snap(pr))
        criados.append(pr)
    ctx.db.commit()
    return criados
