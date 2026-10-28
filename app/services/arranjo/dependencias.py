"""Dependências entre os passos, derivadas da ESTRUTURA DO PRODUTO (não de uma sequência fixa).

Um passo depende do último passo anterior que mexeu em cada um dos seus componentes (cortar → colar borda → furar → levar
à montagem → montar o grupo). A montagem final depende de todas as montagens de grupo; passos sem componente
(conferência) dependem dos passos finais da cadeia. Duas cadeias de componentes sem relação podem andar em paralelo.
"""
from __future__ import annotations


def dependencias(passos: list) -> list[set[int]]:
    """Para cada passo (índice), o conjunto de índices dos passos que precisam terminar antes. `passos`: objetos com
    `componentes` (nomes), `modulo` e `final`."""
    ultimo_por_comp: dict[str, int] = {}
    com_sucessor: set[int] = set()
    out: list[set[int]] = []
    for i, p in enumerate(passos):
        comps = {c.lower() for c in p.componentes}
        preds = {ultimo_por_comp[c] for c in comps if c in ultimo_por_comp}
        if p.modulo == "montagem" and getattr(p, "final", False):
            preds |= {j for j in range(i) if passos[j].modulo == "montagem" and not getattr(passos[j], "final", False)}
        if not comps:
            preds = set(range(i)) - com_sucessor
        preds.discard(i)
        for c in comps:
            ultimo_por_comp[c] = i
        com_sucessor |= preds
        out.append(preds)
    return out
