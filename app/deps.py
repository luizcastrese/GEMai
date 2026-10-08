"""Autenticação, autorização e escopo multiempresa/unidade.

Regra de ouro: nenhuma consulta de negócio é feita fora de `Ctx`, que sempre
filtra por empresa e (para perfis não-admin) pelas unidades atribuídas.
Recurso de outra empresa/unidade responde 404 (não vaza existência).
"""
from datetime import datetime, timezone
from typing import Any, Type

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit as _audit
from .database import get_db
from .models import Empresa, Unidade, Usuario, UsuarioUnidade
from .ratelimit import ip_cliente
from .security import decodificar_token

_bearer = HTTPBearer(auto_error=False)
NAO_ENCONTRADO = HTTPException(404, "Registro não encontrado.")


class Ctx:
    def __init__(self, db: Session, usuario: Usuario, empresa: Empresa, ip: str):
        self.db, self.usuario, self.empresa, self.ip = db, usuario, empresa, ip
        self.empresa_id = usuario.empresa_id
        self.perfil = usuario.perfil
        self.eh_admin = usuario.perfil == "admin"
        self.eh_gestor = usuario.perfil in ("admin", "gestor")
        if self.eh_admin:
            self.unidades: set[int] | None = None  # todas da empresa
        else:
            self.unidades = {
                u for (u,) in db.execute(
                    select(UsuarioUnidade.unidade_id).where(UsuarioUnidade.usuario_id == usuario.id)
                )
            }

    # ------------------------------------------------------------- escopo
    def pode_unidade(self, unidade_id: int | None) -> bool:
        return unidade_id is not None and (self.unidades is None or unidade_id in self.unidades)

    def ids_unidades(self) -> list[int]:
        """IDs de unidades acessíveis (ativas ou não) da empresa."""
        q = select(Unidade.id).where(Unidade.empresa_id == self.empresa_id)
        if self.unidades is not None:
            q = q.where(Unidade.id.in_(self.unidades or {-1}))
        return [i for (i,) in self.db.execute(q)]

    def exige_unidade(self, unidade_id: int) -> Unidade:
        u = self.db.get(Unidade, unidade_id)
        if not u or u.empresa_id != self.empresa_id or not self.pode_unidade(u.id):
            raise NAO_ENCONTRADO
        return u

    def query(self, Model):
        q = select(Model).where(Model.empresa_id == self.empresa_id)
        if hasattr(Model, "unidade_id") and self.unidades is not None:
            q = q.where(Model.unidade_id.in_(self.unidades or {-1}))
        return q

    def obter(self, Model: Type, id_: int) -> Any:
        obj = self.db.get(Model, id_)
        if obj is None or obj.empresa_id != self.empresa_id:
            raise NAO_ENCONTRADO
        uid = getattr(obj, "unidade_id", None)
        if hasattr(Model, "unidade_id") and not self.pode_unidade(uid):
            raise NAO_ENCONTRADO
        return obj

    def obter_filho(self, Model: Type, id_: int, PaiModel: Type, fk: str) -> Any:
        """Obtém um registro sem unidade própria (etapa, operação…) validando pelo pai."""
        obj = self.db.get(Model, id_)
        if obj is None or obj.empresa_id != self.empresa_id:
            raise NAO_ENCONTRADO
        self.obter(PaiModel, getattr(obj, fk))
        return obj

    # ------------------------------------------------------------- auditoria
    def auditar(self, acao: str, entidade: str, entidade_id: int | None = None,
                antes: dict | None = None, depois: dict | None = None) -> None:
        _audit.registrar(self.db, self.empresa_id, self.usuario.id, acao, entidade,
                         entidade_id, antes, depois, self.ip)


def get_ctx(request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
            db: Session = Depends(get_db)) -> Ctx:
    erro = HTTPException(401, "Não autenticado.", headers={"WWW-Authenticate": "Bearer"})
    if cred is None:
        raise erro
    payload = decodificar_token(cred.credentials)
    if not payload:
        raise erro
    try:
        usuario = db.get(Usuario, int(payload["sub"]))
    except (ValueError, TypeError):
        raise erro
    if not usuario or not usuario.ativo or usuario.token_versao != payload["tv"]:
        raise erro
    empresa = db.get(Empresa, usuario.empresa_id)
    if not empresa or not empresa.ativa:
        raise erro
    return Ctx(db, usuario, empresa, ip_cliente(request))


def requer(*perfis: str):
    def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        if ctx.perfil not in perfis:
            raise HTTPException(403, "Seu perfil não permite esta ação.")
        return ctx
    return dep


requer_admin = requer("admin")
requer_gestor = requer("admin", "gestor")
qualquer = get_ctx


def agora() -> datetime:
    return datetime.now(timezone.utc)
