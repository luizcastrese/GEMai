"""Tolerâncias constantes da OIT (necessidades pessoais e fadiga básica): sempre se aplicam."""
from .. import modelo_tempo as mt
from .base import ContextoTolerancia, Saida, Tolerancia, fonte

FONTE_OIT = "OIT, Introduction to Work Study (valor único, sem distinção por sexo); conferido em fonte secundária"


@fonte("oit_constantes")
def oit_constantes(ctx: ContextoTolerancia) -> Saida:
    return Saida(itens=[
        Tolerancia("necessidades pessoais", mt.REFERENCIAS["tolerancia_pessoal_pct"], FONTE_OIT, justificativa="Tolerância constante para necessidades pessoais."),
        Tolerancia("fadiga básica", mt.REFERENCIAS["fadiga_basica_pct"], FONTE_OIT, justificativa="Tolerância constante de fadiga básica.")])
