"""Relatório de desempenho: produto × variante (especificações do pedido) × tempo previsto e realizado.

Uma linha por plano de trabalho (não cancelado). Quando o plano virou ordem e houve apontamentos, entra o tempo realizado.
O resumo agrupa por produto + variante e compara previsto × realizado SÓ nas ordens concluídas e com todos os passos com tempo
(comparar o que ainda não terminou, ou o que não tinha previsão, enganaria).
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from ..deps import Ctx
from ..models import Ordem, PlanoTrabalho, Produto, Unidade
from . import especificacao, metricas, timecalc
from .dashboard import tz_empresa


def _arr(v, casas=1):
    return None if v is None else round(v, casas)


def _intervalo(ctx: Ctx, desde: date | None, ate: date | None):
    tz = tz_empresa(ctx.empresa)
    ini = datetime.combine(desde, time.min, tz).astimezone(timezone.utc) if desde else None
    fim = datetime.combine(ate + timedelta(days=1), time.min, tz).astimezone(timezone.utc) if ate else None
    return ini, fim


def desempenho(ctx: Ctx, *, produto_id: int | None = None, unidade_id: int | None = None,
               desde: date | None = None, ate: date | None = None) -> dict:
    db = ctx.db
    stmt = ctx.query(PlanoTrabalho).where(PlanoTrabalho.status != "cancelado")
    produto = None
    if produto_id is not None:
        produto = ctx.obter(Produto, produto_id)
        stmt = stmt.where(PlanoTrabalho.produto_id == produto.id)
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        stmt = stmt.where(PlanoTrabalho.unidade_id == unidade_id)
    ini, fim = _intervalo(ctx, desde, ate)
    if ini:
        stmt = stmt.where(PlanoTrabalho.criado_em >= ini)
    if fim:
        stmt = stmt.where(PlanoTrabalho.criado_em < fim)
    planos = list(db.scalars(stmt.order_by(PlanoTrabalho.criado_em.desc(), PlanoTrabalho.id.desc()).limit(2000)))

    produtos = {p.id: p for p in db.scalars(select(Produto).where(Produto.empresa_id == ctx.empresa_id))}
    unidades = {u.id: u.nome for u in db.scalars(select(Unidade).where(Unidade.empresa_id == ctx.empresa_id))}
    ordens = {o.id: o for o in db.scalars(select(Ordem).where(Ordem.id.in_([p.ordem_id for p in planos if p.ordem_id]))) } if planos else {}
    por_ordem = metricas.metricas_operacoes(db, list(ordens.values())) if ordens else {}
    tz = tz_empresa(ctx.empresa)

    linhas = []
    for p in planos:
        prod = produtos.get(p.produto_id)
        o = ordens.get(p.ordem_id) if p.ordem_id else None
        t = p.totais or {}
        qtd = p.quantidade or 0
        previsto = t.get("tempo_padrao_min")
        sem_tempo = t.get("passos_incompletos", 0)
        l = {
            "plano_id": p.id, "plano": p.nome, "produto_id": p.produto_id, "produto": prod.nome if prod else "",
            "unidade": unidades.get(p.unidade_id, ""), "especificacoes": dict(p.especificacoes or {}),
            "variante": especificacao.resumo(prod, p.especificacoes), "chave_variante": especificacao.chave_variante(p.especificacoes),
            "quantidade": qtd, "status_plano": p.status, "criado_em": p.criado_em.astimezone(tz).strftime("%d/%m/%Y"),
            "previsto_min": _arr(previsto, 2), "previsto_por_unidade_min": _arr(previsto / qtd, 2) if previsto and qtd else None,
            "passos_sem_tempo": sem_tempo,
            "ordem_numero": o.numero if o else "", "cliente": o.cliente if o else "", "status_ordem": o.status if o else "",
            "concluida_em": o.concluida_em.astimezone(tz).strftime("%d/%m/%Y") if o and o.concluida_em else "",
            "realizado_min": None, "realizado_por_unidade_min": None, "desvio_min": None, "desvio_pct": None, "eficiencia_pct": None,
            "refugo": None, "comparavel": False,
        }
        if o:
            ops = por_ordem.get(o.id, [])
            realizado = sum(m["realizado_min"] for m in ops)
            if any(m["realizado_min"] for m in ops):
                l["realizado_min"] = _arr(realizado, 2)
                l["refugo"] = sum(m["qtd_refugo"] for m in ops)
            if o.status == "concluida" and l["realizado_min"] and previsto and not sem_tempo:
                l["comparavel"] = True
                l["realizado_por_unidade_min"] = _arr(realizado / qtd, 2) if qtd else None
                l["desvio_min"] = _arr(timecalc.desvio(realizado, previsto), 2)
                l["desvio_pct"] = _arr(timecalc.desvio_pct(realizado, previsto))
                l["eficiencia_pct"] = _arr(timecalc.eficiencia(previsto, realizado))
        linhas.append(l)

    return {"produto_id": produto.id if produto else None, "campos": [c["nome"] for c in (produto.campos_especificacao if produto else [])],
            "linhas": linhas, "resumo": _resumo(linhas), "limitado": len(planos) >= 2000}


def _resumo(linhas: list[dict]) -> list[dict]:
    grupos: dict[tuple, list[dict]] = {}
    for l in linhas:
        grupos.setdefault((l["produto"], l["chave_variante"]), []).append(l)
    saida = []
    for (produto, _chave), ls in sorted(grupos.items(), key=lambda kv: (kv[0][0].casefold(), kv[0][1].casefold())):
        comp = [l for l in ls if l["comparavel"]]
        q_comp = sum(l["quantidade"] for l in comp)
        prev_comp = sum(l["previsto_min"] for l in comp)
        real_comp = sum(l["realizado_min"] for l in comp)
        completos = [l for l in ls if l["previsto_min"] and not l["passos_sem_tempo"] and l["quantidade"]]
        q_compl = sum(l["quantidade"] for l in completos)
        saida.append({
            "produto": produto, "variante": ls[0]["variante"], "especificacoes": ls[0]["especificacoes"], "planos": len(ls),
            "ordens_concluidas": len(comp), "quantidade_concluida": q_comp,
            "previsto_por_unidade_planos_min": _arr(sum(l["previsto_min"] for l in completos) / q_compl, 2) if q_compl else None,
            "previsto_por_unidade_concluidas_min": _arr(prev_comp / q_comp, 2) if q_comp else None,
            "realizado_por_unidade_min": _arr(real_comp / q_comp, 2) if q_comp else None,
            "desvio_pct": _arr(timecalc.desvio_pct(real_comp, prev_comp)) if comp else None,
            "refugo": sum(l["refugo"] or 0 for l in comp),
        })
    return saida


# ---------------------------------------------------------------- CSV
def _cel(v) -> str:
    """Texto seguro para planilha: evita injeção de fórmula e usa vírgula decimal (padrão do Excel em pt-BR)."""
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",") if v != int(v) else str(int(v))
    v = str(v)
    return "'" + v if v and v[0] in "=+-@\t\r" else v


def _csv(cabecalho: list[str], linhas: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(cabecalho)
    for l in linhas:
        w.writerow([_cel(c) for c in l])
    return buf.getvalue().encode("utf-8-sig")  # BOM: o Excel abre os acentos certos


_STATUS_PLANO = {"rascunho": "Rascunho", "confirmado": "Confirmado"}
_STATUS_ORDEM = {"planejada": "Planejada", "liberada": "Liberada", "em_andamento": "Em andamento", "concluida": "Concluída", "cancelada": "Cancelada"}


def csv_detalhe(r: dict) -> bytes:
    campos = r["campos"]
    cab = ["Produto", "Pedido (plano)", "Unidade", "Criado em"] + (campos if campos else ["Especificações"]) + [
        "Quantidade", "Tempo previsto total (min)", "Tempo previsto por unidade (min)", "Passos sem tempo", "Situação do plano", "Ordem", "Cliente",
        "Situação da ordem", "Concluída em", "Tempo realizado total (min)", "Tempo realizado por unidade (min)", "Desvio (min)", "Desvio (%)",
        "Eficiência (%)", "Refugo (un)"]
    linhas = []
    for l in r["linhas"]:
        espec = [l["especificacoes"].get(c, "") for c in campos] if campos else [l["variante"]]
        linhas.append([l["produto"], l["plano"], l["unidade"], l["criado_em"]] + espec + [
            l["quantidade"], l["previsto_min"], l["previsto_por_unidade_min"], l["passos_sem_tempo"], _STATUS_PLANO.get(l["status_plano"], l["status_plano"]),
            l["ordem_numero"], l["cliente"], _STATUS_ORDEM.get(l["status_ordem"], l["status_ordem"]), l["concluida_em"], l["realizado_min"],
            l["realizado_por_unidade_min"], l["desvio_min"], l["desvio_pct"], l["eficiencia_pct"], l["refugo"]])
    return _csv(cab, linhas)


def csv_resumo(r: dict) -> bytes:
    campos = r["campos"]
    cab = ["Produto"] + (campos if campos else ["Variante (especificações)"]) + [
        "Planos", "Ordens concluídas", "Quantidade concluída", "Previsto por unidade nos planos (min)", "Previsto por unidade nas concluídas (min)",
        "Realizado por unidade (min)", "Desvio (%)", "Refugo (un)"]
    linhas = []
    for s in r["resumo"]:
        espec = [s["especificacoes"].get(c, "") for c in campos] if campos else [s["variante"] or "(sem especificação)"]
        linhas.append([s["produto"]] + espec + [s["planos"], s["ordens_concluidas"], s["quantidade_concluida"], s["previsto_por_unidade_planos_min"],
                                                 s["previsto_por_unidade_concluidas_min"], s["realizado_por_unidade_min"], s["desvio_pct"], s["refugo"]])
    return _csv(cab, linhas)
