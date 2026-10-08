"""Tela inicial simples: o que precisa de atenção agora, em linguagem comum."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from ..constants import ORDEM_ABERTA
from ..deps import Ctx, get_ctx
from ..models import Apontamento, ModeloTempo, Ocorrencia, Operacao, Ordem, Processo, Etapa
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
    if not ctx.eh_gestor:
        return {"acoes": acoes, "numeros": numeros}

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
    # previsões da IA aguardando confirmação (versão ativa de cada operação)
    pend = ctx.db.scalars(select(ModeloTempo).where(
        ModeloTempo.empresa_id == ctx.empresa_id, ModeloTempo.unidade_id.in_(unidades),
        ModeloTempo.status_validacao != "rejeitado").order_by(ModeloTempo.operacao_id, ModeloTempo.versao.desc())).all()
    ativos: dict[int, ModeloTempo] = {}
    for m in pend:
        ativos.setdefault(m.operacao_id, m)
    n_prev = sum(1 for m in ativos.values() if m.status_validacao == "pendente")
    if n_prev:
        acoes.append({"codigo": "previsoes", "nivel": "acao", "link": "#/processos",
                      "titulo": _plural(n_prev, "previsão de tempo da IA para confirmar", "previsões de tempo da IA para confirmar")})
    rascunhos = ctx.db.scalar(select(func.count(Processo.id)).where(
        Processo.empresa_id == ctx.empresa_id, Processo.unidade_id.in_(unidades), Processo.status == "rascunho")) or 0
    if rascunhos:
        acoes.append({"codigo": "rascunhos", "nivel": "acao", "link": "#/processos",
                      "titulo": _plural(rascunhos, "processo ainda não publicado", "processos ainda não publicados")})
    ativos_n = ctx.db.scalar(select(func.count(Processo.id)).where(
        Processo.empresa_id == ctx.empresa_id, Processo.unidade_id.in_(unidades), Processo.status == "ativo")) or 0
    if not rascunhos and not ativos_n:
        acoes.append({"codigo": "configurar", "nivel": "acao", "link": "#/implantacao",
                      "titulo": "Conte à IA como funciona sua operação para montar o primeiro processo"})
    elif ativos_n and not abertas:
        acoes.append({"codigo": "criar_ordem", "nivel": "info", "link": "#/ordens",
                      "titulo": "Nenhuma ordem em andamento. Crie uma para começar a produzir"})
    return {"acoes": acoes, "numeros": numeros}
