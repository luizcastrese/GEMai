from fastapi import APIRouter, Depends

from ..deps import Ctx, get_ctx
from ..services import contorno

router = APIRouter(tags=["contorno-fisico"])


@router.get("/contorno")
def obter(unidade_id: int, ctx: Ctx = Depends(get_ctx)):
    """O que falta do contorno físico mínimo (locais, distâncias, peças por hora, peso das peças)."""
    ctx.exige_unidade(unidade_id)
    return contorno.resumo(ctx.db, ctx.empresa_id, [unidade_id])
