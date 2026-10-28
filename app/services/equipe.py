"""Vínculo entre usuário e pessoa (quem executa).

Todo apontamento deveria dizer QUEM executou, porque o histórico é normalizado pelo ritmo da pessoa. Por isso
cada usuário ativo ganha uma `Pessoa` ativa em cada unidade em que atua (as atribuídas a ele ou, sem restrição,
todas as ativas da empresa). Tudo é idempotente e NUNCA sobrescreve: uma pessoa já vinculada (inclusive
desativada de propósito) é respeitada, e nada do cadastro existente é alterado.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Pessoa, Unidade, Usuario, UsuarioUnidade


def unidades_do_usuario(db: Session, usuario: Usuario) -> list[int]:
    """Unidades atribuídas ao usuário; sem atribuição, todas as unidades ativas da empresa."""
    atribuidas = [i for (i,) in db.execute(select(UsuarioUnidade.unidade_id).where(UsuarioUnidade.usuario_id == usuario.id))]
    if atribuidas:
        return sorted(atribuidas)
    return [i for (i,) in db.execute(select(Unidade.id).where(
        Unidade.empresa_id == usuario.empresa_id, Unidade.ativa.is_(True)).order_by(Unidade.id))]


def pessoa_vinculada(db: Session, usuario: Usuario, unidade_id: int) -> Pessoa | None:
    """Pessoa ATIVA ligada ao usuário nesta unidade, se houver."""
    return db.scalar(select(Pessoa).where(
        Pessoa.empresa_id == usuario.empresa_id, Pessoa.usuario_id == usuario.id,
        Pessoa.unidade_id == unidade_id, Pessoa.ativo.is_(True)))


def garantir_pessoa(db: Session, usuario: Usuario, unidade_id: int) -> tuple[Pessoa | None, bool]:
    """(pessoa, criada). Cria só se o usuário NÃO tem nenhuma pessoa vinculada nesta unidade;
    se a vinculada foi desativada, respeita (devolve None)."""
    if not usuario.ativo:
        return None, False
    existente = db.scalar(select(Pessoa).where(
        Pessoa.empresa_id == usuario.empresa_id, Pessoa.usuario_id == usuario.id, Pessoa.unidade_id == unidade_id))
    if existente is not None:
        return (existente if existente.ativo else None), False
    unidade = db.get(Unidade, unidade_id)
    if unidade is None or unidade.empresa_id != usuario.empresa_id:
        return None, False
    p = Pessoa(empresa_id=usuario.empresa_id, unidade_id=unidade_id, nome=usuario.nome, usuario_id=usuario.id)
    db.add(p)
    db.flush()
    return p, True


def garantir_pessoas_do_usuario(db: Session, usuario: Usuario, unidade_ids: list[int] | None = None) -> list[Pessoa]:
    """Cria as pessoas que faltam; devolve só as CRIADAS agora."""
    criadas = []
    for uid in (unidades_do_usuario(db, usuario) if unidade_ids is None else unidade_ids):
        p, nova = garantir_pessoa(db, usuario, uid)
        if nova:
            criadas.append(p)
    return criadas


def vincular_usuarios(db: Session, empresa_id: int) -> list[Pessoa]:
    """Rotina para usuários já existentes: garante a pessoa de cada usuário ativo. Devolve as criadas."""
    criadas = []
    for u in db.scalars(select(Usuario).where(Usuario.empresa_id == empresa_id, Usuario.ativo.is_(True)).order_by(Usuario.id)):
        criadas += garantir_pessoas_do_usuario(db, u)
    return criadas
