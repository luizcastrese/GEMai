"""Tipos comuns dos módulos de tempo.

Um MÓDULO declara os parâmetros (condições) de que precisa e, dado um `EntradaModulo` montado PELO SISTEMA a partir
do produto, dos meios cadastrados e do ambiente, devolve elementos de vocabulário FECHADO (`fixo`, `linear_driver`,
`deslocamento`, `indices_most`). Quem calcula minutos é `modelo_tempo.calcular`; o módulo só decide os elementos e os
valores deles a partir de condições e de coeficientes do catálogo. Falta de dado vira pendência (`faltantes`),
nunca um valor escondido.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .coeficientes import Coeficiente


@dataclass(frozen=True)
class ParametroModulo:
    nome: str
    unidade: str
    descricao: str
    origem: str  # produto | meio | ambiente | pedido  (de onde o SISTEMA tira o valor)
    obrigatorio: bool = True
    efeito_no_tempo: bool = True  # False = é registrado/usado em alertas, mas ainda sem coeficiente com fonte


@dataclass
class EntradaModulo:
    """Condições de um passo, montadas pelo sistema. Nenhum campo é tempo."""

    quantidade: float = 1.0  # unidades de contagem do módulo (peças ou unidades do produto)
    unidades_produto: float = 1.0  # N do plano/ordem
    pessoas: int = 1
    componentes: list[dict] = field(default_factory=list)  # nome, qtd, material, comp, larg, esp, peso_kg, furos, bordas_m
    ligacoes: list[dict] = field(default_factory=list)  # metodo, fixadores
    distancia_m: float | None = None
    origem_nome: str | None = None
    destino_nome: str | None = None
    recurso_nome: str | None = None
    ficha: dict[str, float] = field(default_factory=dict)  # parâmetros técnicos VALIDADOS do meio (Parametro/recurso)
    meio_nome: str | None = None  # meio de movimentação
    ficha_meio: dict[str, float] = field(default_factory=dict)
    piso: str = ""
    extras: dict = field(default_factory=dict)  # condições específicas de uma operação (ex.: furos por peça)

    @property
    def peso_medio_kg(self) -> float | None:
        """Peso médio das peças com peso conhecido, ponderado pela quantidade (define quantas cabem por viagem)."""
        com_peso = [(c["peso_kg"], c["qtd"]) for c in self.componentes if c.get("peso_kg")]
        total = sum(q for _, q in com_peso)
        return sum(p * q for p, q in com_peso) / total if total else None

    @property
    def peso_max_kg(self) -> float | None:
        pesos = [c["peso_kg"] for c in self.componentes if c.get("peso_kg")]
        return max(pesos) if pesos else None


@dataclass
class Montagem:
    """O que um módulo produz antes do cálculo."""

    elementos: list[dict] = field(default_factory=list)
    parametros: dict = field(default_factory=dict)  # condições efetivamente usadas (rastreabilidade)
    coeficientes: list[Coeficiente] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)
    premissas: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    pessoas_minimas: int | None = None


@dataclass(frozen=True)
class Modulo:
    chave: str
    titulo: str
    tipo_passo: str  # movimentacao | corte | furacao | bordo | montagem | inspecao (rótulo do passo)
    unidade_contagem: str  # peca | unidade_produto
    parametros: tuple[ParametroModulo, ...]
    montar: Callable[[EntradaModulo], Montagem]
    versao: int = 1
    precisa_recurso: bool = False
    descricao: str = ""

    def resumo(self) -> dict:
        """Descrição para a IA e para a tela: só nomes e unidades, nenhum valor de tempo."""
        return {"chave": self.chave, "titulo": self.titulo, "descricao": self.descricao, "unidade_contagem": self.unidade_contagem,
                "precisa_recurso": self.precisa_recurso,
                "parametros": [{"nome": p.nome, "unidade": p.unidade, "descricao": p.descricao, "origem": p.origem,
                                "obrigatorio": p.obrigatorio} for p in self.parametros]}


def el(nome: str, tipo: str, metodo: str = "fixo", **kw) -> dict:
    """Elemento de tempo (vocabulário fechado) com os mesmos campos de `modelo_tempo.ElementoTempo`."""
    base = {"nome": nome, "tipo": tipo, "metodo": metodo, "indices_most": [], "depende_operador": True, "por_unidade": False,
            "driver": "nenhum", "a_min": 0.0, "b_min": 0.0, "velocidade_m_min": None, "itens_por_viagem": None,
            "ida_e_volta": True, "paralelizavel": False, "justificativa": ""}
    base.update(kw)
    return base
