"""Decomposição do erro entre atividades (e entre PREPARO e EXECUÇÃO) a partir de pedidos medidos só no total.

Quando o dono mede o pedido inteiro ("Comecei / Terminei"), o total é repartido pelo previsto e todas as atividades recebem o mesmo
erro. Mas pedidos com COMPOSIÇÕES diferentes (mais corte em um, mais montagem em outro, lotes maiores ou menores) carregam a
informação de onde está o erro. Modelo, por pedido o:

    realizado_o ≈ Σ_j k_j · previsto_oj        j = (atividade, preparo | execução)

estimado por mínimos quadrados PONDERADOS (peso 1 ÷ previsto_o², para o erro ser relativo e pedidos grandes não dominarem) com
REGULARIZAÇÃO em direção ao padrão (ridge com prior k = 1; Hoerl e Kennard, 1970):

    min Σ_o w_o (y_o − Σ_j x_oj k_j)² + λ Σ_j S_j (k_j − 1)²,   S_j = média_o(w_o x_oj²),  λ = nº de "pedidos fictícios" no padrão

Para uma coluna isolada isso dá k_j = 1 + Z·(k̂_j − 1) com Z = n ÷ (n + λ): a mesma forma da credibilidade de Bühlmann. Com poucos
pedidos o fator fica perto do padrão; com muitos, segue os dados. Fatores limitados a 0,5–2,0. Antes, pedidos absurdos saem pelo
identificador de Hampel (sobre realizado ÷ previsto do pedido).

Uma coluna só é IDENTIFICÁVEL se a sua parcela no previsto varia entre os pedidos (coeficiente de variação ≥ 0,10), não anda junto
com outra coluna (correlação das parcelas < 0,98: por exemplo, as execuções de várias atividades que crescem todas com a quantidade
são colineares e viram um GRUPO com fator único) e há pelo menos 4 pedidos. O que não se separa não é inventado: recebe o fator do
grupo e fica marcado como não identificável.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Apontamento, Ordem, OrdemOperacao
from . import calibracao_modulos, timecalc

LAMBDA = 1.0  # força do prior: equivale a 1 pedido "no padrão"
COLINEAR = 0.98  # colunas cujas parcelas andam juntas (correlação ≥ 0,98) não se separam: dividem um só fator
MIN_PEDIDOS = 4
CV_MIN = 0.10
FATOR_MIN, FATOR_MAX = 0.5, 2.0


@dataclass
class Coluna:
    modulo: str
    parte: str  # preparo | execucao
    fator: float
    peso_dos_dados: float  # Z aproximado = n ÷ (n + λ) ajustado pela informação da coluna
    identificavel: bool
    parcela_media_pct: float
    grupo: tuple = ()  # colunas colineares que dividem este fator (vazio = coluna sozinha)


def _resolver(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Gauss com pivotamento parcial (sistemas pequenos: até ~20 colunas)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def pedidos_da_unidade(db: Session, empresa_id: int, unidade_id: int) -> list[tuple[dict, float]]:
    """[(previsto por (atividade, parte), realizado corrido)] dos pedidos concluídos com tempo aprovado."""
    ordens = list(db.scalars(select(Ordem).where(Ordem.empresa_id == empresa_id, Ordem.unidade_id == unidade_id,
                                                 Ordem.status == "concluida")))
    if not ordens:
        return []
    apts = list(db.scalars(select(Apontamento).where(
        Apontamento.empresa_id == empresa_id, Apontamento.ordem_id.in_([o.id for o in ordens]), Apontamento.status == "aprovado",
        Apontamento.anulado.is_(False), Apontamento.fim.is_not(None), Apontamento.tipo.in_(("execucao", "preparacao")))))
    por_ordem: dict[int, list] = {}
    for a in apts:
        por_ordem.setdefault(a.ordem_id, []).append(a)
    out = []
    for o in ordens:
        lista = por_ordem.get(o.id)
        if not lista:
            continue
        x: dict[tuple[str, str], float] = {}
        for oo in o.operacoes:
            if not oo.modulo or not oo.previsto_normal_min:
                continue
            p, e = oo.tempo_prep_est_min or 0.0, oo.tempo_exec_est_min or 0.0
            fp = p / (p + e) if p + e > 0 else 0.0  # parcela do preparo no previsto da etapa
            if fp > 0:
                x[(oo.modulo, "preparo")] = x.get((oo.modulo, "preparo"), 0.0) + oo.previsto_normal_min * fp
            x[(oo.modulo, "execucao")] = x.get((oo.modulo, "execucao"), 0.0) + oo.previsto_normal_min * (1 - fp)
        real = timecalc.uniao_minutos((a.inicio, a.fim) for a in lista)
        if x and real > 0:
            out.append((x, real))
    return out


def estimar(pedidos: list[tuple[dict, float]], lam: float = LAMBDA) -> list[Coluna]:
    if len(pedidos) < 2:
        return []
    mantidos, _ = calibracao_modulos.hampel([y / sum(x.values()) for x, y in pedidos])
    pedidos = [pedidos[i] for i in mantidos]
    colunas = sorted({k for x, _ in pedidos for k in x})
    n, p = len(pedidos), len(colunas)
    if n < 2 or p == 0:
        return []
    Xc = [[x.get(c, 0.0) for c in colunas] for x, _ in pedidos]
    tot = [sum(r) or 1.0 for r in Xc]
    parc = [[Xc[o][j] / tot[o] for o in range(n)] for j in range(p)]

    def corr(u, v):
        mu, mv = sum(u) / n, sum(v) / n
        su = math.sqrt(sum((a - mu) ** 2 for a in u)); sv = math.sqrt(sum((b - mv) ** 2 for b in v))
        return None if su < 1e-12 or sv < 1e-12 else sum((a - mu) * (b - mv) for a, b in zip(u, v)) / (su * sv)

    # agrupa colunas colineares (union-find): andam juntas, então só o fator do grupo é estimável
    pai = list(range(p))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for i in range(p):
        for j in range(i + 1, p):
            c = corr(parc[i], parc[j])
            if c is None or c >= COLINEAR:
                pai[raiz(i)] = raiz(j)
    grupos: dict[int, list[int]] = {}
    for j in range(p):
        grupos.setdefault(raiz(j), []).append(j)
    gl = list(grupos.values())
    g = len(gl)
    w = [1.0 / t ** 2 for t in tot]
    X = [[sum(Xc[o][j] for j in membros) for membros in gl] for o in range(n)]
    y = [yy for _, yy in pedidos]
    S = [sum(w[o] * X[o][j] ** 2 for o in range(n)) / n for j in range(g)]
    A = [[sum(w[o] * X[o][i] * X[o][j] for o in range(n)) + (lam * S[i] if i == j else 0.0) for j in range(g)] for i in range(g)]
    b = [sum(w[o] * X[o][i] * y[o] for o in range(n)) + lam * S[i] for i in range(g)]
    k = _resolver(A, b)
    if k is None:
        return []
    out = []
    for gi, membros in enumerate(gl):
        info = n * S[gi]
        z = info / (info + lam * S[gi]) if S[gi] > 0 else 0.0
        nomes = tuple(f"{colunas[j][0]}:{colunas[j][1]}" for j in membros) if len(membros) > 1 else ()
        for j in membros:
            media = sum(parc[j]) / n
            cv = math.sqrt(sum((v - media) ** 2 for v in parc[j]) / n) / media if media > 0 else 0.0
            mod, parte = colunas[j]
            out.append(Coluna(mod, parte, round(min(max(k[gi], FATOR_MIN), FATOR_MAX), 4), round(z, 3),
                              n >= MIN_PEDIDOS and cv >= CV_MIN and len(membros) == 1, round(media * 100, 1), nomes))
    return sorted(out, key=lambda c: (c.modulo, c.parte))


def da_unidade(db: Session, empresa_id: int, unidade_id: int) -> list[Coluna]:
    return estimar(pedidos_da_unidade(db, empresa_id, unidade_id))


def fator_da_atividade(colunas: list[Coluna], modulo: str) -> float | None:
    """Fator único da atividade (preparo e execução ponderados pela parcela média), se ao menos uma parte for identificável."""
    cs = [c for c in colunas if c.modulo == modulo]
    if not cs or not any(c.identificavel for c in cs):  # ao menos uma parte separável (as demais usam o fator do seu grupo)
        return None
    peso = sum(c.parcela_media_pct for c in cs) or 1.0
    return round(sum(c.fator * c.parcela_media_pct for c in cs) / peso, 4)


__all__ = ["Coluna", "estimar", "da_unidade", "fator_da_atividade", "OrdemOperacao"]
