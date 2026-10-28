"""Tolerâncias como FONTES PLUGÁVEIS. Cada fonte olha as condições (local, perfil, carga, postura…) e devolve itens
{categoria, percentual, fonte, premissa?}.

Regras que o código impõe (não só a documentação):
- percentual só existe COM fonte (norma/método verificável); sem fonte não há percentual — o item vira alerta;
- uma conversão que não é da norma (ex.: LI → % de fadiga) vai rotulada em `premissa`, nunca escondida;
- dado faltante vira pendência, nunca um valor;
- ninguém digita tolerância, e a fadiga de turno fica FORA do cálculo até ser aprendida de dados.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

FADIGA_DE_TURNO = ("Fadiga ao longo do turno: fora do cálculo. Não há campo para digitar e não há fonte verificável de coeficiente; "
                   "só entra quando for aprendida dos dados reais (apontamentos).")


@dataclass(frozen=True)
class Tolerancia:
    categoria: str
    percentual: float | None  # % do tempo normal; None = só alerta, não altera o tempo
    fonte: str = ""
    premissa: str | None = None  # conversão/hipótese que NÃO é da norma
    justificativa: str = ""

    def __post_init__(self):
        if self.percentual is not None:
            if not self.fonte.strip():
                raise ValueError(f"Tolerância '{self.categoria}' com percentual exige fonte verificável.")
            if self.percentual < 0:
                raise ValueError("Percentual de tolerância não pode ser negativo.")

    def como_dict(self) -> dict:
        d = {"categoria": self.categoria, "percentual": self.percentual, "fonte": self.fonte, "justificativa": self.justificativa}
        if self.premissa:
            d["premissa"] = self.premissa
        return d


@dataclass
class ContextoTolerancia:
    """Condições em que o trabalho acontece. Tudo opcional: o que falta vira pendência da fonte que precisa dele."""
    locais: list = field(default_factory=list)  # Espaco (temperatura_c, umidade_pct, ruido_db, iluminancia_lux, nome)
    perfil: Any = None  # PerfilMaoDeObra (limite_energetico_kcal_min)
    levantamento: dict | None = None  # parâmetros NIOSH
    carga_kg: float | None = None
    gasto_energetico_kcal_min: float | None = None
    postura: str | None = None


@dataclass
class Resultado:
    aplicadas: list[dict] = field(default_factory=list)  # só as com percentual (entram no FT)
    alertas: list[dict] = field(default_factory=list)  # {msg, categoria, fonte}
    pendencias: list[str] = field(default_factory=list)
    premissas: list[str] = field(default_factory=list)

    @property
    def percentual_total(self) -> float:
        return round(sum(t["percentual"] for t in self.aplicadas), 3)


@dataclass
class Saida:
    """O que UMA fonte devolveu."""
    itens: list[Tolerancia] = field(default_factory=list)
    alertas: list[dict] = field(default_factory=list)
    pendencias: list[str] = field(default_factory=list)
    premissas: list[str] = field(default_factory=list)


Fonte = Callable[[ContextoTolerancia], Saida]
FONTES: dict[str, Fonte] = {}


def fonte(nome: str):
    """Registra uma fonte plugável (ordem de registro = ordem de aplicação)."""
    def deco(f: Fonte) -> Fonte:
        FONTES[nome] = f
        return f
    return deco


def calcular(ctx: ContextoTolerancia | None = None, *, apenas: tuple[str, ...] | None = None) -> Resultado:
    ctx = ctx or ContextoTolerancia()
    r = Resultado()
    for nome, f in FONTES.items():
        if apenas is not None and nome not in apenas:
            continue
        s = f(ctx)
        for t in s.itens:
            if t.percentual is None:
                r.alertas.append({"msg": t.justificativa or t.categoria, "categoria": "seguranca", "fonte": t.fonte or nome})
            elif t.percentual > 0:
                r.aplicadas.append(t.como_dict())
        r.alertas += s.alertas
        r.pendencias += s.pendencias
        r.premissas += s.premissas
    r.premissas.append(FADIGA_DE_TURNO)
    r.premissas = list(dict.fromkeys(r.premissas))
    r.pendencias = list(dict.fromkeys(r.pendencias))
    return r
