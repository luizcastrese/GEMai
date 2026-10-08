"""Indicadores do gestor (seção 13). Tudo calculado por regras determinísticas."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import ORDEM_ABERTA
from ..models import Apontamento, Empresa, Ocorrencia, Operacao, Ordem, Processo, Etapa, Recurso
from . import metricas, timecalc


def tz_empresa(empresa: Empresa) -> ZoneInfo:
    try:
        return ZoneInfo(empresa.fuso)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _limites(de: date, ate: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    ini = datetime.combine(de, time.min, tzinfo=tz).astimezone(timezone.utc)
    fim = datetime.combine(ate + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return ini, fim


def alerta_ergonomia(erg: dict | None) -> bool:
    """Sinaliza operação que merece avaliação formal (não é uma avaliação ergonômica)."""
    if not erg:
        return False
    altos = sum(1 for k in ("repetitividade", "esforco_fisico", "postura", "deslocamento", "tempo_em_pe")
                if erg.get(k) == "alto")
    return altos >= 2 or (altos >= 1 and erg.get("pausas") == "insuficientes")


def calcular(db: Session, empresa: Empresa, unidade_ids: list[int], de: date, ate: date) -> dict:
    tz = tz_empresa(empresa)
    ini, fim = _limites(de, ate, tz)
    agora = datetime.now(timezone.utc)
    hoje = agora.astimezone(tz).date()
    base = {"de": de.isoformat(), "ate": ate.isoformat()}
    if not unidade_ids:
        return {**base, "vazio": True}

    ordens = list(db.scalars(select(Ordem).where(Ordem.empresa_id == empresa.id,
                                                 Ordem.unidade_id.in_(unidade_ids))))
    por_status: dict[str, int] = defaultdict(int)
    for o in ordens:
        por_status[o.status] += 1
    abertas = [o for o in ordens if o.status in ORDEM_ABERTA]
    atrasadas = sorted(
        [{"id": o.id, "numero": o.numero, "cliente": o.cliente, "prazo": o.prazo.isoformat(),
          "dias_atraso": (hoje - o.prazo).days, "status": o.status}
         for o in abertas if o.prazo and o.prazo < hoje],
        key=lambda x: -x["dias_atraso"])
    concl_periodo = [o for o in ordens if o.concluida_em and ini <= o.concluida_em < fim]
    concl_atraso = [o for o in concl_periodo if o.prazo and o.concluida_em.astimezone(tz).date() > o.prazo]

    # ordens com atividade no período (para métricas de tempo)
    ids_ordens = [o.id for o in ordens]
    apts = []
    if ids_ordens:
        apts = list(db.scalars(select(Apontamento).where(
            Apontamento.empresa_id == empresa.id, Apontamento.ordem_id.in_(ids_ordens),
            Apontamento.anulado.is_(False), Apontamento.status != "rejeitado",
            Apontamento.inicio >= ini, Apontamento.inicio < fim)))
    ids_ativas = sorted({a.ordem_id for a in apts} | {o.id for o in concl_periodo})
    ordens_ativas = [o for o in ordens if o.id in set(ids_ativas)]
    mets = metricas.metricas_operacoes(db, ordens_ativas)

    # ---- planejado x realizado (operações concluídas no período) e gargalos
    por_op: dict[tuple, dict] = {}
    por_etapa: dict[str, dict] = defaultdict(lambda: {"espera_fila_min": 0.0, "ocupacao_min": 0.0,
                                                      "espera_registrada_min": 0.0, "n": 0})
    tend: dict[date, dict] = defaultdict(lambda: {"est": 0.0, "real": 0.0, "paradas_min": 0.0,
                                                  "boa": 0.0, "refugo": 0.0, "ordens": 0})
    est_tot = real_tot = 0.0
    for o in ordens_ativas:
        for m in mets[o.id]:
            e = por_etapa[m["etapa"]]
            e["espera_fila_min"] += m["espera_fila_min"]
            e["espera_registrada_min"] += m["espera_min"]
            e["ocupacao_min"] += m["realizado_min"]
            e["n"] += 1
            ce = m["concluida_em"]
            if m["status"] == "concluida" and m["estimado_min"] is not None and ce and ini <= ce < fim:
                k = (m["etapa"], m["operacao"])
                d = por_op.setdefault(k, {"etapa": k[0], "operacao": k[1], "estimado_min": 0.0,
                                          "realizado_min": 0.0, "execucoes": 0})
                d["estimado_min"] += m["estimado_min"]
                d["realizado_min"] += m["realizado_min"]
                d["execucoes"] += 1
                est_tot += m["estimado_min"]
                real_tot += m["realizado_min"]
                sem = ce.astimezone(tz).date()
                sem -= timedelta(days=sem.weekday())
                tend[sem]["est"] += m["estimado_min"]
                tend[sem]["real"] += m["realizado_min"]
    comparativo = []
    for d in por_op.values():
        d["desvio_min"] = timecalc.arred(d["realizado_min"] - d["estimado_min"])
        d["desvio_pct"] = timecalc.arred(timecalc.desvio_pct(d["realizado_min"], d["estimado_min"]))
        d["estimado_min"] = timecalc.arred(d["estimado_min"])
        d["realizado_min"] = timecalc.arred(d["realizado_min"])
        comparativo.append(d)
    comparativo.sort(key=lambda d: -abs(d["desvio_min"]))
    gargalos = sorted(
        [{"etapa": k, **{kk: timecalc.arred(vv) if isinstance(vv, float) else vv for kk, vv in v.items()}}
         for k, v in por_etapa.items()],
        key=lambda x: -(x["espera_fila_min"] + x["espera_registrada_min"]))

    # ---- paradas / ocorrências
    ocs = list(db.scalars(select(Ocorrencia).where(
        Ocorrencia.empresa_id == empresa.id, Ocorrencia.unidade_id.in_(unidade_ids),
        Ocorrencia.anulada.is_(False), Ocorrencia.inicio >= ini, Ocorrencia.inicio < fim)))
    paradas: dict[str, dict] = defaultdict(lambda: {"ocorrencias": 0, "duracao_min": 0.0})
    n_qual = n_ret_oc = 0
    for c in ocs:
        dur = timecalc.duracao_min(c.inicio, c.fim or agora) or 0.0
        if c.tipo == "parada":
            p = paradas[c.causa or "Não informada"]
            p["ocorrencias"] += 1
            p["duracao_min"] += dur
            s = c.inicio.astimezone(tz).date()
            tend[s - timedelta(days=s.weekday())]["paradas_min"] += dur
        elif c.tipo == "qualidade":
            n_qual += 1
        elif c.tipo == "retrabalho":
            n_ret_oc += 1
    paradas_l = sorted(({"causa": k, "ocorrencias": v["ocorrencias"], "duracao_min": timecalc.arred(v["duracao_min"])}
                        for k, v in paradas.items()), key=lambda x: -x["duracao_min"])

    # ---- retrabalho, produtividade, qualidade, utilização
    ret_min = exec_min = trab_min = boa = refugo = 0.0
    por_rec_prod: dict[int, dict] = defaultdict(lambda: {"boa": 0.0, "min": 0.0})
    intervalos: dict[int, list] = defaultdict(list)
    for a in apts:
        d = timecalc.duracao_min(a.inicio, a.fim)
        if d is None:
            continue
        if a.tipo in metricas.TRABALHO:
            trab_min += d
        if a.tipo == "retrabalho":
            ret_min += d
        if a.tipo == "execucao":
            exec_min += d
            boa += a.quantidade_boa
            refugo += a.quantidade_refugo
            s = a.inicio.astimezone(tz).date()
            t = tend[s - timedelta(days=s.weekday())]
            t["boa"] += a.quantidade_boa
            t["refugo"] += a.quantidade_refugo
            if a.recurso_id:
                por_rec_prod[a.recurso_id]["boa"] += a.quantidade_boa
                por_rec_prod[a.recurso_id]["min"] += d
        if a.recurso_id and a.tipo in metricas.TRABALHO:
            intervalos[a.recurso_id].append((max(a.inicio, ini), min(a.fim, fim)))
    for o in concl_periodo:
        s = o.concluida_em.astimezone(tz).date()
        tend[s - timedelta(days=s.weekday())]["ordens"] += 1

    recursos = {r.id: r for r in db.scalars(select(Recurso).where(
        Recurso.empresa_id == empresa.id, Recurso.unidade_id.in_(unidade_ids), Recurso.ativo.is_(True)))}
    du = timecalc.dias_uteis(de, ate)
    utilizacao = []
    for rid, r in recursos.items():
        usado = timecalc.uniao_minutos(intervalos.get(rid, []))
        disp = du * r.horas_disponiveis_dia * 60
        utilizacao.append({"recurso_id": rid, "recurso": r.nome, "usado_min": timecalc.arred(usado),
                           "disponivel_min": timecalc.arred(disp),
                           "utilizacao_pct": timecalc.arred(usado / disp * 100) if disp else None})
    utilizacao.sort(key=lambda x: -(x["utilizacao_pct"] or 0))
    produtividade_rec = [{"recurso": recursos[rid].nome if rid in recursos else str(rid),
                          "un_por_hora": timecalc.arred(v["boa"] / (v["min"] / 60)) if v["min"] else None}
                         for rid, v in por_rec_prod.items()]

    # ---- ergonomia: operações de processos ativos sinalizadas
    erg = []
    rows = db.execute(select(Operacao, Etapa, Processo).join(Etapa, Etapa.id == Operacao.etapa_id)
                      .join(Processo, Processo.id == Etapa.processo_id)
                      .where(Operacao.empresa_id == empresa.id, Processo.status == "ativo",
                             Processo.unidade_id.in_(unidade_ids))).all()
    for op, et, pr in rows:
        if alerta_ergonomia(op.ergonomia):
            erg.append({"processo": pr.nome, "etapa": et.nome, "operacao": op.nome, "ergonomia": op.ergonomia})

    semanas = []
    for s in sorted(tend):
        t = tend[s]
        total_q = t["boa"] + t["refugo"]
        semanas.append({
            "semana": s.isoformat(),
            "eficiencia_pct": timecalc.arred(timecalc.eficiencia(t["est"], t["real"])),
            "paradas_min": timecalc.arred(t["paradas_min"]),
            "refugo_pct": timecalc.arred(t["refugo"] / total_q * 100) if total_q else None,
            "ordens_concluidas": t["ordens"],
        })

    total_q = boa + refugo
    return {
        **base,
        "ordens": {"por_status": dict(por_status), "em_producao": len(abertas),
                   "concluidas_no_periodo": len(concl_periodo),
                   "concluidas_com_atraso_no_periodo": len(concl_atraso)},
        "ordens_atrasadas": atrasadas[:20],
        "planejado_x_realizado": {
            "estimado_min": timecalc.arred(est_tot) if por_op else None,
            "realizado_min": timecalc.arred(real_tot) if por_op else None,
            "eficiencia_pct": timecalc.arred(timecalc.eficiencia(est_tot, real_tot)),
            "maiores_desvios": comparativo[:10],
        },
        "gargalos": gargalos[:10],
        "paradas": {"total_min": timecalc.arred(sum(p["duracao_min"] for p in paradas_l)),
                    "por_causa": paradas_l[:10]},
        "retrabalho": {"tempo_min": timecalc.arred(ret_min),
                       "pct_do_tempo_de_trabalho": timecalc.arred(ret_min / trab_min * 100) if trab_min else None,
                       "ocorrencias_registradas": n_ret_oc},
        "produtividade": {"quantidade_boa": boa,
                          "un_por_hora": timecalc.arred(boa / (exec_min / 60)) if exec_min else None,
                          "por_recurso": produtividade_rec},
        "utilizacao_maquinas": utilizacao,
        "qualidade": {"refugo": refugo, "refugo_pct": timecalc.arred(refugo / total_q * 100) if total_q else None,
                      "ocorrencias_qualidade": n_qual, "retrabalho_min": timecalc.arred(ret_min)},
        "tendencia_semanal": semanas,
        "alertas_ergonomia": erg,
    }
