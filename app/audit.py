from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .models import AuditLog

_OCULTOS = {"senha_hash"}


def _json_safe(v: Any):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def snap(obj) -> dict:
    """Retrato das colunas de um objeto ORM, seguro para JSON (sem segredos)."""
    if obj is None:
        return {}
    return {
        c.key: _json_safe(getattr(obj, c.key))
        for c in inspect(obj).mapper.column_attrs
        if c.key not in _OCULTOS
    }


def registrar(db: Session, empresa_id: int, usuario_id: int | None, acao: str, entidade: str,
              entidade_id: int | None = None, antes: dict | None = None,
              depois: dict | None = None, ip: str = "") -> None:
    db.add(AuditLog(empresa_id=empresa_id, usuario_id=usuario_id, acao=acao, entidade=entidade,
                    entidade_id=entidade_id, antes=antes, depois=depois, ip=ip[:64]))
