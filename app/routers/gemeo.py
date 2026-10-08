"""Gêmeo digital: modelo de tempo por operação (IA propõe, sistema calcula), simulação e prontidão."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, select

from .. import audit
from ..deps import Ctx, get_ctx, requer_gestor
from ..models import Espaco, ModeloTempo, PerfilMaoDeObra, Processo, Produto, Recurso
from ..ratelimit import limite_ia
from ..schemas import DecisaoIn, EstimativaOut, ModeloTempoManualIn, ModeloTempoOut
from ..services import ergonomia, estimativa, ia, modelo_tempo, prontidao
from ..services.dashboard import alerta_ergonomia
from ..services.modelo_tempo import ModeloTempoIA, sanear_modelo
from .processos import _operacao

router = APIRouter(tags=["gemeo-digital"])


def _esp(db, id_):
    e = db.get(Espaco, id_) if id_ else None
    if not e:
        return None
    return {"nome": e.nome, "tipo": e.tipo, "comprimento_m": e.comprimento_m, "largura_m": e.largura_m,
            "pe_direito_m": e.pe_direito_m, "piso": e.piso, "temperatura_c": e.temperatura_c,
            "umidade_pct": e.umidade_pct, "ruido_db": e.ruido_db, "iluminancia_lux": e.iluminancia_lux}


def contexto_ia(ctx: Ctx, op, etapa, proc) -> dict:
    """Retrato do contorno físico enviado à IA (sem dados pessoais)."""
    rec = ctx.db.get(Recurso, op.recurso_padrao_id) if op.recurso_padrao_id else None
    c = modelo_tempo.montar_contexto(ctx.db, ctx.empresa_id, op, 1.0, None, rec)
    perfil = ctx.db.get(PerfilMaoDeObra, op.perfil_id) if op.perfil_id else None
    espacos = [ctx.db.get(Espaco, i) for i in (op.espaco_origem_id, op.espaco_destino_id) if i]
    erg = ergonomia.avaliar_operacao(op, perfil, espacos, c.peso_kg)
    return {
        "segmento": ctx.empresa.segmento, "processo": proc.nome, "etapa": etapa.nome,
        "operacao": {"nome": op.nome, "descricao": op.descricao, "unidade_medida": op.unidade_medida,
                     "funcao_requerida": op.funcao_requerida, "num_pessoas": op.num_pessoas,
                     "inicio_marco": op.inicio_marco, "fim_marco": op.fim_marco, "ergonomia": op.ergonomia,
                     "dados_medidos": op.dados_medidos, "tipo_movimento": op.tipo_movimento,
                     "postura_trabalho": op.postura_trabalho, "altura_trabalho_m": op.altura_trabalho_m,
                     "gasto_energetico_kcal_min": op.gasto_energetico_kcal_min},
        # Perfil de REFERÊNCIA (não é uma pessoa). Sexo/estatura/peso corporal servem só a limites de carga.
        "perfil": ({"nome": perfil.nome, "sexo": perfil.sexo, "estatura_cm": perfil.estatura_cm,
                    "peso_corporal_kg": perfil.peso_corporal_kg, "faixa_etaria": perfil.faixa_etaria,
                    "experiencia": perfil.experiencia, "ritmo_pct": perfil.ritmo_pct} if perfil else None),
        "ergonomia_calculada": erg,
        "recurso": ({"nome": rec.nome, "tipo": rec.tipo, "capacidade": rec.capacidade,
                     "capacidade_unidade": rec.capacidade_unidade, "capacidade_un_h": c.capacidade_un_h} if rec else None),
        "espaco_origem": _esp(ctx.db, op.espaco_origem_id), "espaco_destino": _esp(ctx.db, op.espaco_destino_id),
        "distancia_m": c.distancia_m,
        "item": {"peso_kg": c.peso_kg, "comprimento_m": c.comprimento_m, "largura_m": c.largura_m, "altura_m": c.altura_m},
    }


def _gravar(ctx: Ctx, op, proc, m: ModeloTempoIA, *, origem: str, status: str, provedor: str = "",
            contexto: dict | None = None, justificativa_extra: str = "") -> ModeloTempo:
    versao = (ctx.db.scalar(select(func.max(ModeloTempo.versao)).where(
        ModeloTempo.empresa_id == ctx.empresa_id, ModeloTempo.operacao_id == op.id)) or 0) + 1
    mt = ModeloTempo(
        empresa_id=ctx.empresa_id, unidade_id=proc.unidade_id, operacao_id=op.id, versao=versao,
        elementos=[e.model_dump() for e in m.elementos], fator_ambiente=m.fator_ambiente, premissas=m.premissas,
        ritmo_pct=m.ritmo_pct, tolerancias=[t.model_dump() for t in m.tolerancias],
        dados_faltantes=m.dados_faltantes, confianca=m.confianca, origem=origem, provedor=provedor,
        status_validacao=status, contexto=contexto or {}, criado_por=ctx.usuario.id,
        justificativa=(m.justificativa + (" " + justificativa_extra if justificativa_extra else "")).strip(),
        padrao_apontamento={"inicio": m.padrao_apontamento_inicio, "fim": m.padrao_apontamento_fim,
                            "unidade_contagem": m.unidade_contagem},
        validado_por=ctx.usuario.id if status == "validado" else None,
        validado_em=datetime.now(timezone.utc) if status == "validado" else None)
    ctx.db.add(mt)
    ctx.db.flush()
    return mt


def _gerar(ctx: Ctx, op, etapa, proc) -> ModeloTempo:
    limite_ia.checar(str(ctx.empresa_id))
    contexto = contexto_ia(ctx, op, etapa, proc)
    m, prov, aviso = ia.modelar_tempo(ctx.empresa, contexto)
    mt = _gravar(ctx, op, proc, m, origem="ia", status="pendente", provedor=prov, contexto=contexto, justificativa_extra=aviso)
    ctx.auditar("modelo_tempo.gerar", "modelo_tempo", mt.id, None, {"operacao_id": op.id, "provedor": prov,
                                                                      "elementos": len(mt.elementos), "confianca": mt.confianca})
    return mt


@router.post("/operacoes/{oid}/modelo-tempo/gerar", response_model=ModeloTempoOut, status_code=201)
def gerar_modelo(oid: int, ctx: Ctx = Depends(requer_gestor)):
    op, etapa, proc = _operacao(ctx, oid)
    mt = _gerar(ctx, op, etapa, proc)
    ctx.db.commit()
    return mt


@router.post("/processos/{pid}/modelar-tempos", response_model=list[ModeloTempoOut], status_code=201)
def modelar_processo(pid: int, refazer: bool = False, ctx: Ctx = Depends(requer_gestor)):
    """Gera modelos de tempo (IA) para as operações do processo que ainda não têm um."""
    proc = ctx.obter(Processo, pid)
    criados = []
    for e in proc.etapas:
        for op in e.operacoes:
            if refazer or modelo_tempo.modelo_ativo(ctx.db, ctx.empresa_id, op.id) is None:
                criados.append(_gerar(ctx, op, e, proc))
    ctx.db.commit()
    return criados


@router.post("/operacoes/{oid}/modelo-tempo", response_model=ModeloTempoOut, status_code=201)
def modelo_manual(oid: int, dados: ModeloTempoManualIn, ctx: Ctx = Depends(requer_gestor)):
    """Modelo definido por uma pessoa (nasce validado). Mesmo vocabulário fechado de métodos."""
    op, _, proc = _operacao(ctx, oid)
    try:
        m = sanear_modelo(ModeloTempoIA.model_validate({
            "elementos": dados.elementos, "fator_ambiente": dados.fator_ambiente, "ritmo_pct": dados.ritmo_pct,
            "tolerancias": dados.tolerancias, "premissas": dados.premissas,
            "justificativa": dados.justificativa, "confianca": "alta"}))
    except ValidationError as e:
        raise HTTPException(422, f"Elemento inválido: {e.errors()[0]['loc']} {e.errors()[0]['msg']}")
    if not m.elementos:
        raise HTTPException(422, "Informe ao menos um elemento.")
    mt = _gravar(ctx, op, proc, m, origem="manual", status="validado")
    ctx.auditar("modelo_tempo.manual", "modelo_tempo", mt.id, None, {"operacao_id": op.id})
    ctx.db.commit()
    return mt


@router.get("/operacoes/{oid}/modelo-tempo", response_model=list[ModeloTempoOut])
def listar_modelos(oid: int, ctx: Ctx = Depends(get_ctx)):
    _operacao(ctx, oid)
    return ctx.db.scalars(select(ModeloTempo).where(ModeloTempo.empresa_id == ctx.empresa_id, ModeloTempo.operacao_id == oid)
                          .order_by(ModeloTempo.versao.desc())).all()


def _decidir(ctx: Ctx, mid: int, status: str, obs: str) -> ModeloTempo:
    mt = ctx.obter(ModeloTempo, mid)
    if mt.status_validacao != "pendente":
        raise HTTPException(409, "Este modelo já foi decidido.")
    antes = audit.snap(mt)
    mt.status_validacao, mt.validado_por, mt.validado_em = status, ctx.usuario.id, datetime.now(timezone.utc)
    if obs:
        mt.justificativa = (mt.justificativa + f"\n[{status}] {obs}").strip()
    ctx.auditar(f"modelo_tempo.{status}", "modelo_tempo", mt.id, {"status": antes["status_validacao"]}, {"status": status})
    return mt


@router.post("/modelos-tempo/{mid}/validar", response_model=ModeloTempoOut)
def validar_modelo(mid: int, dados: DecisaoIn, ctx: Ctx = Depends(requer_gestor)):
    mt = _decidir(ctx, mid, "validado", dados.observacao)
    ctx.db.commit()
    return mt


@router.post("/modelos-tempo/{mid}/rejeitar", response_model=ModeloTempoOut)
def rejeitar_modelo(mid: int, dados: DecisaoIn, ctx: Ctx = Depends(requer_gestor)):
    mt = _decidir(ctx, mid, "rejeitado", dados.observacao)
    ctx.db.commit()
    return mt


@router.get("/operacoes/{oid}/estimativa", response_model=EstimativaOut)
def simular(oid: int, quantidade: float = Query(1, gt=0, le=1e9), produto_id: int | None = None,
            ctx: Ctx = Depends(get_ctx)):
    """Simulação (what-if): tempo planejado desta operação para uma quantidade e produto."""
    op, _, _ = _operacao(ctx, oid)
    prod = None
    if produto_id is not None:
        prod = ctx.db.get(Produto, produto_id)
        if not prod or prod.empresa_id != ctx.empresa_id:
            raise HTTPException(404, "Registro não encontrado.")
    est = estimativa.estimar_operacao(ctx.db, ctx.empresa_id, op, quantidade, prod)
    total = None if est.exec is None else round((est.prep or 0) + est.exec, 2)
    return EstimativaOut(fonte=est.fonte, validada=est.validada, quantidade=quantidade,
                         preparacao_min=None if est.exec is None else round(est.prep or 0, 2),
                         execucao_min=None if est.exec is None else round(est.exec, 2), total_min=total,
                         elementos=est.detalhe, avisos=est.avisos)


@router.get("/processos/{pid}/prontidao")
def prontidao_processo(pid: int, ctx: Ctx = Depends(get_ctx)):
    return prontidao.avaliar(ctx.db, ctx.empresa_id, ctx.obter(Processo, pid))


@router.get("/operacoes/{oid}/ergonomia")
def ergonomia_operacao(oid: int, ctx: Ctx = Depends(get_ctx)):
    """Triagem ergonômica (NIOSH, limites legais de carga, Murrell, ruído). Não substitui a AET (NR-17)."""
    op, _, _ = _operacao(ctx, oid)
    perfil = ctx.db.get(PerfilMaoDeObra, op.perfil_id) if op.perfil_id else None
    espacos = [ctx.db.get(Espaco, i) for i in (op.espaco_origem_id, op.espaco_destino_id) if i]
    return ergonomia.avaliar_operacao(op, perfil, espacos, op.item_peso_kg)
