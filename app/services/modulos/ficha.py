"""Catálogo da FICHA TÉCNICA dos meios: quais parâmetros técnicos cada tipo de meio tem, em que unidade e faixa plausível.

Esses parâmetros (avanço, velocidade, cabeçotes, curso, capacidade de carga…) alimentam os módulos de tempo. NÃO são
tempos: são características do equipamento, vindas de ficha técnica (informadas por uma pessoa ou achadas em busca na
web e VALIDADAS por uma pessoa). As faixas abaixo existem só para barrar valores absurdos na entrada (validação de
plausibilidade); não são coeficientes de tempo.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParametroFicha:
    nome: str
    unidade: str
    descricao: str
    minimo: float
    maximo: float
    funcoes: tuple[str, ...]  # funções de meio a que se aplica
    inteiro: bool = False


PARAMETROS_FICHA: dict[str, ParametroFicha] = {p.nome: p for p in (
    ParametroFicha("avanco_corte_m_min", "m/min", "Avanço (velocidade) de corte", 0.05, 300, ("corte",)),
    ParametroFicha("espessura_max_corte_mm", "mm", "Espessura máxima de corte", 1, 300, ("corte",)),
    ParametroFicha("velocidade_bordo_m_min", "m/min", "Velocidade de alimentação da coladeira de borda", 0.1, 100, ("bordo",)),
    ParametroFicha("cabecotes_furacao", "un", "Cabeçotes de furação", 1, 200, ("furacao",), inteiro=True),
    ParametroFicha("curso_furacao_mm", "mm", "Curso do ciclo de furação", 1, 500, ("furacao",)),
    ParametroFicha("avanco_furacao_mm_min", "mm/min", "Avanço de furação", 1, 20000, ("furacao",)),
    ParametroFicha("velocidade_meio_m_min", "m/min", "Velocidade do meio de movimentação", 1, 400, ("movimentacao",)),
    ParametroFicha("capacidade_carga_kg", "kg", "Capacidade de carga do meio de movimentação", 1, 50000, ("movimentacao",)),
)}

# Conversões simples e inequívocas entre unidades do mesmo tipo de grandeza (origem → destino: fator multiplicativo).
_CONVERSOES = {("m/s", "m/min"): 60.0, ("mm/s", "mm/min"): 60.0, ("mm/min", "m/min"): 0.001, ("m/min", "mm/min"): 1000.0,
               ("km/h", "m/min"): 1000 / 60, ("t", "kg"): 1000.0, ("m", "mm"): 1000.0, ("cm", "mm"): 10.0}


def _norm(u: str) -> str:
    return (u or "").strip().lower().replace(" ", "").replace("·", "").replace("per", "/").replace("por", "/")


def converter(valor: float, unidade_origem: str, unidade_destino: str) -> float | None:
    """Converte `valor` para a unidade do catálogo; None se a unidade for desconhecida (rejeitar, nunca adivinhar)."""
    o, d = _norm(unidade_origem), _norm(unidade_destino)
    if o == d:
        return valor
    f = _CONVERSOES.get((o, d))
    return None if f is None else valor * f


def validar_valor(nome: str, valor: float, unidade: str | None = None) -> tuple[float | None, str | None]:
    """(valor na unidade do catálogo, motivo da rejeição). Valida o nome, a unidade e a faixa plausível."""
    p = PARAMETROS_FICHA.get(nome)
    if p is None:
        return None, "parâmetro fora do catálogo da ficha técnica"
    if isinstance(valor, bool) or valor != valor or valor in (float("inf"), float("-inf")):
        return None, "valor inválido"
    v = valor if unidade is None else converter(float(valor), unidade, p.unidade)
    if v is None:
        return None, f"unidade '{unidade}' inválida (esperado {p.unidade})"
    if not (p.minimo <= v <= p.maximo):
        return None, f"valor {v:g} {p.unidade} fora da faixa plausível ({p.minimo:g}–{p.maximo:g})"
    if p.inteiro and abs(v - round(v)) > 1e-9:
        return None, "deve ser um número inteiro"
    return (float(round(v)) if p.inteiro else float(v)), None


def aplicaveis(funcao: str) -> list[ParametroFicha]:
    """Parâmetros da ficha de um meio com a função dada (vazio = todos, para meios ainda sem função)."""
    return [p for p in PARAMETROS_FICHA.values() if not funcao or funcao in p.funcoes]


def url_de_fonte(url: str | None) -> str | None:
    """Aceita só http(s) simples (sem credenciais, espaços ou controle); devolve a URL ou None."""
    from urllib.parse import urlsplit
    if not url or len(url) > 500 or any(ord(c) < 33 or ord(c) == 127 for c in url):
        return None
    try:
        u = urlsplit(url)
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
        return None
    return url
