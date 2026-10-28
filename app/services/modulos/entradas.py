"""Montagem das CONDIÇÕES (EntradaModulo) a partir de dados do sistema: produto, meios cadastrados, ambiente.

É aqui que o "mapeamento" da IA (nomes de componentes, equipamento, locais) vira número: medidas, pesos, distâncias
e ficha técnica vêm do banco, nunca da IA. Só parâmetro de meio VIGENTE e VALIDADO por uma pessoa entra.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Parametro
from .base import EntradaModulo


def ficha_do_meio(db: Session, empresa_id: int, recurso_id: int | None) -> dict[str, float]:
    """Parâmetros técnicos validados do meio (escopo `recurso`), por nome. Sem meio ou sem ficha: vazio."""
    if not recurso_id:
        return {}
    rows = db.scalars(select(Parametro).where(
        Parametro.empresa_id == empresa_id, Parametro.escopo_tipo == "recurso", Parametro.escopo_id == recurso_id,
        Parametro.vigente.is_(True), Parametro.status_validacao == "validado", Parametro.valor_num.is_not(None)))
    return {p.nome: p.valor_num for p in rows}


def componente_dict(c, peso_kg: float | None) -> dict:
    """Retrato de um Componente para os módulos (medidas em metros)."""
    return {"nome": c.nome, "qtd": c.quantidade, "material": c.material, "grupo": c.grupo or "Corpo", "comp": c.comprimento_m,
            "larg": c.largura_m, "esp": c.espessura_m, "peso_kg": peso_kg, "furos": c.furos, "bordas_m": c.bordas_m}


def ligacoes_do_grupo(ligs: list[dict], grupo_de: dict[str, str], grupo: str) -> list[dict]:
    """Ligações internas de um subconjunto (e as de seus componentes com o conjunto)."""
    return [l for l in ligs if grupo_de.get(l["componente"]) == grupo and (not l.get("ligado_a") or grupo_de.get(l["ligado_a"]) == grupo)]


def ligacoes_finais(ligs: list[dict], grupo_de: dict[str, str]) -> list[dict]:
    """Ligações entre subconjuntos diferentes (montagem final)."""
    return [l for l in ligs if l.get("ligado_a") and grupo_de.get(l["componente"]) != grupo_de.get(l["ligado_a"])]


def entrada_do_passo(modulo, passo, *, comps: list[dict], ligs: list[dict], unidades_produto: float, pessoas: int,
                     distancia_m: float | None, rec, ficha: dict[str, float], origem: str | None, destino: str | None) -> EntradaModulo:
    """Condições de um passo do plano. `comps` = todos os componentes do produto (dicts); o passo escolhe os seus por nome."""
    nomes = {n.lower() for n in passo.componentes}
    do_passo = [c for c in comps if c["nome"].lower() in nomes]
    grupo_de = {c["nome"]: c["grupo"] for c in comps}
    e = EntradaModulo(unidades_produto=unidades_produto, pessoas=pessoas, distancia_m=distancia_m, origem_nome=origem, destino_nome=destino,
                      recurso_nome=rec.nome if rec else None)
    if modulo.chave == "movimentacao":
        e.componentes = do_passo
        e.quantidade = sum(c["qtd"] for c in do_passo) * unidades_produto
        e.meio_nome, e.ficha_meio = (rec.nome, ficha) if rec else (None, {})
    elif modulo.unidade_contagem == "peca":
        e.componentes = do_passo
        e.quantidade = sum(c["qtd"] for c in do_passo) * unidades_produto
        e.ficha = ficha
    elif modulo.chave == "montagem":
        e.quantidade = unidades_produto
        if getattr(passo, "final", False):
            grupos = list(dict.fromkeys(grupo_de.values()))
            e.componentes, e.ligacoes = comps, ligacoes_finais(ligs, grupo_de)
            e.extras = {"final": True, "grupo": "Final", "n_pecas": float(max(len(grupos) - 1, 1)),
                        "peso_conjunto_kg": sum((c["peso_kg"] or 0) * c["qtd"] for c in comps) or None}
        else:
            grupo = passo.grupo or (do_passo[0]["grupo"] if do_passo else "Corpo")
            e.componentes = do_passo or [c for c in comps if c["grupo"] == grupo]
            e.ligacoes = ligacoes_do_grupo(ligs, grupo_de, grupo)
            e.extras = {"grupo": grupo}
    else:  # conferencia
        e.quantidade = unidades_produto
    return e


def entrada_da_operacao(db: Session, empresa_id: int, operacao, quantidade: float, produto=None, recurso=None) -> tuple[EntradaModulo, object | None]:
    """Condições de uma OPERAÇÃO de processo que escolheu um módulo. Medidas e pesos: o produto da ordem prevalece sobre o
    item típico da operação (como em `modelo_tempo.montar_contexto`). Devolve (entrada, recurso usado)."""
    from ...models import Recurso
    from ..modelo_tempo import distancia_entre
    modulo = operacao.modulo
    par = operacao.modulo_parametros or {}
    rec = recurso
    if rec is None and operacao.recurso_padrao_id:
        rec = db.get(Recurso, operacao.recurso_padrao_id)
        if rec is not None and rec.empresa_id != empresa_id:
            rec = None
    ficha = ficha_do_meio(db, empresa_id, rec.id if rec else None)

    def campo(prod_attr: str, op_attr: str):
        v = getattr(produto, prod_attr, None) if produto is not None else None
        return v if v is not None else getattr(operacao, op_attr)

    comp = {"nome": operacao.nome, "qtd": 1.0, "material": "", "grupo": "Corpo", "comp": campo("comprimento_m", "item_comprimento_m"),
            "larg": campo("largura_m", "item_largura_m"), "esp": None, "peso_kg": campo("peso_kg", "item_peso_kg"),
            "furos": int(par.get("furos_por_peca") or 0), "bordas_m": par.get("bordas_m_por_peca")}
    dist = operacao.distancia_m if operacao.distancia_m is not None else distancia_entre(
        db, empresa_id, operacao.espaco_origem_id, operacao.espaco_destino_id)
    e = EntradaModulo(quantidade=quantidade, unidades_produto=quantidade, pessoas=max(operacao.num_pessoas or 1, 1), distancia_m=dist,
                      recurso_nome=rec.nome if rec else None)
    if modulo == "movimentacao":
        e.componentes = [comp]
        e.meio_nome, e.ficha_meio = (rec.nome, ficha) if rec else (None, {})
    elif modulo in ("corte", "bordo", "furacao"):
        e.componentes = [comp]
        e.ficha = ficha
    elif modulo == "montagem":
        e.componentes = [comp]
        e.ligacoes = list(par.get("ligacoes") or [])
        e.extras = {"grupo": operacao.nome, "n_pecas": par.get("pecas_por_unidade")}
    return e, rec
