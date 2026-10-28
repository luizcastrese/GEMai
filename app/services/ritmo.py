"""Ritmo efetivo de uma pessoa (fonte única da regra de precedência).

Precedência: `pessoa.ritmo_pct` (informado ou calibrado) > `perfil.ritmo_pct` do perfil da pessoa > 100.
Quando nada é conhecido, 100 é usado MAS sinalizado (`origem == "padrao"`), para que quem consome possa avisar
que não houve normalização, em vez de esconder o valor padrão.

O ritmo individual é dado de DESEMPENHO pessoal (LGPD): serve só para normalizar o histórico de tempos.
Não é ranking nem avaliação da pessoa.
"""
from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PerfilMaoDeObra, Pessoa
from .modelo_tempo import RITMO_MAX, RITMO_MIN

PADRAO = 100.0


class RitmoEfetivo(NamedTuple):
    valor: float
    origem: str  # "pessoa" | "perfil" | "padrao"

    @property
    def conhecido(self) -> bool:
        return self.origem != "padrao"


def _limitar(v: float) -> float:
    return min(max(float(v), RITMO_MIN), RITMO_MAX)


def ritmo_efetivo(pessoa: Pessoa | None, perfil: PerfilMaoDeObra | None) -> RitmoEfetivo:
    if pessoa is not None and pessoa.ritmo_pct is not None:
        return RitmoEfetivo(_limitar(pessoa.ritmo_pct), "pessoa")
    if perfil is not None and perfil.ritmo_pct is not None:
        return RitmoEfetivo(_limitar(perfil.ritmo_pct), "perfil")
    return RitmoEfetivo(PADRAO, "padrao")


def ritmos_das_pessoas(db: Session, empresa_id: int, pessoa_ids: set[int]) -> dict[int, RitmoEfetivo]:
    """Ritmo efetivo de cada pessoa da empresa (uma consulta de pessoas e uma de perfis)."""
    if not pessoa_ids:
        return {}
    pessoas = list(db.scalars(select(Pessoa).where(Pessoa.empresa_id == empresa_id, Pessoa.id.in_(pessoa_ids))))
    perfil_ids = {p.perfil_id for p in pessoas if p.perfil_id}
    perfis = {pf.id: pf for pf in db.scalars(select(PerfilMaoDeObra).where(
        PerfilMaoDeObra.empresa_id == empresa_id, PerfilMaoDeObra.id.in_(perfil_ids)))} if perfil_ids else {}
    return {p.id: ritmo_efetivo(p, perfis.get(p.perfil_id)) for p in pessoas}
