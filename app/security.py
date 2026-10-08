"""Hash de senha (Argon2id) e tokens JWT."""
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .config import get_settings

_ph = PasswordHasher()
_ISS = "erp-producao"
# Hash falso para igualar o tempo de resposta quando o e-mail não existe (evita enumeração).
_DUMMY = _ph.hash("senha-ficticia-para-tempo-constante")


def hash_senha(senha: str) -> str:
    return _ph.hash(senha)


def verificar_senha(senha: str, hash_: str | None) -> bool:
    try:
        return _ph.verify(hash_ or _DUMMY, senha) and hash_ is not None
    except (VerificationError, InvalidHashError):
        return False


def senha_precisa_rehash(hash_: str) -> bool:
    return _ph.check_needs_rehash(hash_)


def validar_forca_senha(senha: str) -> str | None:
    """Retorna mensagem de erro, ou None se a senha é aceitável."""
    minimo = get_settings().senha_minima
    if len(senha) < minimo:
        return f"A senha deve ter pelo menos {minimo} caracteres."
    if len(senha) > 128:
        return "A senha deve ter no máximo 128 caracteres."
    if senha.lower() == senha or senha.isdigit() or not any(c.isdigit() for c in senha):
        return "Use letras maiúsculas e minúsculas e pelo menos um número."
    return None


def criar_token(usuario_id: int, token_versao: int) -> tuple[str, int]:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.token_minutos)
    payload = {
        "sub": str(usuario_id), "tv": token_versao, "iss": _ISS,
        "iat": datetime.now(timezone.utc), "exp": exp,
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256"), s.token_minutos * 60


def decodificar_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token, get_settings().secret_key, algorithms=["HS256"], issuer=_ISS,
            options={"require": ["exp", "sub", "tv", "iss"]},
        )
    except jwt.PyJWTError:
        return None
