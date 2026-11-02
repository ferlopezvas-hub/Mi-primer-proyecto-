from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.access import has_access
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import AuditLog, PasswordResetToken, RefreshToken, Role, UsageEvent, User
from app.notifications.email import send_email
from app.plans import get_plan
from app.ratelimit import auth_rate_limit
from app.security import (
    create_access_token,
    hash_password,
    new_opaque_token,
    password_needs_rehash,
    sha256,
    validate_password_strength,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash ficticio para igualar tiempos cuando el email no existe (evita enumeración)
_DUMMY_HASH = hash_password("dummy-Password-123")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    full_name: str = Field(default="", max_length=120)
    accept_terms: bool


class LoginIn(BaseModel):
    email: str = Field(max_length=320)  # sin validar formato: solo se compara con cuentas existentes
    password: str = Field(max_length=256)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str


class ForgotIn(BaseModel):
    email: str = Field(max_length=320)


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(max_length=256)


def _now():
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "plan": get_plan(user.plan_code).to_dict(),
        "timezone": user.timezone,
        "created_at": user.created_at,
        "access_expires_at": user.access_expires_at,
        "access_active": has_access(user),
        "admin_contact": get_settings().admin_contact,
    }


def _issue_tokens(db: Session, user: User, family: str | None = None) -> TokenOut:
    s = get_settings()
    raw = new_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=sha256(raw),
            family=family or secrets.token_hex(8),
            expires_at=_now() + timedelta(days=s.refresh_token_days),
        )
    )
    db.commit()
    return TokenOut(
        access_token=create_access_token(user.id, user.role.value, user.token_version),
        refresh_token=raw,
        expires_in=s.access_token_minutes * 60,
    )


@router.post("/register", status_code=201, dependencies=[Depends(auth_rate_limit)])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if not body.accept_terms:
        raise HTTPException(400, "Debes aceptar los términos y la política de privacidad")
    if err := validate_password_strength(body.password):
        raise HTTPException(400, err)
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Ya existe una cuenta con ese email")
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip())
    db.add(user)
    db.flush()
    db.add(UsageEvent(user_id=user.id, kind="register"))
    db.commit()
    tokens = _issue_tokens(db, user)
    return {"user": user_out(user), "tokens": tokens}


@router.post("/login", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(401, "Email o contraseña incorrectos")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email o contraseña incorrectos")
    if not user.is_active:
        raise HTTPException(403, "Cuenta desactivada")
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = _now()
    db.add(UsageEvent(user_id=user.id, kind="login"))
    db.commit()
    return _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)])
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    tok = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(body.refresh_token)))
    if not tok:
        raise HTTPException(401, "Sesión no válida")
    if tok.revoked_at is not None:
        # Reutilización de un token rotado: posible robo -> se revoca toda la familia.
        db.execute(
            update(RefreshToken).where(RefreshToken.family == tok.family, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        db.commit()
        raise HTTPException(401, "Sesión no válida")
    if _aware(tok.expires_at) < _now():
        raise HTTPException(401, "Sesión caducada")
    user = db.get(User, tok.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Sesión no válida")
    tok.revoked_at = _now()
    db.commit()
    return _issue_tokens(db, user, family=tok.family)


@router.post("/logout", status_code=204)
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    tok = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(body.refresh_token)))
    if tok and tok.revoked_at is None:
        tok.revoked_at = _now()
        db.commit()


@router.post("/logout-all", status_code=204)
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.token_version += 1
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=_now()))
    db.commit()


@router.post("/forgot-password", status_code=202, dependencies=[Depends(auth_rate_limit)])
def forgot_password(body: ForgotIn, db: Session = Depends(get_db)):
    s = get_settings()
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.is_active:
        raw = new_opaque_token()
        db.add(PasswordResetToken(user_id=user.id, token_hash=sha256(raw),
                                  expires_at=_now() + timedelta(minutes=s.password_reset_minutes)))
        db.commit()
        link = f"{s.web_url}/reset-password?token={raw}"
        send_email(
            user.email,
            "Recupera tu contraseña - SPORT AI PREDICTOR",
            f"Hola,\n\nPara crear una nueva contraseña abre este enlace (caduca en "
            f"{s.password_reset_minutes} minutos):\n\n{link}\n\nSi no lo has solicitado, ignora este mensaje.",
        )
    # Respuesta idéntica exista o no la cuenta
    return {"detail": "Si el email está registrado, recibirás un enlace para restablecer la contraseña."}


@router.post("/reset-password", dependencies=[Depends(auth_rate_limit)])
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    tok = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == sha256(body.token)))
    if not tok or tok.used_at is not None or _aware(tok.expires_at) < _now():
        raise HTTPException(400, "Enlace no válido o caducado")
    if err := validate_password_strength(body.new_password):
        raise HTTPException(400, err)
    user = db.get(User, tok.user_id)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # invalida sesiones abiertas
    tok.used_at = _now()
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=_now()))
    db.commit()
    return {"detail": "Contraseña actualizada. Ya puedes iniciar sesión."}


class ClaimAdminIn(BaseModel):
    code: str = Field(max_length=200)


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)):
    """Indica si falta crear el primer administrador (sin datos sensibles)."""
    has_admin = db.scalar(select(User.id).where(User.role == Role.admin).limit(1)) is not None
    return {"admin_exists": has_admin, "setup_available": bool(get_settings().admin_setup_code) and not has_admin}


@router.post("/claim-admin", dependencies=[Depends(auth_rate_limit)])
def claim_admin(body: ClaimAdminIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expected = get_settings().admin_setup_code
    if len(expected) < 16:
        raise HTTPException(400, "La configuración inicial no está activada en el servidor")
    if db.scalar(select(User.id).where(User.role == Role.admin).limit(1)) is not None:
        raise HTTPException(409, "Ya existe un administrador")
    if not hmac.compare_digest(body.code.strip(), expected):
        raise HTTPException(403, "Código incorrecto")
    user.role, user.plan_code = Role.admin, "elite"
    user.token_version += 1
    db.add(AuditLog(actor_id=user.id, action="admin.claim", detail={"user_id": user.id}))
    db.commit()
    return _issue_tokens(db, user)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña actual no es correcta")
    if err := validate_password_strength(body.new_password):
        raise HTTPException(400, err)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    db.commit()
    return _issue_tokens(db, user)
