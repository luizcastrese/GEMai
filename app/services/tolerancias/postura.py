"""Postura: PONTO DE EXTENSÃO para um método de avaliação postural (RULA, REBA, OWAS…).

Nenhum método está implementado: o RULA (McAtamney & Corlett, 1993) só pode entrar com as tabelas ORIGINAIS conferidas, e elas não foram
verificadas nesta base — implementar de memória é proibido. Quando existir, o método é registrado com `@fonte("rula")` devolvendo
`Tolerancia(..., fonte="McAtamney & Corlett (1993)", premissa="conversão score→% é premissa do sistema")`.
"""
from .base import ContextoTolerancia, Saida, fonte

POSTURA_AVALIADA = False  # vira True só quando um método verificado estiver registrado


@fonte("postura")
def postura(ctx: ContextoTolerancia) -> Saida:
    s = Saida()
    if ctx.postura:
        s.premissas.append(f"Postura de trabalho ('{ctx.postura}') registrada, mas sem método de avaliação postural verificado (RULA não implementado): não altera o tempo.")
    return s
