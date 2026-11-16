"""Variante do pedido: o produto é a família ("Armário"); tamanho, tipo e a lista de peças/parafusos daquele pedido ficam no plano.

- `validar`: confere os valores informados contra os campos que o produto declarou (nada de campo solto).
- `resumo` / `chave_variante`: texto legível e chave estável para agrupar pedidos iguais no relatório.
- `estrutura_transiente`: converte a estrutura do pedido nos mesmos objetos que o motor já usa, sem gravar nada.
"""
from __future__ import annotations

from fastapi import HTTPException

from ..models import Componente, Ligacao, Produto


def _num(v) -> float | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _fmt(v) -> str:
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def validar(produto: Produto, valores: dict | None) -> dict:
    """Devolve os valores limpos (números como número) na ordem dos campos do produto. Levanta 422 se algo não bate."""
    campos = list(produto.campos_especificacao or [])
    valores = {k.strip(): v for k, v in (valores or {}).items()}
    por_nome = {c["nome"].casefold(): c for c in campos}
    if valores and not campos:
        raise HTTPException(422, f'O produto "{produto.nome}" ainda não tem campos de especificação (ex.: largura, tipo). '
                                 "Cadastre-os no produto antes de informar os valores do pedido.")
    desconhecidos = [k for k in valores if k.casefold() not in por_nome]
    if desconhecidos:
        raise HTTPException(422, f'Campo(s) que o produto não tem: {", ".join(desconhecidos)}.')
    dado = {k.casefold(): v for k, v in valores.items()}
    limpo: dict = {}
    for c in campos:
        v = dado.get(c["nome"].casefold())
        vazio = v is None or (isinstance(v, str) and not v.strip())
        if vazio:
            if c.get("obrigatorio"):
                raise HTTPException(422, f'Preencha "{c["nome"]}".')
            continue
        if c["tipo"] == "numero":
            n = _num(v)
            if n is None or n < 0 or n > 1e9:
                raise HTTPException(422, f'"{c["nome"]}" deve ser um número positivo.')
            limpo[c["nome"]] = n
        elif c["tipo"] == "opcao":
            achou = next((o for o in c.get("opcoes", []) if o.casefold() == str(v).strip().casefold()), None)
            if achou is None:
                raise HTTPException(422, f'"{c["nome"]}": escolha uma das opções ({", ".join(c.get("opcoes", []))}).')
            limpo[c["nome"]] = achou
        else:
            t = str(v).strip()
            if len(t) > 200:
                raise HTTPException(422, f'"{c["nome"]}" é longo demais (máx. 200 caracteres).')
            limpo[c["nome"]] = t
    return limpo


def resumo(produto: Produto | None, valores: dict | None) -> str:
    """Ex.: "Largura 80 cm · Altura 200 cm · Tipo 2 portas"."""
    if not valores:
        return ""
    unidades = {c["nome"]: c.get("unidade", "") for c in (produto.campos_especificacao if produto else [])}
    partes = []
    for k, v in valores.items():
        u = unidades.get(k, "")
        partes.append(f"{k} {_fmt(v)}{(' ' + u) if u else ''}")
    return " · ".join(partes)


def chave_variante(valores: dict | None) -> str:
    """Chave estável (independe da ordem) para agrupar pedidos iguais."""
    return "; ".join(f"{k}={_fmt(v)}" for k, v in sorted((valores or {}).items(), key=lambda kv: kv[0].casefold()))


def estrutura_do_produto(componentes: list[Componente], ligacoes: list[Ligacao]) -> dict:
    """Modelo base do produto no formato do pedido (ligações por nome). Serve de ponto de partida editável."""
    nome = {c.id: c.nome for c in componentes}
    return {
        "componentes": [{"nome": c.nome, "quantidade": c.quantidade, "material": c.material, "grupo": c.grupo, "comprimento_m": c.comprimento_m,
                         "largura_m": c.largura_m, "espessura_m": c.espessura_m, "peso_kg": c.peso_kg, "furos": c.furos, "bordas_m": c.bordas_m}
                        for c in componentes],
        "ligacoes": [{"componente": nome[l.componente_id], "ligado_a": nome.get(l.ligado_a_id), "metodo": l.metodo, "fixadores": l.fixadores}
                     for l in ligacoes if l.componente_id in nome],
    }


def estrutura_transiente(estrutura: dict, empresa_id: int, produto_id: int) -> tuple[list[Componente], list[Ligacao]]:
    """Objetos em memória (NUNCA adicionados à sessão) com ids provisórios, no formato que `plano._carregar` devolve."""
    comps, por_nome = [], {}
    for i, c in enumerate(estrutura["componentes"], 1):
        obj = Componente(id=i, empresa_id=empresa_id, produto_id=produto_id, ordem=i, nome=c["nome"], quantidade=c.get("quantidade", 1.0),
                         material=c.get("material", ""), grupo=c.get("grupo") or "Corpo", comprimento_m=c.get("comprimento_m"),
                         largura_m=c.get("largura_m"), espessura_m=c.get("espessura_m"), peso_kg=c.get("peso_kg"),
                         furos=c.get("furos", 0), bordas_m=c.get("bordas_m"))
        comps.append(obj)
        por_nome[c["nome"].casefold()] = i
    ligs = [Ligacao(id=i, empresa_id=empresa_id, produto_id=produto_id, ordem=i, componente_id=por_nome[l["componente"].casefold()],
                    ligado_a_id=por_nome.get((l.get("ligado_a") or "").casefold()), metodo=l.get("metodo", "parafuso"), fixadores=l.get("fixadores", 0))
            for i, l in enumerate(estrutura.get("ligacoes", []), 1)]
    return comps, ligs
