"""Fachada de IA: escolhe o provedor e garante fallback local.

Regra principal do projeto: IA sugere, sistema valida. Esta camada só devolve
objetos validados/saneados; quem persiste (routers) grava como RecomendacaoIA pendente.
"""
from __future__ import annotations

import logging

from ...config import get_settings
from ...models import Empresa
from ..modelo_tempo import ModeloTempoIA, sanear_modelo
from . import claude, heuristica
from .esquemas import (AnaliseTexto, EstruturaProposta, ListaPerguntas, PerguntaIA,
                       sanear_analise, sanear_estrutura, sanear_perguntas)

log = logging.getLogger("erp.ia")


def provedor_ativo(empresa: Empresa) -> str:
    s = get_settings()
    if s.ia_provedor == "heuristica":
        return heuristica.NOME
    if claude.disponivel() and empresa.permite_ia_externa:
        return claude.NOME
    return heuristica.NOME


def _executar(empresa: Empresa, fn: str, *args):
    """Tenta o provedor externo; em qualquer falha recai no local e registra o motivo."""
    if provedor_ativo(empresa) == claude.NOME:
        try:
            return getattr(claude, fn)(*args), f"claude:{get_settings().ia_modelo}", ""
        except Exception as exc:  # rede, cota, recusa, schema inválido…
            log.warning("Falha no provedor Claude (%s): %s", fn, type(exc).__name__)
            return getattr(heuristica, fn)(*args), heuristica.NOME, \
                "O provedor de IA externo falhou; foi usado o provedor local."
    return getattr(heuristica, fn)(*args), heuristica.NOME, ""


def gerar_perguntas(empresa: Empresa, ctx: dict) -> tuple[list[PerguntaIA], str, str]:
    r, prov, aviso = _executar(empresa, "gerar_perguntas", ctx)
    return sanear_perguntas(r, ctx.get("max", 12)), prov, aviso


def estruturar(empresa: Empresa, ctx: dict) -> tuple[EstruturaProposta, str, str]:
    r, prov, aviso = _executar(empresa, "estruturar", ctx)
    return sanear_estrutura(r), prov, aviso


def analisar(empresa: Empresa, tipo: str, fatos: dict) -> tuple[AnaliseTexto, str, str]:
    r, prov, aviso = _executar(empresa, "analisar", tipo, fatos)
    return sanear_analise(r), prov, aviso


def modelar_tempo(empresa: Empresa, ctx: dict) -> tuple[ModeloTempoIA, str, str]:
    r, prov, aviso = _executar(empresa, "modelar", ctx)
    return sanear_modelo(r), prov, aviso
