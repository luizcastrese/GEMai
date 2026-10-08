"""Aplica uma proposta de estrutura (aprovada por humano) ao ERP.

Tudo o que nasce aqui é marcado com origem 'ia'; processos entram como RASCUNHO e os
parâmetros como 'ia_sugerido/pendente' (não entram em cálculos até serem validados).
"""
from __future__ import annotations

import re
import unicodedata
import uuid

from sqlalchemy import select

from .. import audit
from ..deps import Ctx
from ..models import Etapa, Material, Operacao, Parametro, Processo, Recurso, RecomendacaoIA
from .ia.esquemas import EstruturaProposta


def _chave(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode().strip()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", _chave(s)).strip("_")[:80] or "parametro"


def aplicar(ctx: Ctx, rec: RecomendacaoIA, est: EstruturaProposta) -> dict:
    uid = rec.unidade_id
    recursos = {_chave(r.nome): r for r in ctx.db.scalars(
        select(Recurso).where(Recurso.empresa_id == ctx.empresa_id, Recurso.unidade_id == uid))}
    materiais = {_chave(m.nome) for m in ctx.db.scalars(select(Material).where(Material.empresa_id == ctx.empresa_id))}
    cont = {"processos": 0, "etapas": 0, "operacoes": 0, "parametros": 0, "recursos": 0, "materiais": 0}

    def recurso(nome: str, tipo: str = "maquina") -> Recurso:
        k = _chave(nome)
        if k not in recursos:
            r = Recurso(empresa_id=ctx.empresa_id, unidade_id=uid, nome=nome, tipo=tipo, origem="ia")
            ctx.db.add(r)
            ctx.db.flush()
            recursos[k] = r
            cont["recursos"] += 1
            ctx.auditar("recurso.criar_por_ia", "recurso", r.id, None, audit.snap(r))
        return recursos[k]

    for r in est.recursos:
        recurso(r.nome, r.tipo)
    for m in est.materiais:
        if _chave(m.nome) not in materiais:
            obj = Material(empresa_id=ctx.empresa_id, nome=m.nome, unidade_medida=m.unidade_medida, origem="ia")
            ctx.db.add(obj)
            ctx.db.flush()
            materiais.add(_chave(m.nome))
            cont["materiais"] += 1
            ctx.auditar("material.criar_por_ia", "material", obj.id, None, audit.snap(obj))

    for pi in est.processos:
        p = Processo(empresa_id=ctx.empresa_id, unidade_id=uid, codigo=str(uuid.uuid4()), versao=1, nome=pi.nome,
                     macroprocesso=pi.macroprocesso, descricao=pi.descricao, status="rascunho", origem="ia",
                     recomendacao_id=rec.id, criado_por=ctx.usuario.id)
        ctx.db.add(p)
        ctx.db.flush()
        cont["processos"] += 1
        for i, ei in enumerate(pi.etapas, 1):
            e = Etapa(empresa_id=ctx.empresa_id, processo_id=p.id, sequencia=i, nome=ei.nome, descricao=ei.descricao,
                      entradas=ei.entradas, saidas=ei.saidas, opcional=ei.opcional, condicao=ei.condicao)
            ctx.db.add(e)
            ctx.db.flush()
            cont["etapas"] += 1
            for j, oi in enumerate(ei.operacoes, 1):
                op = Operacao(empresa_id=ctx.empresa_id, etapa_id=e.id, sequencia=j, nome=oi.nome,
                              descricao=oi.descricao, formula_tipo=oi.formula_tipo, unidade_medida=oi.unidade_medida,
                              dados_medidos=oi.dados_medidos or ["tempo", "quantidade"],
                              recurso_padrao_id=recurso(oi.recurso).id if oi.recurso else None)
                ctx.db.add(op)
                ctx.db.flush()
                cont["operacoes"] += 1
                for pa in oi.parametros:
                    ctx.db.add(Parametro(
                        empresa_id=ctx.empresa_id, unidade_id=uid, escopo_tipo="operacao", escopo_id=op.id,
                        nome=_slug(pa.nome), valor_num=pa.valor, unidade=pa.unidade, origem="ia_sugerido",
                        status_validacao="pendente", versao=1, vigente=False, justificativa=pa.justificativa,
                        recomendacao_id=rec.id, criado_por=ctx.usuario.id))
                    cont["parametros"] += 1
        ctx.auditar("processo.criar_por_ia", "processo", p.id, None, audit.snap(p))
    ctx.db.flush()
    return cont
