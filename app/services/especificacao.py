"""Variante do pedido: o produto é a família ("Armário"); tamanho, tipo e a lista de peças/parafusos daquele pedido ficam no plano.

- `validar`: confere os valores informados contra os campos que o produto declarou (nada de campo solto).
- `resumo` / `chave_variante`: texto legível e chave estável para agrupar pedidos iguais no relatório.
- `estrutura_transiente`: converte a estrutura do pedido nos mesmos objetos que o motor já usa, sem gravar nada.
"""
from __future__ import annotations

import math

from fastapi import HTTPException

from ..models import Componente, Ligacao, Produto
from . import formulas as fm


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


def validar(produto: Produto, valores: dict | None, *, completo: bool = True) -> dict:
    """Devolve os valores limpos (números como número) na ordem dos campos do produto. Levanta 422 se algo não bate.
    `completo=False` (pré-visualização enquanto a pessoa digita) não cobra os campos obrigatórios."""
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
            if c.get("obrigatorio") and completo:
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
                         "largura_m": c.largura_m, "espessura_m": c.espessura_m, "peso_kg": c.peso_kg, "furos": c.furos, "bordas_m": c.bordas_m,
                         "formulas": dict(c.formulas or {})} for c in componentes],
        "ligacoes": [{"componente": nome[l.componente_id], "ligado_a": nome.get(l.ligado_a_id), "metodo": l.metodo, "fixadores": l.fixadores,
                      "formula_fixadores": l.formula_fixadores or ""} for l in ligacoes if l.componente_id in nome],
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


# ================================================================== fórmulas: medidas do pedido → peças
_UNIDADE_M = {"m": 1.0, "cm": 0.01, "mm": 0.001}
_DIMENSOES = ("comprimento_m", "largura_m", "espessura_m")


def valores_para_formulas(produto: Produto, espec: dict) -> dict:
    """Valores que as fórmulas enxergam: campos em m/cm/mm chegam em METROS; os demais, como foram digitados."""
    por_nome = {c["nome"]: c for c in (produto.campos_especificacao or [])}
    out = {}
    for k, v in (espec or {}).items():
        c = por_nome.get(k, {})
        fator = _UNIDADE_M.get((c.get("unidade") or "").strip().casefold()) if c.get("tipo") == "numero" else None
        out[k.casefold()] = v * fator if fator else v
    return out


def validar_formula(produto: Produto, texto: str, onde: str) -> None:
    """Confere a sintaxe e se os campos citados existem no produto. Levanta 422 com a mensagem para a pessoa."""
    try:
        usados = fm.campos_usados(fm.compilar(texto))
    except fm.FormulaErro as e:
        raise HTTPException(422, f"Fórmula de {onde}: {e}")
    existentes = {c["nome"].casefold(): c["nome"] for c in (produto.campos_especificacao or [])}
    faltam = sorted(u for u in usados if u not in existentes)
    if faltam:
        lista = ", ".join(existentes.values()) or "nenhum campo cadastrado"
        raise HTTPException(422, f"Fórmula de {onde}: o produto não tem o campo «{faltam[0]}». Campos do produto: {lista}.")


def _coagir(onde: str, campo: str, v: float, texto: str) -> float | int:
    lo, hi, estrito, inteiro = fm.LIMITES[campo]
    r = math.floor(v + 0.5) if inteiro else round(v, 3 if campo == "quantidade" else 4)
    if (r <= lo if estrito else r < lo) or r > hi:
        raise HTTPException(422, f"{onde}: «{campo}» deu {v:g} com a fórmula ={texto}. Confira as medidas do pedido.")
    return int(r) if inteiro else r


def _avaliar(produto, vals, texto: str, onde: str, campo: str, estrito: bool, pendentes: list, usados: set):
    """None = não aplicável agora (campo do pedido ainda sem valor, só na pré-visualização)."""
    try:
        no = fm.compilar(texto)
    except fm.FormulaErro as e:
        raise HTTPException(422, f"Fórmula de {onde}: {e}")
    usados |= fm.campos_usados(no)
    try:
        return _coagir(onde, campo, fm.avaliar(no, vals), texto)
    except fm.FaltaValor as e:
        if not estrito:
            pendentes.append({"onde": onde, "campo": campo, "falta": e.campo})
            return None
        raise HTTPException(422, f"{onde}: {e}")
    except fm.FormulaErro as e:
        raise HTTPException(422, f"Fórmula de {onde} ({campo}): {e}")


