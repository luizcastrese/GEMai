"""Contorno físico MÍNIMO para a IA prever tempo, em linguagem comum.

Mínimo = o que cada tarefa precisa para o tempo ser calculado:
  • locais por onde a peça passa e a distância entre eles;
  • para cada equipamento usado, para que serve e a ficha técnica validada (avanço, velocidade… — nunca uma taxa digitada);
  • o peso da peça manuseada.
Dimensões dos locais, temperatura, ruído, etc. são opcionais e ficam fora deste mínimo.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Componente, Distancia, Espaco, Etapa, Operacao, Processo, Produto, Recurso
from . import modelo_tempo
from .modulos import entradas as entradas_modulo, ficha as ficha_catalogo


def resumo(db: Session, empresa_id: int, unidade_ids: list[int]) -> dict:
    locais = list(db.scalars(select(Espaco).where(Espaco.empresa_id == empresa_id, Espaco.unidade_id.in_(unidade_ids),
                                                  Espaco.ativo.is_(True)).order_by(Espaco.nome)))
    nome_local = {e.id: e.nome for e in locais}
    equip = {r.id: r for r in db.scalars(select(Recurso).where(
        Recurso.empresa_id == empresa_id, Recurso.unidade_id.in_(unidade_ids), Recurso.ativo.is_(True)))}
    pecas = list(db.scalars(select(Produto).where(Produto.empresa_id == empresa_id, Produto.ativo.is_(True)).order_by(Produto.nome)))

    rows = db.execute(select(Operacao, Etapa, Processo).join(Etapa, Etapa.id == Operacao.etapa_id)
                      .join(Processo, Processo.id == Etapa.processo_id)
                      .where(Operacao.empresa_id == empresa_id, Processo.unidade_id.in_(unidade_ids),
                             Processo.status.in_(("rascunho", "ativo")))
                      .order_by(Processo.id, Etapa.sequencia, Operacao.sequencia)).all()
    tarefas, faltando = [], []
    pares: dict[tuple[int, int], dict] = {}
    equip_usados: set[int] = set()
    total = 0
    if not locais:
        faltando.append("Cadastre os locais por onde a peça passa (ex.: estoque, bancada, montagem).")
        total += 1
    for op, et, pr in rows:
        pend = []
        total += 1  # peso da peça
        if op.item_peso_kg is None:
            pend.append("peso da peça")
            faltando.append(f"Peso da peça em '{op.nome}'")
        if op.recurso_padrao_id:
            equip_usados.add(op.recurso_padrao_id)
        o, d = op.espaco_origem_id, op.espaco_destino_id
        dist = None
        if o and d and o != d:
            dist = op.distancia_m if op.distancia_m is not None else modelo_tempo.distancia_entre(db, empresa_id, o, d)
            par = tuple(sorted((o, d)))
            pares.setdefault(par, {"origem_id": par[0], "destino_id": par[1],
                                   "origem": nome_local.get(par[0], "?"), "destino": nome_local.get(par[1], "?"), "metros": dist})
        elif bool(o) != bool(d):
            total += 1
            pend.append("de onde sai e para onde vai")
            faltando.append(f"De onde a peça sai e para onde vai em '{op.nome}'")
        tarefas.append({"operacao_id": op.id, "processo_id": pr.id, "processo": pr.nome, "status": pr.status,
                        "nome": op.nome if et.nome == op.nome else f"{et.nome} › {op.nome}",
                        "recurso_padrao_id": op.recurso_padrao_id, "espaco_origem_id": o, "espaco_destino_id": d,
                        "distancia_m": dist, "item_peso_kg": op.item_peso_kg, "pendente": pend})
    # Produtos com componentes: a peça percorre estoque → equipamentos (corte, borda, furação) → montagem.
    usa_produtos = bool(db.scalar(select(Componente.id).where(Componente.empresa_id == empresa_id).limit(1)))
    if usa_produtos:
        def local_de(tipo=None, funcao=None):
            if funcao:
                r = next((r for r in sorted(equip.values(), key=lambda r: r.nome) if r.funcao == funcao and r.espaco_id in nome_local), None)
                return r.espaco_id if r else None
            e = next((e for e in locais if e.tipo == tipo), None)
            return e.id if e else None
        rota = [local_de("estoque"), local_de(funcao="corte"), local_de(funcao="bordo"), local_de(funcao="furacao"), local_de("montagem")]
        rota = [x for x in rota if x]
        for a, b in zip(rota, rota[1:]):
            if a == b:
                continue
            par = tuple(sorted((a, b)))
            if par not in pares:
                pares[par] = {"origem_id": par[0], "destino_id": par[1], "origem": nome_local.get(par[0], "?"), "destino": nome_local.get(par[1], "?"),
                              "metros": modelo_tempo.distancia_entre(db, empresa_id, par[0], par[1])}
    for par in pares.values():
        total += 1
        if par["metros"] is None:
            faltando.append(f"Distância entre {par['origem']} e {par['destino']}")
    equipamentos = []
    for r in equip.values():
        usado = r.id in equip_usados
        validados = entradas_modulo.ficha_do_meio(db, empresa_id, r.id)
        precisa = ficha_catalogo.aplicaveis(r.funcao) if r.funcao else []
        faltam_ficha = [p for p in precisa if p.nome not in validados]
        if usado:
            total += 1
            if not r.funcao:
                faltando.append(f"Para que serve '{r.nome}' (função)")
            elif faltam_ficha:
                faltando.append(f"Ficha técnica de '{r.nome}': faltam " + ", ".join(p.descricao.lower() for p in faltam_ficha))
        equipamentos.append({"id": r.id, "nome": r.nome, "ficha_validada": len(precisa) - len(faltam_ficha), "ficha_total": len(precisa),
                             "espaco_id": r.espaco_id, "usado": usado, "funcao": r.funcao, "marca": r.marca, "modelo": r.modelo})
    pendentes = len(faltando)
    return {
        "locais": [{"id": e.id, "nome": e.nome, "tipo": e.tipo, "temperatura_c": e.temperatura_c, "ruido_db": e.ruido_db} for e in locais],
        "equipamentos": sorted(equipamentos, key=lambda x: x["nome"]),
        "pecas": [{"id": p.id, "nome": p.nome, "peso_kg": p.peso_kg} for p in pecas],
        "tarefas": tarefas, "distancias": sorted(pares.values(), key=lambda x: (x["origem"], x["destino"])),
        "faltando": faltando, "pendentes": pendentes, "total": max(total, 1),
        "completo": pendentes == 0 and (bool(rows) or usa_produtos),
        "progresso_pct": round(100 * (max(total, 1) - pendentes) / max(total, 1)) if rows or locais or usa_produtos else 0,
    }
