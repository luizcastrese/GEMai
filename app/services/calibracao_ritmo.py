"""Calibração do ritmo individual pela equipe a partir do histórico aprovado.

IMPORTANTE — o que o número significa: é um ritmo RELATIVO À EQUIPE (a mediana da equipe vale 100). NÃO é uma
avaliação de ritmo no sentido OIT/Barnes (comparação com o ritmo normal de um operador qualificado, feita por
observação cronometrada). Uma equipe inteira lenta ou rápida ainda resulta em ritmos próximos de 100. O valor serve
só para normalizar o histórico de tempos (`estimativa`); não é ranking nem avaliação da pessoa (dado de desempenho:
LGPD, finalidade e minimização).

Método (só apontamentos de execução aprovados e não anulados):
- operação elegível: ≥ `min_amostras_historico` amostras e ≥ 2 pessoas distintas executando (com uma só pessoa a
  razão seria 1 por construção e não diz nada); referência = mediana dos tempos por unidade (mesma lógica de
  `estimativa.amostras_do_historico`, sem normalizar);
- por pessoa e operação com ≥ `min_amostras_ritmo` amostras próprias: razão = referência ÷ mediana da pessoa
  (mais rápida que a equipe ⇒ razão > 1);
- ritmo sugerido = mediana das razões × 100, limitado a 50–150, exigindo ≥ `min_operacoes_ritmo` operações
  distintas (com 1 operação o resultado depende de uma só tarefa; 2 ou mais é mais robusto).
Operações e histórico são limitados às unidades do escopo (a unidade escolhida ou as que o usuário acessa).
A referência inclui as amostras da própria pessoa; com equipes pequenas isso aproxima a razão de 1.
Quando duas pessoas dividem a mesma ordem_operacao em operações de fórmula `fixo`/`lote`, o tempo de cada uma é
parcial e a razão subestima o ritmo de quem trabalhou menos tempo na ordem.

O serviço apenas SUGERE; quem grava (`aplicar`) é o endpoint, com auditoria, e ritmo `informado` nunca é
sobrescrito.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Operacao, Ordem, OrdemOperacao, Pessoa
from . import estimativa, timecalc
from .modelo_tempo import RITMO_MAX, RITMO_MIN

AVISO = ("Ritmo RELATIVO À EQUIPE (a mediana da equipe vale 100), calculado do histórico aprovado. Não é avaliação "
         "de ritmo no sentido OIT e não deve ser usado para ranquear ou avaliar pessoas; serve só para normalizar "
         "tempos observados. O sistema sugere; uma pessoa confirma.")


@dataclass
class SugestaoPessoa:
    pessoa: Pessoa
    status: str  # sugerido | mantido | insuficiente
    ritmo_sugerido: float | None = None
    operacoes: int = 0
    amostras: int = 0
    motivo: str = ""


@dataclass
class Calibracao:
    pessoas: list[SugestaoPessoa] = field(default_factory=list)
    operacoes_consideradas: int = 0
    operacoes_ignoradas: list[str] = field(default_factory=list)


def calibrar(db: Session, empresa_id: int, pessoas: list[Pessoa], unidade_ids: set[int] | None = None) -> Calibracao:
    """`unidade_ids` limita as operações e o histórico às unidades que o usuário pode ver (None = empresa toda)."""
    s = get_settings()
    alvo = {p.id: p for p in pessoas}
    razoes: dict[int, list[float]] = {i: [] for i in alvo}
    amostras: dict[int, int] = {i: 0 for i in alvo}
    out = Calibracao()

    q = (select(OrdemOperacao.operacao_id).join(Ordem, Ordem.id == OrdemOperacao.ordem_id)
         .where(OrdemOperacao.empresa_id == empresa_id, OrdemOperacao.status == "concluida",
                OrdemOperacao.operacao_id.is_not(None)).distinct())
    if unidade_ids is not None:
        q = q.where(Ordem.unidade_id.in_(unidade_ids or {-1}))
    op_ids = [i for (i,) in db.execute(q)]
    for op_id in sorted(op_ids):
        op = db.get(Operacao, op_id)
        if op is None or op.empresa_id != empresa_id:
            continue
        params = estimativa.parametros_vigentes(db, empresa_id, "operacao", op.id)
        lote = params["tamanho_lote"].valor_num if "tamanho_lote" in params else None
        h = estimativa.carregar_historico(db, empresa_id, op.id, unidade_ids)
        execucoes = [r for r in h.registros if r.tipo == "execucao"]
        ref_amostras, _ = estimativa.amostras_do_historico(execucoes, h.plano, op.formula_tipo, lote)
        if len(ref_amostras) < s.min_amostras_historico:
            continue
        if len({r.pessoa_id for r in execucoes if r.pessoa_id}) < 2:
            out.operacoes_ignoradas.append(f"{op.nome}: só uma pessoa (ou nenhuma) identificada; sem comparação possível.")
            continue
        referencia = timecalc.mediana(ref_amostras)
        out.operacoes_consideradas += 1
        for pid in alvo:
            proprios = [r for r in execucoes if r.pessoa_id == pid]
            am, _ = estimativa.amostras_do_historico(proprios, h.plano, op.formula_tipo, lote)
            if len(am) >= s.min_amostras_ritmo:
                razoes[pid].append(referencia / timecalc.mediana(am))
                amostras[pid] += len(am)

    for p in sorted(pessoas, key=lambda x: (x.nome.lower(), x.id)):  # ordem alfabética: nada de ranking por ritmo
        n = len(razoes[p.id])
        sug = None
        if n >= max(s.min_operacoes_ritmo, 1):
            sug = round(min(max(timecalc.mediana(razoes[p.id]) * 100.0, RITMO_MIN), RITMO_MAX), 1)
        if p.ritmo_origem == "informado":
            out.pessoas.append(SugestaoPessoa(p, "mantido", sug, n, amostras[p.id],
                                              "Ritmo informado manualmente: a calibração não o sobrescreve."))
        elif sug is not None:
            out.pessoas.append(SugestaoPessoa(p, "sugerido", sug, n, amostras[p.id]))
        else:
            out.pessoas.append(SugestaoPessoa(
                p, "insuficiente", None, n, amostras[p.id],
                f"{n} de {max(s.min_operacoes_ritmo, 1)} operações necessárias, cada uma com ≥ {s.min_amostras_ritmo} "
                "apontamentos aprovados da pessoa e ≥ 2 pessoas na operação."))
    return out
