"""Métricas determinísticas por ordem/operação (base para dashboard e para a IA analítica)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Apontamento, Ocorrencia, Ordem, OrdemOperacao
from . import timecalc

TRABALHO = ("preparacao", "execucao", "retrabalho")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def apontamentos_validos(db: Session, ordem_ids: list[int]) -> list[Apontamento]:
    if not ordem_ids:
        return []
    return list(db.scalars(select(Apontamento).where(
        Apontamento.ordem_id.in_(ordem_ids), Apontamento.anulado.is_(False),
        Apontamento.status != "rejeitado")))


def metricas_operacoes(db: Session, ordens: list[Ordem]) -> dict[int, list[dict]]:
    """Por ordem: lista (na sequência do roteiro) com tempos estimado/real, espera e refugo."""
    ids = [o.id for o in ordens]
    por_oo: dict[int, list[Apontamento]] = {}
    for a in apontamentos_validos(db, ids):
        por_oo.setdefault(a.ordem_operacao_id, []).append(a)
    saida: dict[int, list[dict]] = {}
    for o in ordens:
        ultimo_fim = o.liberada_em
        linhas = []
        for oo in o.operacoes:
            aps = por_oo.get(oo.id, [])
            soma = {"preparacao": 0.0, "execucao": 0.0, "espera": 0.0, "retrabalho": 0.0}
            boa = refugo = 0.0
            for a in aps:
                d = timecalc.duracao_min(a.inicio, a.fim) or 0.0
                soma[a.tipo] += d
                if a.tipo == "execucao":
                    boa += a.quantidade_boa
                    refugo += a.quantidade_refugo
            primeiro = min((a.inicio for a in aps), default=None)
            fila = 0.0
            if primeiro and ultimo_fim and primeiro > ultimo_fim:
                fila = timecalc.duracao_min(ultimo_fim, primeiro) or 0.0
            fins = [a.fim for a in aps if a.fim]
            if fins:
                ultimo_fim = max(fins)
            realizado = soma["preparacao"] + soma["execucao"] + soma["retrabalho"]
            est = None
            if oo.tempo_exec_est_min is not None:
                est = (oo.tempo_prep_est_min or 0.0) + oo.tempo_exec_est_min
            linhas.append({
                "ordem_operacao_id": oo.id, "sequencia": oo.sequencia, "etapa": oo.etapa_nome,
                "operacao": oo.nome, "status": oo.status, "fonte_estimativa": oo.fonte_estimativa,
                "estimativa_validada": oo.estimativa_validada, "elementos_modelo": oo.detalhe_estimativa,
                "estimado_min": est, "realizado_min": realizado, **{f"{k}_min": v for k, v in soma.items()},
                "espera_fila_min": fila, "qtd_boa": boa, "qtd_refugo": refugo,
                "desvio_min": timecalc.desvio(realizado, est) if aps else None,
                "desvio_pct": timecalc.desvio_pct(realizado, est) if aps else None,
                "concluida_em": oo.concluida_em, "recurso_id": oo.recurso_id,
            })
        saida[o.id] = linhas
    return saida


def _comparaveis(linhas: list[dict]) -> list[dict]:
    return [m for m in linhas if m["estimado_min"] is not None and m["status"] == "concluida"]


def resumo_comparacao(linhas: list[dict]) -> dict:
    comp = _comparaveis(linhas)
    est = sum(m["estimado_min"] for m in comp)
    real = sum(m["realizado_min"] for m in comp)
    return {
        "operacoes_comparadas": len(comp),
        "estimado_min": timecalc.arred(est) if comp else None,
        "realizado_min": timecalc.arred(real) if comp else None,
        "desvio_min": timecalc.arred(real - est) if comp else None,
        "desvio_pct": timecalc.arred(timecalc.desvio_pct(real, est)) if comp else None,
        "eficiencia_pct": timecalc.arred(timecalc.eficiencia(est, real)) if comp else None,
        "comparacao_parcial": len(comp) < len([m for m in linhas if m["status"] == "concluida"]),
    }


def analisar_ordem(db: Session, ordem: Ordem) -> dict:
    linhas = metricas_operacoes(db, [ordem])[ordem.id]
    ocs = list(db.scalars(select(Ocorrencia).where(
        Ocorrencia.ordem_id == ordem.id, Ocorrencia.anulada.is_(False))))
    agora = _agora()
    ocorrencias = [{
        "id": c.id, "tipo": c.tipo, "causa": c.causa or "Não informada",
        "duracao_min": timecalc.arred(timecalc.duracao_min(c.inicio, c.fim or agora)),
        "em_aberto": c.fim is None, "ordem_operacao_id": c.ordem_operacao_id,
    } for c in ocs]
    tot = lambda k: sum(m[k] for m in linhas)  # noqa: E731
    return {
        "ordem": {"id": ordem.id, "numero": ordem.numero, "status": ordem.status,
                  "quantidade": ordem.quantidade, "prazo": ordem.prazo.isoformat() if ordem.prazo else None},
        "resumo": {
            **resumo_comparacao(linhas),
            "tempo_trabalho_min": timecalc.arred(tot("realizado_min")),
            "espera_registrada_min": timecalc.arred(tot("espera_min")),
            "espera_fila_min": timecalc.arred(tot("espera_fila_min")),
            "retrabalho_min": timecalc.arred(tot("retrabalho_min")),
            "tempo_total_min": timecalc.arred(tot("realizado_min") + tot("espera_min")),
            "refugo": tot("qtd_refugo"),
            "paradas_min": timecalc.arred(sum(o["duracao_min"] or 0 for o in ocorrencias if o["tipo"] == "parada")),
            "operacoes_sem_estimativa": len([m for m in linhas if m["estimado_min"] is None]),
        },
        "operacoes": [{k: (timecalc.arred(v) if isinstance(v, float) and k.endswith(("_min", "_pct")) else
                           (v.isoformat() if isinstance(v, datetime) else v)) for k, v in m.items()}
                      for m in linhas],
        "ocorrencias": ocorrencias,
    }
