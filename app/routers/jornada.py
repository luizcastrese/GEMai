"""Trilha guiada: em que etapa a unidade está e o que falta para avançar."""
from fastapi import APIRouter, Depends, HTTPException

from ..deps import Ctx, get_ctx
from ..services import jornada

router = APIRouter(tags=["jornada"])


@router.get("/jornada")
def obter_jornada(ctx: Ctx = Depends(get_ctx), unidade_id: int | None = None):
    if unidade_id is None:
        ids = ctx.ids_unidades()
        if not ids:
            raise HTTPException(404, "Nenhuma unidade disponível.")
        unidade_id = ids[0]
    return jornada.calcular(ctx.db, ctx.exige_unidade(unidade_id))
