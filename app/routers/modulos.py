"""Módulos da EMPRESA: atividades delimitadas por necessidade (a IA propõe, uma pessoa valida) sobre arquétipos de cálculo.

Fluxo: descrever a atividade → a IA (ou a regra local) propõe a especificação (arquétipo, driver, parâmetro técnico, ações por
categoria) → fica PENDENTE → uma pessoa revisa/edita e VALIDA → o módulo entra no catálogo da empresa (planos, operações e
calibração). Nenhum campo é minuto digitado; o sistema calcula.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .. import audit
from ..deps import Ctx, get_ctx
from ..models import ModuloEmpresa
from ..ratelimit import limite_ia
from ..schemas import In
from ..services import ia
from ..services.modulos import arquetipos, catalogo
from ..services.modulos.base import EntradaModulo
from ..services.modulos.motor import calcular_modulo

router = APIRouter(tags=["modulos"])


class ProporModuloIn(In):
    nome: Annotated[str, Field(min_length=2, max_length=120)]
    descricao: Annotated[str, Field(max_length=2000)] = ""


class EspecIn(In):
    espec: dict


class DecisaoModuloIn(In):
    observacao: Annotated[str, Field(max_length=1000)] = ""


class ModuloEmpresaOut(BaseModel):
    id: int
    chave: str
    titulo: str
    arquetipo: str
    versao: int
    status: str
    vigente: bool
    origem: str
    provedor: str
    justificativa: str
    espec: dict
    problemas: list[str] = []
    dados_faltantes: list[str] = []
    aviso: str = ""
    exemplo: dict | None = None  # cálculo de demonstração com uma peça de referência (só para conferência)


def _problemas(espec: dict) -> list[str]:
    try:
        return arquetipos.EspecModulo.model_validate(espec).problemas()
    except Exception as exc:
        return [f"especificação inválida: {str(exc)[:300]}"]


def _exemplo(espec: dict) -> dict | None:
    """Demonstração: uma peça de 1,0 × 0,5 m, 5 kg, ficha com o MEIO da faixa plausível. Não grava; só mostra a composição."""
    try:
        e = arquetipos.EspecModulo.model_validate(espec)
    except Exception:
        return None
    if e.arquetipo == "deslocamento":
        return None
    ficha = {e.taxa.nome: (e.taxa.minimo * e.taxa.maximo) ** 0.5} if e.taxa else {}
    peca = {"nome": "Peça de referência", "qtd": 1.0, "comp": 1.0, "larg": 0.5, "esp": 0.02, "peso_kg": 5.0, "furos": 0, "bordas_m": 3.0,
            "atributos": {}}
    ent = EntradaModulo(quantidade=1.0, unidades_produto=1.0, componentes=[peca], recurso_nome="Equipamento de referência" if e.taxa else None,
                        ficha=ficha)
    r = calcular_modulo(arquetipos.construir(e), ent)
    return {"peca": "1,0 × 0,5 × 0,02 m, 5 kg (só para conferência)", "ficha": ficha, "tempo_padrao_min": r.total,
            "composicao": r.composicao, "faltantes": r.faltantes, "premissas": r.premissas,
            "aviso": "Exemplo ilustrativo com valores do meio da faixa plausível; o plano usa a ficha validada do seu equipamento."}


def _out(m: ModuloEmpresa, **kw) -> ModuloEmpresaOut:
    return ModuloEmpresaOut(id=m.id, chave=m.chave, titulo=m.titulo, arquetipo=m.arquetipo, versao=m.versao, status=m.status, vigente=m.vigente,
                            origem=m.origem, provedor=m.provedor, justificativa=m.justificativa, espec=m.espec,
                            problemas=_problemas(m.espec), exemplo=_exemplo(m.espec), **kw)


def _chave_livre(ctx: Ctx, base: str) -> str:
    """Chave para a atividade: reaproveita a da empresa (nova versão) e nunca colide com um módulo embutido."""
    chave = base if base not in catalogo.CATALOGO else f"x_{base}"[:30]
    return chave


def _gravar(ctx: Ctx, espec: dict, origem: str, provedor: str = "", justificativa: str = "") -> ModuloEmpresa:
    ultima = ctx.db.scalar(select(func.max(ModuloEmpresa.versao)).where(ModuloEmpresa.empresa_id == ctx.empresa_id,
                                                                         ModuloEmpresa.chave == espec["chave"])) or 0
    for p in ctx.db.scalars(select(ModuloEmpresa).where(ModuloEmpresa.empresa_id == ctx.empresa_id, ModuloEmpresa.chave == espec["chave"],
                                                         ModuloEmpresa.status == "pendente")):
        p.status = "rejeitado"  # a proposta nova substitui a pendente anterior
    m = ModuloEmpresa(empresa_id=ctx.empresa_id, chave=espec["chave"], titulo=espec["titulo"], arquetipo=espec["arquetipo"], espec=espec,
                      versao=ultima + 1, status="pendente", vigente=False, origem=origem, provedor=provedor, justificativa=justificativa,
                      criado_por=ctx.usuario.id)
    ctx.db.add(m)
    ctx.db.flush()
    ctx.auditar("modulo_empresa.propor", "modulo_empresa", m.id, None, audit.snap(m))
    return m


@router.get("/modulos/vocabulario")
def vocabulario(ctx: Ctx = Depends(get_ctx)):
    """Arquétipos e categorias que a IA e a pessoa podem escolher (nenhum minuto)."""
    return arquetipos.vocabulario()


@router.get("/modulos/empresa", response_model=list[ModuloEmpresaOut])
def listar(ctx: Ctx = Depends(get_ctx)):
    """Última versão de cada módulo da empresa (validado, pendente ou rejeitado) e a vigente, se houver."""
    rows = list(ctx.db.scalars(select(ModuloEmpresa).where(ModuloEmpresa.empresa_id == ctx.empresa_id)
                               .order_by(ModuloEmpresa.chave, ModuloEmpresa.versao)))
    ultimas: dict[str, ModuloEmpresa] = {}
    vigentes = {r.chave: r for r in rows if r.vigente}
    for r in rows:
        ultimas[r.chave] = r
    out = []
    for chave, r in ultimas.items():
        out.append(_out(r))
        if chave in vigentes and vigentes[chave].id != r.id:
            out.append(_out(vigentes[chave]))
    return out


@router.post("/modulos/propor", response_model=ModuloEmpresaOut, status_code=201)
def propor(dados: ProporModuloIn, ctx: Ctx = Depends(get_ctx)):
    """A IA DELIMITA a atividade como módulo (arquétipo + driver + parâmetro técnico + ações por categoria). Fica pendente."""
    limite_ia.checar(f"{ctx.empresa_id}")
    chave = _chave_livre(ctx, arquetipos.slug(dados.nome))
    contexto = {"nome": dados.nome, "descricao": dados.descricao, "segmento": ctx.empresa.segmento, "vocabulario": arquetipos.vocabulario(),
                "modulos_existentes": [{"chave": m["chave"], "titulo": m["titulo"]} for m in catalogo.resumo_para_ia(ctx.db, ctx.empresa_id)]}
    espec, problemas, bruto, prov, aviso = ia.propor_modulo(ctx.empresa, contexto, chave)
    if espec is None:
        raise HTTPException(422, "Não foi possível delimitar a atividade: " + "; ".join(problemas))
    falta = list(bruto.dados_faltantes or [])
    just = (bruto.justificativa or "") + (("\nPara o tempo ficar bom: " + "; ".join(falta)) if falta else "")
    m = _gravar(ctx, espec, "ia", prov, just.strip())
    ctx.db.commit()
    return _out(m, dados_faltantes=list(bruto.dados_faltantes or []), aviso=aviso)


@router.post("/modulos/empresa", response_model=ModuloEmpresaOut, status_code=201)
def criar(dados: EspecIn, ctx: Ctx = Depends(get_ctx)):
    """Cria (ou revisa, com a mesma chave) a especificação de um módulo. Nasce pendente: só vale depois de validada."""
    espec = dict(dados.espec)
    espec["chave"] = _chave_livre(ctx, espec.get("chave") or arquetipos.slug(espec.get("titulo", "")))
    try:
        e = arquetipos.EspecModulo.model_validate(espec)
    except Exception as exc:
        raise HTTPException(422, f"Especificação inválida: {str(exc)[:400]}")
    m = _gravar(ctx, e.model_dump(), "manual")
    ctx.db.commit()
    return _out(m)


def _pendente(ctx: Ctx, mid: int) -> ModuloEmpresa:
    m = ctx.obter(ModuloEmpresa, mid)
    if m.status != "pendente":
        raise HTTPException(409, "Só uma proposta pendente pode ser validada ou rejeitada.")
    return m


@router.post("/modulos/empresa/{mid}/validar", response_model=ModuloEmpresaOut)
def validar(mid: int, dados: DecisaoModuloIn, ctx: Ctx = Depends(get_ctx)):
    """Uma pessoa revisa e valida: o módulo passa a valer no catálogo da empresa (a versão anterior deixa de ser vigente)."""
    m = _pendente(ctx, mid)
    probl = _problemas(m.espec)
    if probl:
        raise HTTPException(422, "Corrija antes de validar: " + "; ".join(probl))
    antes = audit.snap(m)
    for v in ctx.db.scalars(select(ModuloEmpresa).where(ModuloEmpresa.empresa_id == ctx.empresa_id, ModuloEmpresa.chave == m.chave,
                                                         ModuloEmpresa.vigente.is_(True))):
        v.vigente = False
    m.status, m.vigente, m.validado_por, m.validado_em = "validado", True, ctx.usuario.id, datetime.now(timezone.utc)
    if dados.observacao:
        m.justificativa = (m.justificativa + "\nValidação: " + dados.observacao).strip()
    ctx.auditar("modulo_empresa.validar", "modulo_empresa", m.id, antes, audit.snap(m))
    ctx.db.commit()
    return _out(m)


@router.post("/modulos/empresa/{mid}/rejeitar", response_model=ModuloEmpresaOut)
def rejeitar(mid: int, dados: DecisaoModuloIn, ctx: Ctx = Depends(get_ctx)):
    m = _pendente(ctx, mid)
    antes = audit.snap(m)
    m.status = "rejeitado"
    if dados.observacao:
        m.justificativa = (m.justificativa + "\nRejeição: " + dados.observacao).strip()
    ctx.auditar("modulo_empresa.rejeitar", "modulo_empresa", m.id, antes, audit.snap(m))
    ctx.db.commit()
    return _out(m)
