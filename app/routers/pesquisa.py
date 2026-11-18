"""Indicadores do piloto (para o TCC): agregados da empresa, sem dado pessoal e sem rastreamento de cliques."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..deps import Ctx, get_ctx
from ..services import pesquisa

router = APIRouter(tags=["pesquisa"])


@router.get("/pesquisa/indicadores")
def indicadores(ctx: Ctx = Depends(get_ctx)):
    return pesquisa.indicadores(ctx.db, ctx.empresa_id)


@router.get("/pesquisa/pedidos.csv")
def pedidos_csv(ctx: Ctx = Depends(get_ctx)):
    """Previsto × realizado por pedido (uma linha por pedido medido), para análise estatística fora do sistema."""
    d = pesquisa.indicadores(ctx.db, ctx.empresa_id)["previsto_x_realizado"]["pedidos"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["pedido", "previsto_min", "realizado_min", "desvio_pct", "calibrado", "forma_de_medir", "concluido_em"])
    for p in d:
        w.writerow([p["ordem_id"], str(p["previsto_min"]).replace(".", ","), str(p["realizado_min"]).replace(".", ","),
                    str(p["desvio_pct"]).replace(".", ","), "sim" if p["calibrado"] else "nao", p["forma"], p["concluida_em"] or ""])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="pedidos-previsto-realizado.csv"'})
