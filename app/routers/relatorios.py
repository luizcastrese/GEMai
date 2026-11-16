"""Relatório de desempenho: produto × variante × tempo previsto e realizado (tela e planilha)."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..deps import Ctx, get_ctx
from ..services import relatorio

router = APIRouter(tags=["relatorios"])


@router.get("/relatorios/desempenho")
def desempenho(produto_id: int | None = None, unidade_id: int | None = None, desde: date | None = None, ate: date | None = None,
               ctx: Ctx = Depends(get_ctx)):
    """Uma linha por plano (com o realizado quando a ordem tem apontamentos) e um resumo por produto + variante."""
    return relatorio.desempenho(ctx, produto_id=produto_id, unidade_id=unidade_id, desde=desde, ate=ate)


@router.get("/relatorios/desempenho.csv")
def desempenho_csv(tipo: Literal["detalhe", "resumo"] = Query("detalhe"), produto_id: int | None = None, unidade_id: int | None = None,
                   desde: date | None = None, ate: date | None = None, ctx: Ctx = Depends(get_ctx)):
    r = relatorio.desempenho(ctx, produto_id=produto_id, unidade_id=unidade_id, desde=desde, ate=ate)
    corpo = relatorio.csv_resumo(r) if tipo == "resumo" else relatorio.csv_detalhe(r)
    ctx.auditar("relatorio.exportar", "relatorio", None, None, {"tipo": tipo, "produto_id": produto_id, "linhas": len(r["linhas"])})
    ctx.db.commit()
    return Response(corpo, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="desempenho-{tipo}.csv"'})