def montar_estrutura(produto: Produto, base: dict, espec: dict, *, estrito: bool = True) -> tuple[dict, dict]:
    """Peças e ligações do PEDIDO: o modelo base com as fórmulas calculadas para estas medidas.
    `estrito=False` (pré-visualização): fórmula que usa campo ainda vazio fica com o valor de partida e vai para `pendentes`."""
    vals = valores_para_formulas(produto, espec)
    usados: set[str] = set()
    pendentes: list[dict] = []
    avisos: list[str] = []
    comps = []
    for c in base["componentes"]:
        n, f = dict(c), dict(c.get("formulas") or {})
        for campo, texto in f.items():
            v = _avaliar(produto, vals, texto, f"Peça «{c['nome']}»", campo, estrito, pendentes, usados)
            if v is not None:
                n[campo] = v
        if any(k in f for k in _DIMENSOES) and c.get("peso_kg") is not None and "peso_kg" not in f:
            n["peso_kg"] = None  # peso fixo não acompanha o tamanho: o sistema volta a estimar por material e medidas
            avisos.append(f"O peso fixo de «{c['nome']}» foi desconsiderado: as medidas variam com o pedido, então o peso é estimado por material e medidas.")
        comps.append(n)
    ligs = []
    for l in base["ligacoes"]:
        n = dict(l)
        if l.get("formula_fixadores"):
            v = _avaliar(produto, vals, l["formula_fixadores"], f"Ligação «{l['componente']}» → «{l.get('ligado_a') or 'conjunto'}»", "fixadores", estrito, pendentes, usados)
            if v is not None:
                n["fixadores"] = v
        ligs.append(n)
    return {"componentes": comps, "ligacoes": ligs}, {"usados": usados, "avisos": avisos, "pendentes": pendentes}


def _chave_lig(l: dict):
    return (l["componente"].casefold(), (l.get("ligado_a") or "").casefold(), l.get("metodo"))


def _g(v) -> str:
    return "vazio" if v is None else f"{v:g}"


def _igual(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) < 1e-6


def comparar(montada: dict, enviada: dict) -> tuple[list[str], bool]:
    """(ajustes manuais sobre campos que TÊM fórmula, houve alguma edição manual?) da estrutura enviada contra a calculada."""
    ajustes, editou = [], False
    por_nome = {c["nome"].casefold(): c for c in montada["componentes"]}
    editou = {c["nome"].casefold() for c in enviada["componentes"]} != set(por_nome)
    for c in enviada["componentes"]:
        m = por_nome.get(c["nome"].casefold())
        if m is None:
            continue
        for k in fm.CAMPOS_FORMULA:
            novo, calc = c.get(k), m.get(k)
            if k == "quantidade":
                novo = novo if novo is not None else 1.0
            if k == "furos":
                novo = novo if novo is not None else 0
            if not _igual(novo, calc):
                editou = True
                if k in (m.get("formulas") or {}):
                    ajustes.append(f"Ajuste manual: «{c['nome']}» {k} = {_g(novo)} (a fórmula dava {_g(calc)}).")
    lm = {_chave_lig(l): l for l in montada["ligacoes"]}
    le = {_chave_lig(l): l for l in enviada["ligacoes"]}
    if set(lm) != set(le):
        editou = True
    for chave, l in le.items():
        m = lm.get(chave)
        if m is not None and l.get("fixadores") != m.get("fixadores"):
            editou = True
            if m.get("formula_fixadores"):
                ajustes.append(f"Ajuste manual: ligação «{l['componente']}» → «{l.get('ligado_a') or 'conjunto'}» com {l['fixadores']} fixador(es) (a fórmula dava {m['fixadores']}).")
    return ajustes, editou


def aviso_medidas_soltas(produto: Produto, espec: dict, usados: set[str], editou: bool) -> list[str]:
    """Medida numérica informada que não alimenta nenhuma peça: o tempo não varia com o tamanho (e ninguém ajustou à mão)."""
    soltas = [c["nome"] for c in (produto.campos_especificacao or [])
              if c["tipo"] == "numero" and c["nome"] in espec and c["nome"].casefold() not in usados]
    if not soltas or editou:
        return []
    return [f"As medidas informadas ({', '.join(soltas)}) não estão ligadas a nenhuma peça: o tempo padrão NÃO muda com o tamanho. "
            "Ligue as peças às medidas no produto (ex.: ={Altura})."]
