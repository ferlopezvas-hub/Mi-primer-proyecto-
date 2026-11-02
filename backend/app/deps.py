from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Role, UsageEvent, User
from app.plans import Plan, get_plan
from app.ratelimit import enforce
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="No autenticado",
    headers={"WWW-Authenticate": "Bearer"},
)


def _user_from_token(token: str, db: Session) -> User:
    try:
        data = decode_access_token(token)
    except jwt.PyJWTError:
        raise UNAUTHORIZED from None
    user = db.get(User, int(data["sub"]))
    if not user or not user.is_active or user.token_version != data.get("tv"):
        raise UNAUTHORIZED
    return user


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise UNAUTHORIZED
    user = _user_from_token(creds.credentials, db)
    enforce("user", str(user.id), get_settings().rate_limit_user_per_min)
    request.state.user_id = user.id
    return user


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if creds is None:
        return None
    try:
        return _user_from_token(creds.credentials, db)
    except HTTPException:
        return None


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol administrador")
    return user


def user_plan(user: User = Depends(get_current_user)) -> Plan:
    return get_plan(user.plan_code)


def require_feature(feature: str):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if feature not in get_plan(user.plan_code).features:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Tu plan no incluye '{feature}'")
        return user

    return _dep


def consume_prediction_view(db: Session, user: User, ref: str) -> None:
    """Aplica el límite diario de vistas detalladas de predicción del plan."""
    plan = get_plan(user.plan_code)
    since = datetime.now(UTC) - timedelta(days=1)
    if plan.prediction_views_per_day is not None:
        already = db.scalar(
            select(func.count()).select_from(UsageEvent).where(
                UsageEvent.user_id == user.id, UsageEvent.kind == "prediction_view",
                UsageEvent.ref == ref, UsageEvent.created_at >= since,
            )
        )
        if not already:
            used = db.scalar(
                select(func.count(func.distinct(UsageEvent.ref))).where(
                    UsageEvent.user_id == user.id, UsageEvent.kind == "prediction_view",
                    UsageEvent.created_at >= since,
                )
            )
            if used >= plan.prediction_views_per_day:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=f"Has alcanzado el límite de {plan.prediction_views_per_day} análisis en 24 h de tu plan",
                )
    db.add(UsageEvent(user_id=user.id, kind="prediction_view", ref=ref))
    db.commit()
