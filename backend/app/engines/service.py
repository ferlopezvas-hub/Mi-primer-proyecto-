"""Orquestación: construye el histórico, ajusta los motores y guarda predicciones
INMUTABLES antes del inicio de cada encuentro."""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.engines.base import Engine, HistMatch, InsufficientData, PredictionOutput, canonical
from app.engines.registry import make_engine
from app.evaluation.resolve import regulation_score
from app.models import Competition, Match, MatchStatus, Prediction, Sport

log = logging.getLogger(__name__)
MIN_LEAD = timedelta(minutes=2)  # margen mínimo antes del inicio


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def competition_group(c: Competition | None) -> str:
    return canonical(c.name) if c else ""


def to_hist(m: Match) -> HistMatch | None:
    h, a = regulation_score(m)
    if h is None or a is None:
        return None
    return HistMatch(date=_aware(m.start_time), home=canonical(m.home.name), away=canonical(m.away.name),
                     home_score=int(h), away_score=int(a), surface=(m.surface or "").lower())


def load_history(db: Session, sport: Sport, group: str | None, until: datetime, days: int = 1100) -> list[HistMatch]:
    q = (select(Match).options(joinedload(Match.home), joinedload(Match.away), joinedload(Match.competition))
         .where(Match.sport == sport, Match.status == MatchStatus.finished,
                Match.start_time >= until - timedelta(days=days), Match.start_time < until))
    out, seen = [], set()
    for m in db.scalars(q).unique().all():
        if sport != Sport.tennis and group is not None and competition_group(m.competition) != group:
            continue
        hm = to_hist(m)
        if hm is None:
            continue
        # El mismo partido puede llegar de dos fuentes (p. ej. API-Football y football-data.co.uk):
        # se cuenta una sola vez.
        key = (hm.date.date(), hm.home, hm.away)
        if key in seen:
            continue
        seen.add(key)
        out.append(hm)
    return out


def content_hash(match_id: int, out: PredictionOutput, version: str, created_at: datetime) -> str:
    body = json.dumps({"m": match_id, "mk": out.market, "p": out.probabilities, "o": out.predicted_outcome,
                       "v": version, "t": created_at.isoformat()}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def store_outputs(db: Session, m: Match, engine: Engine, outputs: list[PredictionOutput], *, is_backtest: bool,
                  created_at: datetime, data_cutoff: datetime) -> int:
    n = 0
    for out in outputs:
        p = Prediction(
            match_id=m.id, sport=m.sport, competition_id=m.competition_id, engine=engine.name,
            engine_version=engine.version, market=out.market, probabilities=out.probabilities,
            predicted_outcome=out.predicted_outcome, confidence=out.confidence, explanation=out.explanation,
            data_quality=out.data_quality, is_backtest=is_backtest, created_at=created_at,
            kickoff_at=_aware(m.start_time), data_cutoff_at=data_cutoff,
            content_hash=content_hash(m.id, out, engine.version, created_at),
        )
        try:
            with db.begin_nested():
                db.add(p)
                db.flush()
            n += 1
        except IntegrityError:
            pass  # ya existe una predicción para este partido/mercado/versión
    return n


def generate_upcoming(db: Session, horizon_hours: int = 72, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    matches = db.scalars(
        select(Match).options(joinedload(Match.home), joinedload(Match.away), joinedload(Match.competition))
        .where(Match.status == MatchStatus.scheduled, Match.start_time > now + MIN_LEAD,
               Match.start_time <= now + timedelta(hours=horizon_hours))
    ).unique().all()
    groups: dict[tuple, list[Match]] = defaultdict(list)
    for m in matches:
        groups[(m.sport, None if m.sport == Sport.tennis else competition_group(m.competition))].append(m)
    stats = {"matches": len(matches), "created": 0, "insufficient": 0, "already": 0}
    for (sport, group), ms in groups.items():
        engine = make_engine(sport)
        existing = set(db.scalars(select(Prediction.match_id).where(
            Prediction.match_id.in_([m.id for m in ms]), Prediction.engine_version == engine.version,
            Prediction.is_backtest.is_(False))).all())
        todo = [m for m in ms if m.id not in existing]
        stats["already"] += len(ms) - len(todo)
        if not todo:
            continue
        engine.fit(load_history(db, sport, group, now), now)
        for m in todo:
            try:
                outs = engine.predict(canonical(m.home.name), canonical(m.away.name), _aware(m.start_time),
                                      m.surface)
            except InsufficientData as exc:
                stats["insufficient"] += 1
                m.stats = {**(m.stats or {}), "prediction_note": str(exc)}
                log.debug("Sin predicción para %s: %s", m.id, exc)
                continue
            stats["created"] += store_outputs(db, m, engine, outs, is_backtest=False, created_at=now,
                                              data_cutoff=now)
    db.commit()
    return stats
