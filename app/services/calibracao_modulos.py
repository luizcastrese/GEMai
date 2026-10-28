"""Calibração por MÓDULO: fator multiplicativo = mediana(tempo normal observado ÷ tempo normal previsto).

- amostra = uma operação concluída (ordem não cancelada) que tem módulo e previsão; o tempo observado é o dos apontamentos
  APROVADOS e não anulados de preparação + execução, normalizado POR APONTAMENTO pelo ritmo de quem executou (só na fração
  do tempo que depende do operador, como no histórico normalizado); a previsão é a do módulo em ritmo 100 e SEM fator
  de calibração (para não calibrar sobre a própria calibração);
- por (unidade, módulo): fator = mediana das razões, com ≥ `min_amostras_calibracao` amostras, limitado a 0,5–2,0;
- a prévia não grava; registrar cria uma proposta PENDENTE; só uma pessoa a valida (validado + vigente) e só a validada
  entra no cálculo, rotulada `calibrado` com o nº de amostras;
- é um fator do MÓDULO, nunca de uma pessoa (o ritmo individual só normaliza o observado).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Apontamento, CalibracaoModulo, Ordem, OrdemOperacao
from . import ritmo, timecalc
from .modulos import catalogo

FATOR_MIN, FATOR_MAX = 0.5, 2.0


@dataclass
class Sugestao:
    unidade_id: int
    modulo: str
    amostras: int
    minimo: int
    mediana_bruta: float | None
    fator: float | None
    limitado: bool
    status: str  # sugerido | insuficiente


def razoes(db: Session, empresa_id: int, unidade_ids: list[int]) -> dict[tuple[int, str], list[float]]:
    """{(unidade_id, módulo): [observado normal ÷ previsto, …]} das operações concluídas com módulo e previsão."""
    if not unidade_ids:
        return {}
    rows = db.execute(
        select(OrdemOperacao, Ordem.unidade_id).join(Ordem, Ordem.id == OrdemOperacao.ordem_id).where(
            OrdemOperacao.empresa_id == empresa_id, OrdemOperacao.status == "concluida", OrdemOperacao.modulo.is_not(None),
            OrdemOperacao.previsto_normal_min > 0, Ordem.status != "cancelada", Ordem.unidade_id.in_(unidade_ids))).all()
    if not rows:
        return {}
    por_oo = {oo.id: (oo, uid) for oo, uid in rows}
    apts = list(db.scalars(select(Apontamento).where(
        Apontamento.empresa_id == empresa_id, Apontamento.ordem_operacao_id.in_(por_oo), Apontamento.status == "aprovado",
        Apontamento.anulado.is_(False), Apontamento.fim.is_not(None), Apontamento.tipo.in_(("execucao", "preparacao")))))
    ritmos = ritmo.ritmos_das_pessoas(db, empresa_id, {a.pessoa_id for a in apts if a.pessoa_id})
    observado: dict[int, float] = {}
    for a in apts:
        oo, _ = por_oo[a.ordem_operacao_id]
        f = oo.fracao_operador if oo.fracao_operador is not None else 1.0
        r = ritmos.get(a.pessoa_id)
        rit = r.valor / 100.0 if r is not None and r.conhecido else 1.0
        d = timecalc.duracao_min(a.inicio, a.fim) or 0.0
        observado[oo.id] = observado.get(oo.id, 0.0) + d * (f * rit + (1.0 - f))
    out: dict[tuple[int, str], list[float]] = {}
    for oo_id, obs in observado.items():
        if obs <= 0:
            continue
        oo, uid = por_oo[oo_id]
        out.setdefault((uid, oo.modulo), []).append(obs / oo.previsto_normal_min)
    return out


def previa(db: Session, empresa_id: int, unidade_ids: list[int]) -> list[Sugestao]:
    minimo = max(get_settings().min_amostras_calibracao, 1)
    sugestoes = []
    for (uid, modulo), xs in sorted(razoes(db, empresa_id, unidade_ids).items()):
        if modulo not in catalogo.CATALOGO:
            continue
        if len(xs) < minimo:
            sugestoes.append(Sugestao(uid, modulo, len(xs), minimo, None, None, False, "insuficiente"))
            continue
        bruta = timecalc.mediana(xs)
        fator = min(max(bruta, FATOR_MIN), FATOR_MAX)
        sugestoes.append(Sugestao(uid, modulo, len(xs), minimo, round(bruta, 4), round(fator, 4), fator != bruta, "sugerido"))
    return sugestoes


def fator_vigente(db: Session, empresa_id: int, unidade_id: int | None, modulo: str) -> CalibracaoModulo | None:
    """Calibração VALIDADA e vigente do módulo na unidade (None = sem calibração: fator 1, coeficientes genéricos)."""
    if unidade_id is None:
        return None
    return db.scalar(select(CalibracaoModulo).where(
        CalibracaoModulo.empresa_id == empresa_id, CalibracaoModulo.unidade_id == unidade_id, CalibracaoModulo.modulo == modulo,
        CalibracaoModulo.vigente.is_(True), CalibracaoModulo.status == "validado"))


def como_dict(c: CalibracaoModulo | None) -> dict | None:
    return None if c is None else {"fator": c.fator, "amostras": c.amostras, "versao": c.versao}
