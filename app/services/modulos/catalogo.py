"""Catálogo FECHADO de módulos. A IA só pode escolher chaves daqui; nada fora do catálogo é executado."""
from __future__ import annotations

from typing import Literal

from . import conferencia, montagem, movimentacao, usinagem
from .base import Modulo

CATALOGO: dict[str, Modulo] = {m.chave: m for m in (
    movimentacao.MODULO, usinagem.CORTE, usinagem.BORDO, usinagem.FURACAO, montagem.MODULO, conferencia.MODULO)}
CHAVES = tuple(CATALOGO)
ChaveModulo = Literal["movimentacao", "corte", "bordo", "furacao", "montagem", "conferencia"]
assert set(ChaveModulo.__args__) == set(CHAVES)  # o tipo (usado no esquema da IA) acompanha o catálogo


def obter(chave: str) -> Modulo | None:
    return CATALOGO.get(chave)


def resumo_para_ia() -> list[dict]:
    """Só nomes, unidades e descrições: nenhum valor de tempo ou coeficiente é exposto à IA."""
    return [m.resumo() for m in CATALOGO.values()]
