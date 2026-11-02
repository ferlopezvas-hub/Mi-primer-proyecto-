"""Sincronización idempotente proveedor -> base de datos."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Competition, Match, MatchEvent, MatchStatus, Team
from app.providers.base import CompetitionDTO, MatchDTO, SportsProvider, TeamDTO
from app.sync.detector import detect, snapshot

log = logging.getLogger(__name__)
# No se notifican eventos de partidos que empezaron hace más de esto (evita
# avalanchas al importar históricos o tras una caída larga).
NOTIFY_WINDOW = timedelta(hours=6)


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    events: int = 0
    event_ids: list[int] = field(default_factory=list)

    def merge(self, o: SyncResult) -> None:
        self.created += o.created
        self.updated += o.updated
        self.events += o.events
        self.event_ids += o.event_ids


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def upsert_team(db: Session, provider: str, sport, dto: TeamDTO) -> Team:
    t = db.scalar(select(Team).where(Team.provider == provider, Team.provider_id == dto.provider_id))
    if t is None:
        t = Team(provider=provider, provider_id=dto.provider_id, sport=sport, name=dto.name, country=dto.country,
                 logo_url=dto.logo_url, extra=dto.extra or {})
        db.add(t)
        db.flush()
    else:
        if dto.name and t.name != dto.name:
            t.name = dto.name
        if dto.logo_url:
            t.logo_url = dto.logo_url
        if dto.extra:
            t.extra = {**(t.extra or {}), **dto.extra}
    return t


def upsert_competition(db: Session, provider: str, sport, dto: CompetitionDTO | None) -> Competition | None:
    if dto is None:
        return None
    c = db.scalar(select(Competition).where(Competition.provider == provider,
                                            Competition.provider_id == dto.provider_id,
                                            Competition.season == dto.season))
    if c is None:
        c = Competition(provider=provider, provider_id=dto.provider_id, season=dto.season, sport=sport,
                        name=dto.name, country=dto.country, logo_url=dto.logo_url)
        db.add(c)
        db.flush()
    return c


def _apply(m: Match, dto: MatchDTO) -> None:
    m.start_time = dto.start_time
    m.status = dto.status
    m.status_detail = dto.status_detail
    m.elapsed = dto.elapsed
    m.home_score = dto.home_score
    m.away_score = dto.away_score
    m.periods = dto.periods or {}
    if dto.venue:
        m.venue = dto.venue
    if dto.surface:
        m.surface = dto.surface
    if dto.stats:
        m.stats = {**(m.stats or {}), **dto.stats}
    m.last_synced_at = _now()
    if dto.status == MatchStatus.finished and m.finished_at is None:
        m.finished_at = _now()


def upsert_match(db: Session, provider: SportsProvider | str, dto: MatchDTO, notify: bool = True) -> SyncResult:
    pname = provider if isinstance(provider, str) else provider.name
    res = SyncResult()
    q = select(Match).where(Match.provider == pname, Match.provider_id == dto.provider_id)
    if db.bind.dialect.name == "postgresql":
        q = q.with_for_update()
    m = db.scalar(q)
    prev = snapshot(m) if m is not None else None
    if m is None:
        comp = upsert_competition(db, pname, dto.sport, dto.competition)
        home = upsert_team(db, pname, dto.sport, dto.home)
        away = upsert_team(db, pname, dto.sport, dto.away)
        m = Match(provider=pname, provider_id=dto.provider_id, sport=dto.sport,
                  competition_id=comp.id if comp else None, home_id=home.id, away_id=away.id,
                  start_time=dto.start_time)
        db.add(m)
        _apply(m, dto)
        db.flush()
        res.created = 1
    else:
        upsert_team(db, pname, dto.sport, dto.home)
        upsert_team(db, pname, dto.sport, dto.away)
        _apply(m, dto)
        res.updated = 1

    cancellations = 0
    if prev is not None:
        cancellations = db.scalar(select(func.count()).select_from(MatchEvent).where(
            MatchEvent.match_id == m.id, MatchEvent.type == "goal_cancelled")) or 0
    detected = detect(dto.sport, prev, m, dto.events, cancellations)
    recent = _aware(m.start_time) >= _now() - NOTIFY_WINDOW
    for ev in detected:
        try:
            with db.begin_nested():
                me = MatchEvent(match_id=m.id, type=ev.type, dedup_key=ev.dedup_key, payload=ev.payload,
                                fanned_out=not (notify and recent))
                db.add(me)
                db.flush()
            res.events += 1
            if not me.fanned_out:
                res.event_ids.append(me.id)
        except IntegrityError:
            pass  # ya registrado: deduplicado
    return res


def process(db: Session, provider: SportsProvider | str, dtos: list[MatchDTO], notify: bool = True) -> SyncResult:
    total = SyncResult()
    for dto in dtos:
        try:
            with db.begin_nested():
                total.merge(upsert_match(db, provider, dto, notify=notify))
        except IntegrityError:
            # carrera con otra tarea insertando el mismo partido: reintento único
            log.info("Conflicto concurrente en %s/%s, reintentando", getattr(provider, "name", provider),
                     dto.provider_id)
            with db.begin_nested():
                total.merge(upsert_match(db, provider, dto, notify=notify))
    db.commit()
    return total
