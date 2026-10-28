"""Orquestra: recomendar arranjos para um produto e gerar o plano a partir do arranjo ESCOLHIDO."""
from __future__ import annotations

import math

from fastapi import HTTPException

from ...deps import Ctx
from ...models import PlanoTrabalho, Produto
from .. import ia
from .. import plano as pl
from .avaliar import Avaliador, Config, Resultado, cronograma, melhores


def _rotulo(r: Resultado) -> str:
    c = r.config
    return f"{c.pessoas} pessoa(s), {c.lotes} lote(s), regra {c.regra}" + (f", meio {r.meio_nome}" if r.meio_nome else "")


def _candidato(base, r: Resultado, inicio_local) -> dict:
    cron = cronograma(base, r, inicio_local)
    return {**r.config.como_dict(), "rotulo": _rotulo(r), "meio": r.meio_nome, **r.metricas, "cronograma": cron,
            "fim_previsto": max((t["fim"] for t in cron), default=None)}


def preparar_avaliador(ctx: Ctx, produto: Produto, quantidade: float, unidade_id: int, cfg: dict):
    cfg = {**cfg, "pessoas": 1}  # o nº de pessoas é decisão do ARRANJO, não da configuração
    base = pl.preparar(ctx, produto, unidade_id, cfg)
    proposta, provedor, aviso = pl.propor(base, quantidade)
    return base, proposta, provedor, aviso, Avaliador(base, proposta, quantidade)


def recomendar(ctx: Ctx, produto: Produto, quantidade: float, unidade_id: int, cfg: dict, *, pessoas_max: int, n_melhores: int,
               explicar: bool = False) -> dict:
    base, proposta, provedor, aviso, av = preparar_avaliador(ctx, produto, quantidade, unidade_id, cfg)
    inicio_local = pl.inicio_local_do_plano(ctx, cfg)
    resultados = [r for c in av.configs(pessoas_max) if (r := av.avaliar(c)) is not None]
    pendencias = av.pendencias_gerais() + list(proposta.dados_faltantes)
    if not resultados:
        meio = av.meios_completos[0] if av.meios_completos else None
        pendencias = list(dict.fromkeys(av.incompletos(quantidade, meio) + pendencias))
        return {"provedor": provedor, "aviso": aviso, "avaliados": 0, "candidatos": [], "pendencias": pendencias, "explicacao": "",
                "equipe_minima": av.equipe_minima(quantidade, meio), "premissas": proposta.premissas}
    explicacao, ia_prov = "", ""
    top = melhores(resultados, n_melhores)
    if explicar:
        fatos = {"produto": produto.nome, "quantidade": quantidade, "limites": {"pessoas": [1, 8], "lotes": [1, 2, 4], "regras": ["plano", "critico"]},
                 "candidatos": [{"rotulo": _rotulo(r), **{k: r.metricas[k] for k in ("makespan_min", "pessoas_hora", "gargalo", "ocupacao_pct", "ergonomia")}} for r in top]}
        ex, ia_prov, _ = ia.explicar_arranjos(ctx.empresa, fatos)
        extras = [Config(a.pessoas, a.lotes, a.regra, resultados[0].config.meio_id, "ia") for a in ex.alternativas]
        novos = [r for c in av.configs(pessoas_max, extras) if c.origem == "ia" and (r := av.avaliar(c)) is not None]
        if novos:
            resultados += novos
            top = melhores(resultados, n_melhores)
        explicacao = ex.texto
    cands = [_candidato(base, r, inicio_local) for r in top]
    return {"provedor": provedor, "aviso": aviso, "avaliados": len(resultados), "candidatos": cands, "pendencias": list(dict.fromkeys(pendencias)),
            "explicacao": explicacao, "explicacao_provedor": ia_prov, "equipe_minima": av.equipe_minima(quantidade, None if not av.meios_completos else av.meios_completos[0]),
            "premissas": proposta.premissas}


def gerar_do_arranjo(ctx: Ctx, produto: Produto, quantidade: float, unidade_id: int, cfg: dict, escolha: Config,
                     plano: PlanoTrabalho | None = None) -> PlanoTrabalho:
    base, proposta, provedor, aviso, av = preparar_avaliador(ctx, produto, quantidade, unidade_id, cfg)
    if escolha.meio_id is not None and escolha.meio_id not in {m.id for m in av.meios_completos}:
        raise HTTPException(422, "Meio de movimentação inválido para esta unidade ou sem ficha técnica validada.")
    if escolha.lotes not in (1, 2, 4) or (escolha.lotes > 1 and (quantidade != int(quantidade) or escolha.lotes > int(quantidade))):
        raise HTTPException(422, "Número de lotes inválido para esta quantidade.")
    if not 1 <= escolha.pessoas <= 8 or escolha.regra not in ("plano", "critico"):
        raise HTTPException(422, "Arranjo inválido.")
    if not av.meios_completos and escolha.meio_id is not None:
        raise HTTPException(422, "Nenhum meio de movimentação com ficha técnica validada.")
    res = av.avaliar(escolha)
    if res is None:
        falt = av.incompletos(quantidade, next((m for m in av.meios_completos if m.id == escolha.meio_id), None))
        raise HTTPException(422, "Arranjo inviável: " + ("; ".join(falt) if falt else "a equipe é menor que a necessária para alguma tarefa."))
    inicio_local = pl.inicio_local_do_plano(ctx, cfg)
    uteis = cfg.get("so_dias_uteis", True)
    linhas, ag = [], []
    for a in res.alocadas:
        l = dict(a.opcao.linha)
        l["nome"] = a.tarefa.nome
        linhas.append(l)
        ini = pl._inicio_util(pl.instante_apos(inicio_local, base.blocos, uteis, a.ini), base.blocos, uteis)
        ag.append((ini, pl.instante_apos(inicio_local, base.blocos, uteis, a.fim), a.fim - a.ini))
    m = res.metricas
    arranjo = {**escolha.como_dict(), "meio": res.meio_nome, **{k: m[k] for k in ("makespan_min", "pessoas_hora", "gargalo", "ocupacao_pct", "ergonomia")}}
    prem = av.pendencias_gerais() + [f"Arranjo escolhido: {_rotulo(res)}. Prazo (trabalho corrido): {m['makespan_min']:g} min; gargalo: "
                                     f"{m['gargalo']['recurso']} ({m['gargalo']['ocupacao_pct']:g}% de ocupação)."]
    return pl.persistir(base, quantidade, plano, proposta, provedor, aviso, linhas, ag, extras_config={"arranjo": arranjo},
                        extras_totais={"arranjo": arranjo, "makespan_min": m["makespan_min"]}, extras_premissas=prem)
