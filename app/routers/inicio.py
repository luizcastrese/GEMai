"""Tela inicial simples: o que precisa de atenção agora, em linguagem comum."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from ..constants import ORDEM_ABERTA
from ..deps import Ctx, get_ctx
from ..models import Apontamento, Ocorrencia, Ordem
from ..services import jornada
from ..services.dashboard import tz_empresa

router = APIRouter(tags=["inicio"])


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


@router.get("/inicio")
def inicio(ctx: Ctx = Depends(get_ctx), unidade_id: int | None = None):
    if unidade_id is not None:
        ctx.exige_unidade(unidade_id)
        unidades = [unidade_id]
    else:
        unidades = ctx.ids_unidades()
    if not unidades:
        return {"acoes": [], "numeros": {}}
    hoje = datetime.now(timezone.utc).astimezone(tz_empresa(ctx.empresa)).date()
    abertas = ctx.db.scalars(select(Ordem).where(Ordem.empresa_id == ctx.empresa_id, Ordem.unidade_id.in_(unidades),
                                                 Ordem.status.in_(ORDEM_ABERTA))).all()
    atrasadas = [o for o in abertas if o.prazo and o.prazo < hoje]
    paradas = ctx.db.scalar(select(func.count(Ocorrencia.id)).where(
        Ocorrencia.empresa_id == ctx.empresa_id, Ocorrencia.unidade_id.in_(unidades), Ocorrencia.tipo == "parada",
        Ocorrencia.fim.is_(None), Ocorrencia.anulada.is_(False))) or 0
    numeros = {"ordens_abertas": len(abertas), "atrasadas": len(atrasadas), "paradas_abertas": paradas}
    acoes: list[dict] = []

    if atrasadas:
        acoes.append({"codigo": "atrasadas", "nivel": "alerta", "link": "#/ordens",
                      "titulo": _plural(len(atrasadas), "ordem atrasada", "ordens atrasadas")})
    if paradas:
        acoes.append({"codigo": "paradas", "nivel": "alerta", "link": "#/ordens",
                      "titulo": _plural(paradas, "parada em aberto", "paradas em aberto")})
    a_aprovar = ctx.db.scalar(select(func.count(Apontamento.id)).where(
        Apontamento.empresa_id == ctx.empresa_id, Apontamento.unidade_id.in_(unidades), Apontamento.status == "registrado",
        Apontamento.fim.is_not(None), Apontamento.anulado.is_(False))) or 0
    if a_aprovar:
        acoes.append({"codigo": "aprovar", "nivel": "acao", "link": "#/aprovacoes",
                      "titulo": _plural(a_aprovar, "registro de produção para aprovar", "registros de produção para aprovar")})
    # O próximo passo da trilha (etapas da preparação, depois plano → ordem). Uma unidade por vez.
    if unidade_id is not None or len(unidades) == 1:
        proximo = jornada.calcular(ctx.db, ctx.exige_unidade(unidades[0]))["proximo"]
        if proximo:
            acoes.append({"codigo": "proximo", "nivel": "acao", "link": proximo["link"], "titulo": proximo["titulo"], "botao": proximo["botao"]})
    return {"acoes": acoes, "numeros": numeros}
