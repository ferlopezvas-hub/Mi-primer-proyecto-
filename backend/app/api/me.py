"""Perfil, preferencias, seguimientos y suscripciones push del usuario."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.auth import user_out
from app.db import get_db
from app.deps import get_current_user
from app.models import Competition, Follow, Match, PushSubscription, Team, User
from app.notifications.prefs import ALLOWED_UPCOMING_MINUTES, EVENT_CATALOG, merged_prefs
from app.plans import PLANS, get_plan
from app.security import verify_password

router = APIRouter(prefix="/me", tags=["me"])
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)


class QuietHours(BaseModel):
    start: str
    end: str


class PrefsIn(BaseModel):
    channels: dict[str, bool] | None = None
    upcoming_minutes: int | None = None
    quiet_hours: QuietHours | None = None
    clear_quiet_hours: bool = False
    events: dict[str, dict[str, bool]] | None = None


class FollowIn(BaseModel):
    kind: str = Field(pattern="^(team|match|competition)$")
    target_id: int


class PushSubIn(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: dict[str, str]
    user_agent: str = Field(default="", max_length=300)


class DeleteAccountIn(BaseModel):
    password: str


@router.get("")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.patch("")
def update_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.timezone is not None:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(body.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(400, "Zona horaria no válida") from None
        user.timezone = body.timezone
    db.commit()
    return user_out(user)


@router.delete("", status_code=204)
def delete_account(body: DeleteAccountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Derecho de supresión (RGPD art. 17)."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(400, "Contraseña incorrecta")
    db.delete(user)
    db.commit()


@router.get("/plans")
def plans(user: User = Depends(get_current_user)):
    return {"current": user.plan_code, "plans": [p.to_dict() for p in PLANS.values()],
            "payments_enabled": False}


# ---------------------------------------------------------------- preferencias
@router.get("/notification-preferences")
def get_prefs(user: User = Depends(get_current_user)):
    return {"preferences": merged_prefs(user.notification_prefs), "catalog": EVENT_CATALOG,
            "allowed_upcoming_minutes": ALLOWED_UPCOMING_MINUTES}


@router.put("/notification-preferences")
def put_prefs(body: PrefsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prefs = merged_prefs(user.notification_prefs)
    if body.channels is not None:
        prefs["channels"].update({k: v for k, v in body.channels.items() if k in prefs["channels"]})
    if body.upcoming_minutes is not None:
        if body.upcoming_minutes not in ALLOWED_UPCOMING_MINUTES:
            raise HTTPException(400, f"Valores permitidos: {ALLOWED_UPCOMING_MINUTES}")
        prefs["upcoming_minutes"] = body.upcoming_minutes
    if body.clear_quiet_hours:
        prefs["quiet_hours"] = None
    elif body.quiet_hours is not None:
        if not (_HHMM.match(body.quiet_hours.start) and _HHMM.match(body.quiet_hours.end)):
            raise HTTPException(400, "Formato de hora HH:MM")
        prefs["quiet_hours"] = body.quiet_hours.model_dump()
    if body.events:
        for sport, evs in body.events.items():
            if sport not in EVENT_CATALOG:
                raise HTTPException(400, f"Deporte desconocido: {sport}")
            for k, v in evs.items():
                if k not in EVENT_CATALOG[sport]:
                    raise HTTPException(400, f"Evento desconocido: {sport}.{k}")
                prefs["events"][sport][k] = v
    user.notification_prefs = prefs
    db.commit()
    return {"preferences": prefs}


# ---------------------------------------------------------------- seguimientos
_FOLLOW_MODELS = {"team": Team, "match": Match, "competition": Competition}


def _follow_label(db: Session, f: Follow) -> dict:
    obj = db.get(_FOLLOW_MODELS[f.kind], f.target_id)
    if obj is None:
        name = "(eliminado)"
    elif f.kind == "match":
        name = f"{obj.home.name} vs {obj.away.name}"
    else:
        name = obj.name
    return {"id": f.id, "kind": f.kind, "target_id": f.target_id, "name": name,
            "sport": getattr(obj, "sport", None)}


@router.get("/follows")
def list_follows(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Follow).where(Follow.user_id == user.id).order_by(Follow.created_at.desc())).all()
    return [_follow_label(db, f) for f in rows]


@router.post("/follows", status_code=201)
def add_follow(body: FollowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.get(_FOLLOW_MODELS[body.kind], body.target_id) is None:
        raise HTTPException(404, "No encontrado")
    existing = db.scalar(select(Follow).where(Follow.user_id == user.id, Follow.kind == body.kind,
                                              Follow.target_id == body.target_id))
    if existing:
        return _follow_label(db, existing)
    count = db.scalar(select(func.count()).select_from(Follow).where(Follow.user_id == user.id))
    limit = get_plan(user.plan_code).max_follows
    if count >= limit:
        raise HTTPException(402, f"Tu plan permite seguir hasta {limit} elementos")
    f = Follow(user_id=user.id, kind=body.kind, target_id=body.target_id)
    db.add(f)
    db.commit()
    return _follow_label(db, f)


@router.delete("/follows/{follow_id}", status_code=204)
def remove_follow(follow_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(delete(Follow).where(Follow.id == follow_id, Follow.user_id == user.id))
    db.commit()


# ---------------------------------------------------------------- push
@router.post("/push-subscriptions", status_code=201)
def add_push(body: PushSubIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.endpoint.startswith("https://"):
        raise HTTPException(400, "Endpoint no válido")
    if "p256dh" not in body.keys or "auth" not in body.keys:
        raise HTTPException(400, "Faltan claves de la suscripción")
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=body.endpoint, user_id=user.id, p256dh="", auth="")
        db.add(sub)
    sub.user_id = user.id
    sub.p256dh = body.keys["p256dh"]
    sub.auth = body.keys["auth"]
    sub.user_agent = body.user_agent
    sub.failures = 0
    db.commit()
    return {"id": sub.id}


@router.delete("/push-subscriptions", status_code=204)
def remove_push(endpoint: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(delete(PushSubscription).where(PushSubscription.endpoint == endpoint,
                                              PushSubscription.user_id == user.id))
    db.commit()
