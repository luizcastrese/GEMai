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
from .esquemas import (AnaliseTexto, EstruturaProdutoIA, EstruturaProposta, FichaTecnicaIA, IdentificacaoMeio, ListaPerguntas,
                       PerguntaIA, PlanoProposta, SugestaoModulo, ExplicacaoArranjos, sanear_explicacao, sanear_sugestao_modulo, sanear_identificacao, sanear_analise, sanear_estrutura, sanear_estrutura_produto, sanear_perguntas, sanear_plano)

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


def interpretar_produto(empresa: Empresa, ctx: dict) -> tuple[EstruturaProdutoIA, str, str]:
    r, prov, aviso = _executar(empresa, "interpretar_produto", ctx)
    return sanear_estrutura_produto(r), prov, aviso


def planejar(empresa: Empresa, ctx: dict) -> tuple[PlanoProposta, str, str]:
    r, prov, aviso = _executar(empresa, "planejar", ctx)
    return sanear_plano(r), prov, aviso


def externa_disponivel(empresa: Empresa) -> bool:
    """IA externa habilitada (chave no servidor + consentimento da empresa): exigida para foto e busca na web."""
    return provedor_ativo(empresa) == claude.NOME


def identificar_meio(empresa: Empresa, ctx: dict, imagem: tuple[bytes, str] | None = None) -> tuple[IdentificacaoMeio, str, str]:
    r, prov, aviso = _executar(empresa, "identificar_meio", ctx, imagem)
    return sanear_identificacao(r), prov, aviso


def buscar_ficha(empresa: Empresa, ctx: dict) -> tuple[FichaTecnicaIA, str, str]:
    """Busca de ficha técnica. Só o provedor externo pesquisa na web; o local devolve 'não encontrada'."""
    return _executar(empresa, "buscar_ficha", ctx)


def sugerir_modulo(empresa: Empresa, ctx: dict) -> tuple[SugestaoModulo, str, str]:
    r, prov, aviso = _executar(empresa, "sugerir_modulo", ctx)
    return sanear_sugestao_modulo(r), prov, aviso


def explicar_arranjos(empresa: Empresa, fatos: dict) -> tuple[ExplicacaoArranjos, str, str]:
    r, prov, aviso = _executar(empresa, "explicar_arranjos", fatos)
    return sanear_explicacao(r), prov, aviso
