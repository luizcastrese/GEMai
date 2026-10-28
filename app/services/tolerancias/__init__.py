"""Tolerâncias por fontes plugáveis (Fase 8). Importar o pacote registra as fontes na ordem de aplicação."""
from . import oit_constantes, niosh, murrell, ambiente, postura  # noqa: F401  (registram as fontes)
from .base import FADIGA_DE_TURNO, FONTES, ContextoTolerancia, Resultado, Saida, Tolerancia, calcular, fonte
from .oit_constantes import FONTE_OIT

__all__ = ["FADIGA_DE_TURNO", "FONTES", "FONTE_OIT", "ContextoTolerancia", "Resultado", "Saida", "Tolerancia", "calcular", "fonte"]
