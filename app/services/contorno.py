"""Ambiente do item em linguagem comum: locais, equipamentos e as distâncias que a rota das peças usa.

A rota segue o que o planejador faz: estoque → equipamentos (corte, borda, furação) → montagem. Cada par de locais
consecutivos gera uma distância a informar; o que não for informado aparece como pendência, nunca como valor inventado.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Espaco, Recurso
from . import modelo_tempo


def resumo(db: Session, empresa_id: int, unidade_ids: list[int]) -> dict:
    locais = list(db.scalars(select(Espaco).where(Espaco.empresa_id == empresa_id, Espaco.unidade_id.in_(unidade_ids),
                                                  Espaco.ativo.is_(True)).order_by(Espaco.nome)))
    nome_local = {e.id: e.nome for e in locais}
    equip = list(db.scalars(select(Recurso).where(Recurso.empresa_id == empresa_id, Recurso.unidade_id.in_(unidade_ids),
                                                  Recurso.ativo.is_(True)).order_by(Recurso.nome)))

    def local_de(tipo=None, funcao=None):
        if funcao:
            r = next((r for r in equip if r.funcao == funcao and r.espaco_id in nome_local), None)
            return r.espaco_id if r else None
        e = next((e for e in locais if e.tipo == tipo), None)
        return e.id if e else None

    rota = [x for x in (local_de("estoque"), local_de(funcao="corte"), local_de(funcao="bordo"),
                        local_de(funcao="furacao"), local_de("montagem")) if x]
    pares: dict[tuple[int, int], dict] = {}
    for a, b in zip(rota, rota[1:]):
        if a == b:
            continue
        par = tuple(sorted((a, b)))
        pares.setdefault(par, {"origem_id": par[0], "destino_id": par[1], "origem": nome_local.get(par[0], "?"),
                               "destino": nome_local.get(par[1], "?"),
                               "metros": modelo_tempo.distancia_entre(db, empresa_id, par[0], par[1])})
    equipamentos = []
    for r in equip:
        cap = modelo_tempo.capacidade_por_hora(r.capacidade, r.capacidade_unidade)
        equipamentos.append({"id": r.id, "nome": r.nome, "capacidade": r.capacidade, "capacidade_unidade": r.capacidade_unidade,
                             "pecas_por_hora": cap, "espaco_id": r.espaco_id, "funcao": r.funcao})
    return {
        "locais": [{"id": e.id, "nome": e.nome, "tipo": e.tipo, "tolerancia_ambiente_pct": e.tolerancia_ambiente_pct,
                    "temperatura_c": e.temperatura_c, "ruido_db": e.ruido_db, "altura_trabalho_m": e.altura_trabalho_m} for e in locais],
        "equipamentos": equipamentos,
        "distancias": sorted(pares.values(), key=lambda x: (x["origem"], x["destino"])),
    }
