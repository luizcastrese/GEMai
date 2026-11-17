"""Calibração por MÓDULO: fator multiplicativo = mediana(tempo normal observado ÷ tempo normal previsto).

- amostra = uma operação concluída (ordem não cancelada) que tem módulo e previsão; o tempo observado é o dos apontamentos
  APROVADOS e não anulados de preparação + execução, normalizado POR APONTAMENTO pelo ritmo de quem executou (só na fração
  do tempo que depende do operador, como no histórico normalizado); a previsão é a do módulo em ritmo 100 e SEM fator
  de calibração (para não calibrar sobre a própria calibração);
- por (unidade, módulo): fator = mediana das razões, com ≥ `min_amostras_calibracao` amostras, limitado a 0,5–2,0;
- a prévia não grava; registrar cria uma proposta PENDENTE; só uma pessoa a valida (validado + vigente) e só a validada
  entra no cálculo, rotulada `calibrado` com o nº de amostras;
- é um fator do MÓDULO, nunca de uma pessoa (o ritmo individual só normaliza o observado).

Família (produto × módulo): pedidos do mesmo produto com dimensões diferentes têm o MESMO núcleo de cálculo, mas o erro do
módulo pode crescer (ou encolher) com o tamanho. Por isso, além do fator geral, cada produto com amostras suficientes
ganha um fator que ESCALA com o porte do pedido, aprendido dos pedidos já feitos (os maiores informam os menores):
- porte = tempo normal previsto POR UNIDADE do pedido (já deriva das medidas pelas fórmulas das peças; nada extra a informar);
- ajuste robusto (Theil–Sen) de ln(razão) contra ln(porte): expoente `b` e fator no porte de referência (mediana dos portes);
  fator(porte) = fator_ref × (porte ÷ porte_ref)^b, limitado a 0,5–2,0; b limitado a −0,5…1,0;
- exige ≥ `min_amostras_familia` amostras, ≥ 3 tamanhos distintos e dispersão de porte ≥ 1,25×; senão não há como aprender a
  escala e vale o fator geral do módulo;
- fora do intervalo observado (±50 %) o porte é travado na borda e o resultado é rotulado "extrapolado";
- precedência no cálculo: família validada do produto > fator geral validado do módulo > nada (coeficientes genéricos).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Apontamento, CalibracaoModulo, Ordem, OrdemOperacao
from . import ritmo, timecalc
from .modulos import catalogo

FATOR_MIN, FATOR_MAX = 0.5, 2.0
EXPOENTE_MIN, EXPOENTE_MAX = -0.5, 1.0
MIN_TAMANHOS = 3        # tamanhos distintos (portes que diferem > 5 %) para enxergar uma escala
MIN_DISPERSAO = 1.25    # maior porte ÷ menor porte
FOLGA_EXTRAPOLACAO = 1.5  # além do intervalo observado ×1,5 o porte é travado na borda


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
    produto_id: int | None = None  # None = geral do módulo; com produto = família (escala com o porte)
    expoente: float = 0.0
    porte_ref: float | None = None
    porte_min: float | None = None
    porte_max: float | None = None


@dataclass
class Amostra:
    unidade_id: int
    modulo: str
    produto_id: int | None
    porte: float | None  # tempo normal previsto por unidade do pedido
    razao: float  # tempo normal observado ÷ previsto


def amostras(db: Session, empresa_id: int, unidade_ids: list[int]) -> list[Amostra]:
    """Uma amostra por operação concluída com módulo e previsão: razão (observado normal ÷ previsto) e o porte do pedido."""
    if not unidade_ids:
        return []
    rows = db.execute(
        select(OrdemOperacao, Ordem.unidade_id, Ordem.produto_id, Ordem.quantidade).join(Ordem, Ordem.id == OrdemOperacao.ordem_id).where(
            OrdemOperacao.empresa_id == empresa_id, OrdemOperacao.status == "concluida", OrdemOperacao.modulo.is_not(None),
            OrdemOperacao.previsto_normal_min > 0, Ordem.status != "cancelada", Ordem.unidade_id.in_(unidade_ids))).all()
    if not rows:
        return []
    por_oo = {oo.id: (oo, uid, pid, qtd) for oo, uid, pid, qtd in rows}
    apts = list(db.scalars(select(Apontamento).where(
        Apontamento.empresa_id == empresa_id, Apontamento.ordem_operacao_id.in_(por_oo), Apontamento.status == "aprovado",
        Apontamento.anulado.is_(False), Apontamento.fim.is_not(None), Apontamento.tipo.in_(("execucao", "preparacao")))))
    ritmos = ritmo.ritmos_das_pessoas(db, empresa_id, {a.pessoa_id for a in apts if a.pessoa_id})
    observado: dict[int, float] = {}
    for a in apts:
        oo = por_oo[a.ordem_operacao_id][0]
        f = oo.fracao_operador if oo.fracao_operador is not None else 1.0
        r = ritmos.get(a.pessoa_id)
        rit = r.valor / 100.0 if r is not None and r.conhecido else 1.0
        d = timecalc.duracao_min(a.inicio, a.fim) or 0.0
        observado[oo.id] = observado.get(oo.id, 0.0) + d * (f * rit + (1.0 - f))
    out: list[Amostra] = []
    for oo_id, obs in observado.items():
        if obs <= 0:
            continue
        oo, uid, pid, qtd = por_oo[oo_id]
        porte = oo.previsto_normal_min / qtd if qtd and qtd > 0 else None
        out.append(Amostra(uid, oo.modulo, pid, porte, obs / oo.previsto_normal_min))
    return out


def razoes(db: Session, empresa_id: int, unidade_ids: list[int]) -> dict[tuple[int, str], list[float]]:
    """{(unidade_id, módulo): [observado normal ÷ previsto, …]} das operações concluídas com módulo e previsão (todos os produtos)."""
    out: dict[tuple[int, str], list[float]] = {}
    for a in amostras(db, empresa_id, unidade_ids):
        out.setdefault((a.unidade_id, a.modulo), []).append(a.razao)
    return out


@dataclass
class Familia:
    fator: float  # no porte de referência, já limitado
    bruto: float
    limitado: bool
    expoente: float
    porte_ref: float
    porte_min: float
    porte_max: float


def ajustar_familia(pares: list[tuple[float, float]]) -> Familia | None:
    """pares = [(porte, razão)]. None quando não há como aprender a escala (poucos tamanhos ou pouca dispersão)."""
    pares = [(x, r) for x, r in pares if x and x > 0 and r and r > 0]
    if len(pares) < 2:
        return None
    lx = [math.log(x) for x, _ in pares]
    lr = [math.log(r) for _, r in pares]
    if len({round(v / 0.05) for v in lx}) < MIN_TAMANHOS or max(lx) - min(lx) < math.log(MIN_DISPERSAO):
        return None
    inclinacoes = [(lr[j] - lr[i]) / (lx[j] - lx[i]) for i in range(len(pares)) for j in range(i + 1, len(pares))
                   if abs(lx[j] - lx[i]) >= 0.05]
    if not inclinacoes:
        return None
    b = min(max(timecalc.mediana(inclinacoes), EXPOENTE_MIN), EXPOENTE_MAX)
    if abs(b) * (max(lx) - min(lx)) < 0.05:  # a escala quase não muda o fator na faixa observada: vale uma constante
        b = 0.0
    ref = timecalc.mediana([x for x, _ in pares])
    bruto = math.exp(timecalc.mediana([lr[i] - b * (lx[i] - math.log(ref)) for i in range(len(pares))]))
    fator = min(max(bruto, FATOR_MIN), FATOR_MAX)
    return Familia(round(fator, 4), round(bruto, 4), fator != bruto, round(b, 4), round(ref, 4),
                   round(min(x for x, _ in pares), 4), round(max(x for x, _ in pares), 4))


def previa(db: Session, empresa_id: int, unidade_ids: list[int]) -> list[Sugestao]:
    """Sugestões gerais (por módulo) e por família (produto × módulo). Não grava."""
    cfg = get_settings()
    minimo, min_fam = max(cfg.min_amostras_calibracao, 1), max(cfg.min_amostras_familia, 2)
    todas = [a for a in amostras(db, empresa_id, unidade_ids) if a.modulo in catalogo.CATALOGO]
    gerais: dict[tuple[int, str], list[float]] = {}
    familias: dict[tuple[int, str, int], list[Amostra]] = {}
    for a in todas:
        gerais.setdefault((a.unidade_id, a.modulo), []).append(a.razao)
        if a.produto_id is not None:
            familias.setdefault((a.unidade_id, a.modulo, a.produto_id), []).append(a)
    sugestoes = []
    for (uid, modulo), xs in sorted(gerais.items()):
        if len(xs) < minimo:
            sugestoes.append(Sugestao(uid, modulo, len(xs), minimo, None, None, False, "insuficiente"))
            continue
        bruta = timecalc.mediana(xs)
        fator = min(max(bruta, FATOR_MIN), FATOR_MAX)
        sugestoes.append(Sugestao(uid, modulo, len(xs), minimo, round(bruta, 4), round(fator, 4), fator != bruta, "sugerido"))
    for (uid, modulo, pid), am in sorted(familias.items()):
        fam = ajustar_familia([(a.porte, a.razao) for a in am if a.porte]) if len(am) >= min_fam else None
        if fam is None:
            sugestoes.append(Sugestao(uid, modulo, len(am), min_fam, None, None, False, "insuficiente", produto_id=pid))
        else:
            sugestoes.append(Sugestao(uid, modulo, len(am), min_fam, fam.bruto, fam.fator, fam.limitado, "sugerido", produto_id=pid,
                                      expoente=fam.expoente, porte_ref=fam.porte_ref, porte_min=fam.porte_min, porte_max=fam.porte_max))
    return sugestoes


def vigente_exato(db: Session, empresa_id: int, unidade_id: int | None, modulo: str, produto_id: int | None = None) -> CalibracaoModulo | None:
    """Calibração VALIDADA e vigente exatamente desta chave (produto_id None = fator geral do módulo)."""
    if unidade_id is None:
        return None
    return db.scalar(select(CalibracaoModulo).where(
        CalibracaoModulo.empresa_id == empresa_id, CalibracaoModulo.unidade_id == unidade_id, CalibracaoModulo.modulo == modulo,
        CalibracaoModulo.produto_id.is_(None) if produto_id is None else CalibracaoModulo.produto_id == produto_id,
        CalibracaoModulo.vigente.is_(True), CalibracaoModulo.status == "validado"))


def fator_vigente(db: Session, empresa_id: int, unidade_id: int | None, modulo: str, produto_id: int | None = None) -> CalibracaoModulo | None:
    """Calibração a usar: a da FAMÍLIA (produto) se validada; senão o fator geral do módulo; senão None (fator 1, coeficientes genéricos)."""
    if produto_id is not None:
        fam = vigente_exato(db, empresa_id, unidade_id, modulo, produto_id)
        if fam is not None:
            return fam
    return vigente_exato(db, empresa_id, unidade_id, modulo)


def fator_para(c: CalibracaoModulo, porte: float | None) -> tuple[float, bool]:
    """(fator efetivo, extrapolou?) para o porte do pedido. Geral ou família sem escala: o fator fixo."""
    if c.produto_id is None or not c.expoente or porte is None or porte <= 0 or not c.porte_ref or not c.porte_min or not c.porte_max:
        return c.fator, False
    x = min(max(porte, c.porte_min / FOLGA_EXTRAPOLACAO), c.porte_max * FOLGA_EXTRAPOLACAO)
    k = c.fator * (x / c.porte_ref) ** c.expoente
    return min(max(k, FATOR_MIN), FATOR_MAX), (porte < c.porte_min or porte > c.porte_max)


def como_dict(c: CalibracaoModulo | None, porte: float | None = None) -> dict | None:
    if c is None:
        return None
    k, extra = fator_para(c, porte)
    d = {"fator": k, "amostras": c.amostras, "versao": c.versao}
    if c.produto_id is not None:
        d["fonte"] = (f"Calibração validada da família: {c.amostras} amostras aprovadas deste produto"
                      + (f", escala com o porte (expoente {c.expoente:g})" if c.expoente else "") + f" (v{c.versao})"
                      + ("; porte fora do já observado: fator travado na borda (extrapolado)" if extra else ""))
        d["extrapolado"] = extra
    return d
