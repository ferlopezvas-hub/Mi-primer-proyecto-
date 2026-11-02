"""Reparto de eventos a usuarios (fan-out), deduplicación y envío push."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Follow, Match, MatchEvent, MatchStatus, PushSubscription, User, UserNotification
from app.notifications import messages
from app.notifications.prefs import merged_prefs, wants
from app.plans import get_plan

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def followers(db: Session, m: Match) -> list[User]:
    conds = [
        (Follow.kind == "match") & (Follow.target_id == m.id),
        (Follow.kind == "team") & (Follow.target_id.in_([m.home_id, m.away_id])),
    ]
    if m.competition_id:
        conds.append((Follow.kind == "competition") & (Follow.target_id == m.competition_id))
    user_ids = select(Follow.user_id).where(or_(*conds)).distinct()
    return list(db.scalars(select(User).where(User.id.in_(user_ids), User.is_active.is_(True))).all())


def in_quiet_hours(prefs: dict, tz: str, now: datetime | None = None) -> bool:
    qh = prefs.get("quiet_hours")
    if not qh:
        return False
    try:
        local = (now or _now()).astimezone(ZoneInfo(tz)).time()
        start, end = time.fromisoformat(qh["start"]), time.fromisoformat(qh["end"])
    except (KeyError, ValueError):
        return False
    return start <= local < end if start <= end else (local >= start or local < end)


def _create(db: Session, user: User, m: Match, kind: str, payload: dict, dedup_key: str,
            event_id: int | None) -> UserNotification | None:
    title, body = messages.build(m, kind, payload)
    n = UserNotification(user_id=user.id, event_id=event_id, match_id=m.id, kind=kind, title=title, body=body,
                         data={"sport": m.sport.value, "url": f"/matches/{m.id}", **payload}, dedup_key=dedup_key)
    try:
        with db.begin_nested():
            db.add(n)
            db.flush()
        return n
    except IntegrityError:
        return None  # duplicado: el usuario ya recibió esta notificación


def fanout_event(db: Session, ev: MatchEvent) -> list[int]:
    """Crea notificaciones para los interesados. Devuelve ids a enviar por push."""
    m = ev.match
    to_push: list[int] = []
    if not ev.fanned_out:
        for user in followers(db, m):
            prefs = merged_prefs(user.notification_prefs)
            if not wants(prefs, m.sport.value, ev.type):
                continue
            plan = get_plan(user.plan_code)
            if not plan.live_events and ev.type not in ("full_time",):
                continue
            n = _create(db, user, m, ev.type, ev.payload, f"ev:{ev.id}", ev.id)
            if n and prefs["channels"].get("push") and plan.push_notifications \
                    and not in_quiet_hours(prefs, user.timezone):
                to_push.append(n.id)
        ev.fanned_out = True
    db.commit()
    return to_push


def fanout_pending(db: Session, limit: int = 500) -> list[int]:
    out: list[int] = []
    for ev in db.scalars(select(MatchEvent).where(MatchEvent.fanned_out.is_(False))
                         .order_by(MatchEvent.id).limit(limit)).all():
        out += fanout_event(db, ev)
    return out


def notify_upcoming(db: Session, now: datetime | None = None) -> list[int]:
    """Aviso de 'partido próximo' según la antelación elegida por cada usuario."""
    now = now or _now()
    horizon = now + timedelta(minutes=125)
    matches = db.scalars(select(Match).where(Match.status == MatchStatus.scheduled, Match.start_time > now,
                                             Match.start_time <= horizon)).all()
    to_push: list[int] = []
    for m in matches:
        start = m.start_time if m.start_time.tzinfo else m.start_time.replace(tzinfo=UTC)
        minutes_left = (start - now).total_seconds() / 60
        for user in followers(db, m):
            prefs = merged_prefs(user.notification_prefs)
            if not wants(prefs, m.sport.value, "upcoming") or minutes_left > prefs["upcoming_minutes"]:
                continue
            n = _create(db, user, m, "upcoming", {"minutes": max(1, round(minutes_left))},
                        f"upcoming:{m.id}", None)
            if n and prefs["channels"].get("push") and not in_quiet_hours(prefs, user.timezone, now):
                to_push.append(n.id)
    db.commit()
    return to_push


# ------------------------------------------------------------------ Web Push
class PushSender:
    """Envía Web Push (VAPID). Funciona en Chrome/Edge/Firefox/Android y en
    iOS/iPadOS ≥ 16.4 cuando la PWA está instalada en la pantalla de inicio."""

    def __init__(self, webpush_fn=None):
        self._fn = webpush_fn

    def _webpush(self):
        if self._fn is None:
            from pywebpush import webpush

            self._fn = webpush
        return self._fn

    def send(self, db: Session, notification_id: int) -> dict:
        s = get_settings()
        n = db.get(UserNotification, notification_id)
        if n is None or n.pushed_at is not None:
            return {"skipped": True}
        if not (s.vapid_private_key and s.vapid_public_key):
            return {"skipped": True, "reason": "VAPID no configurado"}
        from pywebpush import WebPushException

        payload = json.dumps({"title": n.title, "body": n.body, "tag": f"match-{n.match_id}",
                              "url": n.data.get("url", "/"), "id": n.id}, ensure_ascii=False)
        sent = failed = 0
        temporary_failure = False
        subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == n.user_id)).all()
        for sub in subs:
            try:
                self._webpush()(subscription_info={"endpoint": sub.endpoint,
                                                   "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                                data=payload, vapid_private_key=s.vapid_private_key,
                                vapid_claims={"sub": s.vapid_subject}, ttl=3600, timeout=10)
                sub.failures = 0
                sub.last_success_at = _now()
                sent += 1
            except WebPushException as exc:
                code = getattr(getattr(exc, "response", None), "status_code", None)
                failed += 1
                if code in (404, 410):  # suscripción caducada: se elimina
                    db.delete(sub)
                else:
                    sub.failures += 1
                    temporary_failure = True
                    if sub.failures >= 10:
                        db.delete(sub)
        if not temporary_failure or sent:
            n.pushed_at = _now()
        db.commit()
        return {"sent": sent, "failed": failed, "retry": temporary_failure and not sent}
