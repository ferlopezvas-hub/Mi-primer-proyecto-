"""Hash de contraseñas (Argon2id), JWT de acceso y tokens opacos."""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings

_ph = PasswordHasher()  # Argon2id con parámetros recomendados por la librería


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def validate_password_strength(password: str) -> str | None:
    s = get_settings()
    if len(password) < s.min_password_length:
        return f"La contraseña debe tener al menos {s.min_password_length} caracteres"
    if password.lower() == password or password.upper() == password or not any(c.isdigit() for c in password):
        return "La contraseña debe combinar mayúsculas, minúsculas y números"
    return None


def create_access_token(user_id: int, role: str, token_version: int) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    s = get_settings()
    data = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub"]})
    if data.get("type") != "access":
        raise jwt.InvalidTokenError("tipo de token incorrecto")
    return data


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
