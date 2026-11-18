"""Registro de módulos: PACOTES embutidos (o primeiro é o de marcenaria) + módulos criados pela EMPRESA (por necessidade).

A IA só escolhe chaves do catálogo da empresa (embutidos + módulos VALIDADOS por uma pessoa); nada fora dele é executado.
Um módulo da empresa é uma especificação de arquétipo (`arquetipos.EspecModulo`), nunca minutos digitados.
"""
from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import arquetipos, conferencia, montagem, movimentacao, usinagem
from .base import Modulo

log = logging.getLogger("erp.modulos")

# Pacote "marcenaria" (v1): o primeiro pacote, usado na validação de campo. Os números ficam congelados por testes de regressão.
PACOTES: dict[str, dict[str, Modulo]] = {
    "marcenaria": {m.chave: m for m in (movimentacao.MODULO, usinagem.CORTE, usinagem.BORDO, usinagem.FURACAO, montagem.MODULO,
                                        conferencia.MODULO)},
}
CATALOGO: dict[str, Modulo] = {k: m for p in PACOTES.values() for k, m in p.items()}  # embutidos
CHAVES = tuple(CATALOGO)
CHAVE_PATTERN = r"^[a-z][a-z0-9_]{1,29}$"
# Tipo da chave nos esquemas: qualquer chave bem formada; QUEM decide se ela existe é o catálogo da empresa (validação na borda).
ChaveModulo = Annotated[str, Field(pattern=CHAVE_PATTERN, max_length=30)]


def modulos_da_empresa(db: Session | None, empresa_id: int | None, *, so_validados: bool = True) -> list:
    """Linhas `ModuloEmpresa` vigentes (validadas) da empresa; com `so_validados=False`, a última versão de cada chave."""
    if db is None or empresa_id is None:
        return []
    from ...models import ModuloEmpresa
    q = select(ModuloEmpresa).where(ModuloEmpresa.empresa_id == empresa_id)
    if so_validados:
        q = q.where(ModuloEmpresa.vigente.is_(True), ModuloEmpresa.status == "validado")
    ultimas: dict[str, object] = {}
    for r in db.scalars(q.order_by(ModuloEmpresa.chave, ModuloEmpresa.versao)):
        ultimas[r.chave] = r
    return list(ultimas.values())


def modulo_de_linha(row) -> Modulo | None:
    try:
        return arquetipos.construir(arquetipos.EspecModulo.model_validate(row.espec), versao=row.versao)
    except Exception as exc:  # especificação gravada inválida: não executa, registra
        log.warning("Módulo da empresa %s inválido: %s", row.chave, exc)
        return None


def da_empresa(db: Session | None, empresa_id: int | None) -> dict[str, Modulo]:
    """Catálogo efetivo da empresa: embutidos + módulos validados (um módulo da empresa NÃO substitui um embutido)."""
    out = dict(CATALOGO)
    for r in modulos_da_empresa(db, empresa_id):
        if r.chave in out:
            continue
        m = modulo_de_linha(r)
        if m is not None:
            out[r.chave] = m
    return out


def obter(chave: str, db: Session | None = None, empresa_id: int | None = None) -> Modulo | None:
    if chave in CATALOGO:
        return CATALOGO[chave]
    if not chave or db is None:
        return None
    return da_empresa(db, empresa_id).get(chave)


def resumo_para_ia(db: Session | None = None, empresa_id: int | None = None) -> list[dict]:
    """Só nomes, unidades e descrições: nenhum valor de tempo ou coeficiente é exposto à IA."""
    return [m.resumo() for m in da_empresa(db, empresa_id).values()]


def parametros_ficha_extras(db: Session | None, empresa_id: int | None) -> dict:
    """Parâmetros de ficha técnica declarados pelos módulos VALIDADOS da empresa (nome → ParametroFicha)."""
    from .ficha import ParametroFicha
    out = {}
    for r in modulos_da_empresa(db, empresa_id):
        t = (r.espec or {}).get("taxa")
        if t:
            funcao = (r.espec or {}).get("funcao_meio") or ""
            out[t["nome"]] = ParametroFicha(t["nome"], t["unidade"], t["descricao"], float(t["minimo"]), float(t["maximo"]),
                                            (funcao,) if funcao else ())
    return out
