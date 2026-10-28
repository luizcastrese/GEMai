"""Módulo `conferencia`: conferência final de acabamento, folgas e funcionamento (por unidade do produto)."""
from __future__ import annotations

from .base import EntradaModulo, Modulo, Montagem, ParametroModulo, el
from .coeficientes import coef


def montar(e: EntradaModulo) -> Montagem:
    c = coef("conferencia_final")
    m = Montagem(coeficientes=[c], parametros={"unidades": e.quantidade})
    m.elementos.append(el("Conferir acabamento, folgas e funcionamento", "inspecao", "fixo", por_unidade=True, a_min=c.valor,
                          justificativa="Referência genérica do catálogo; ajuste ao seu padrão de qualidade por calibração."))
    return m


MODULO = Modulo(
    chave="conferencia", titulo="Conferência final", tipo_passo="inspecao", unidade_contagem="unidade_produto", versao=1,
    descricao="Conferência de cada unidade do produto antes da expedição.",
    parametros=(ParametroModulo("unidades", "un", "Unidades do produto", "pedido"),), montar=montar)
