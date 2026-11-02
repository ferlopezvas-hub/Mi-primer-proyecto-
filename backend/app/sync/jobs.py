"""Lógica de los trabajos periódicos (independiente de Celery para poder probarla)."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Match, MatchStatus, RefreshToken, UsageEvent, UserNotification
from app.providers.base import ProviderError, ProviderTemporaryError, QuotaExceededError
from app.providers.registry import active_providers
from app.sync.service import SyncResult, process

log = logging.getLogger(__name__)

# Tras este tiempo desde el inicio, un partido no finalizado se considera "por cerrar"
EXPECTED_DURATION = {"football": timedelta(hours=2), "basketball": timedelta(hours=2, minutes=30),
                     "tennis": timedelta(hours=2)}


def _now() -> datetime:
    return datetime.now(UTC)


def run_sync_fixtures(db: Session) -> dict:
    s = get_settings()
    today = _now().date()
    report, total = {}, SyncResult()
    for p in active_providers():
        try:
            dtos = p.fixtures(today - timedelta(days=1), today + timedelta(days=s.fixture_horizon_days))
            r = process(db, p, dtos)
            total.merge(r)
            report[p.name] = {"fetched": len(dtos), "created": r.created, "updated": r.updated}
        except QuotaExceededError as exc:
            report[p.name] = {"skipped": str(exc)}
        except ProviderError as exc:
            db.rollback()
            report[p.name] = {"error": str(exc), "temporary": isinstance(exc, ProviderTemporaryError)}
    return {"providers": report, "event_ids": total.event_ids}


def live_window_active(db: Session, now: datetime | None = None) -> bool:
    """¿Merece la pena consultar el directo? Ahorra cuota cuando no hay partidos."""
    now = now or _now()
    q = select(Match.id).where(or_(
        Match.status == MatchStatus.live,
        (Match.status == MatchStatus.scheduled) & (Match.start_time <= now + timedelta(minutes=10))
        & (Match.start_time >= now - timedelta(hours=3)),
    )).limit(1)
    return db.scalar(q) is not None


def run_sync_live(db: Session) -> dict:
    if not live_window_active(db):
        return {"skipped": "sin partidos en juego ni a punto de empezar", "event_ids": []}
    report, total = {}, SyncResult()
    for p in active_providers():
        if not p.supports_live:
            continue
        try:
            dtos = p.live()
            r = process(db, p, dtos)
            total.merge(r)
            # Partidos que estaban en directo y ya no aparecen: consultar su estado final
            seen = {d.provider_id for d in dtos}
            vanished = db.scalars(select(Match.provider_id).where(
                Match.provider == p.name, Match.status == MatchStatus.live)).all()
            missing = [pid for pid in vanished if pid not in seen]
            if missing:
                r2 = process(db, p, p.by_ids(missing))
                total.merge(r2)
            report[p.name] = {"live": len(dtos), "closed_check": len(missing), "events": total.events}
        except QuotaExceededError as exc:
            report[p.name] = {"skipped": str(exc)}
        except ProviderError as exc:
            db.rollback()
            report[p.name] = {"error": str(exc), "temporary": isinstance(exc, ProviderTemporaryError)}
    return {"providers": report, "event_ids": total.event_ids}


def run_sync_results(db: Session) -> dict:
    now = _now()
    report, total = {}, SyncResult()
    for p in active_providers():
        dur = EXPECTED_DURATION[p.sport.value]
        pending = db.scalars(select(Match.provider_id).where(
            Match.provider == p.name,
            Match.status.in_([MatchStatus.scheduled, MatchStatus.live, MatchStatus.unknown]),
            Match.start_time <= now - dur, Match.start_time >= now - timedelta(days=3),
        ).limit(100)).all()
        if not pending:
            continue
        try:
            r = process(db, p, p.by_ids(list(pending)))
            total.merge(r)
            report[p.name] = {"checked": len(pending), "updated": r.updated}
        except QuotaExceededError as exc:
            report[p.name] = {"skipped": str(exc)}
        except ProviderError as exc:
            db.rollback()
            report[p.name] = {"error": str(exc), "temporary": isinstance(exc, ProviderTemporaryError)}
    return {"providers": report, "event_ids": total.event_ids}


def run_cleanup(db: Session) -> dict:
    now = _now()
    a = db.execute(delete(UsageEvent).where(UsageEvent.created_at < now - timedelta(days=400))).rowcount
    b = db.execute(delete(UserNotification).where(UserNotification.created_at < now - timedelta(days=180))).rowcount
    c = db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now - timedelta(days=1))).rowcount
    db.commit()
    return {"usage_events": a, "notifications": b, "refresh_tokens": c}


def has_temporary_errors(result: dict) -> bool:
    return any(isinstance(v, dict) and v.get("temporary") for v in (result.get("providers") or {}).values())
