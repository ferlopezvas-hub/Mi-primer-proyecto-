from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import User, UserNotification
from app.ratelimit import anon_rate_limit

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _out(n: UserNotification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "data": n.data, "match_id": n.match_id,
            "created_at": n.created_at, "read_at": n.read_at}


@router.get("")
def list_notifications(unread_only: bool = False, limit: int = Query(30, le=100), before_id: int | None = None,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(UserNotification).where(UserNotification.user_id == user.id)
    if unread_only:
        q = q.where(UserNotification.read_at.is_(None))
    if before_id:
        q = q.where(UserNotification.id < before_id)
    rows = db.scalars(q.order_by(UserNotification.id.desc()).limit(limit)).all()
    unread = db.scalar(select(func.count()).select_from(UserNotification).where(
        UserNotification.user_id == user.id, UserNotification.read_at.is_(None)))
    return {"items": [_out(n) for n in rows], "unread": unread}


@router.post("/{notification_id}/read", status_code=204)
def mark_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(update(UserNotification).where(UserNotification.id == notification_id,
                                              UserNotification.user_id == user.id,
                                              UserNotification.read_at.is_(None))
               .values(read_at=datetime.now(UTC)))
    db.commit()


@router.post("/read-all", status_code=204)
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(update(UserNotification).where(UserNotification.user_id == user.id,
                                              UserNotification.read_at.is_(None)).values(read_at=datetime.now(UTC)))
    db.commit()


@router.get("/vapid-public-key", dependencies=[Depends(anon_rate_limit)])
def vapid_public_key():
    key = get_settings().vapid_public_key
    return {"key": key or None, "enabled": bool(key)}
