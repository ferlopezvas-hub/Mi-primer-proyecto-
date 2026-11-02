"""Backtesting walk-forward: cada partido se predice con un modelo ajustado SOLO
con partidos anteriores a la fecha de corte. Sin fuga de información."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.engines.base import InsufficientData, canonical
from app.engines.registry import make_engine
from app.engines.service import competition_group, load_history, store_outputs
from app.evaluation.resolve import resolve_prediction
from app.models import Match, MatchStatus, Prediction, Sport


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def walk_forward(db: Session, sport: Sport, start: datetime, end: datetime, competition_name: str | None = None,
                 refit_days: int = 7) -> dict:
    q = (select(Match).options(joinedload(Match.home), joinedload(Match.away), joinedload(Match.competition))
         .where(Match.sport == sport, Match.status == MatchStatus.finished, Match.start_time >= start,
                Match.start_time < end).order_by(Match.start_time))
    matches = db.scalars(q).unique().all()
    group_filter = canonical(competition_name) if competition_name else None
    by_group: dict[str | None, list[Match]] = defaultdict(list)
    for m in matches:
        g = None if sport == Sport.tennis else competition_group(m.competition)
        if group_filter and g != group_filter:
            continue
        by_group[g].append(m)
    stats = {"matches": 0, "predictions": 0, "insufficient": 0}
    for group, ms in by_group.items():
        engine = make_engine(sport)
        done = set(db.scalars(select(Prediction.match_id).where(
            Prediction.match_id.in_([m.id for m in ms]), Prediction.is_backtest.is_(True),
            Prediction.engine_version == engine.version)).all())
        full_hist = load_history(db, sport, group, _aware(end) + timedelta(days=1), days=4000)
        cutoff = None
        for m in ms:
            if m.id in done:
                continue
            kt = _aware(m.start_time)
            day0 = kt.replace(hour=0, minute=0, second=0, microsecond=0)
            if cutoff is None or day0 >= cutoff + timedelta(days=refit_days):
                cutoff = day0
                engine.fit([h for h in full_hist if h.date < cutoff], cutoff)
            stats["matches"] += 1
            try:
                outs = engine.predict(canonical(m.home.name), canonical(m.away.name), kt, m.surface)
            except InsufficientData:
                stats["insufficient"] += 1
                continue
            stats["predictions"] += store_outputs(db, m, engine, outs, is_backtest=True,
                                                  created_at=datetime.now(UTC), data_cutoff=cutoff)
        db.flush()
        for p in db.scalars(select(Prediction).where(Prediction.is_backtest.is_(True),
                                                     Prediction.resolved_at.is_(None),
                                                     Prediction.match_id.in_([m.id for m in ms]))).all():
            resolve_prediction(p, p.match)
        db.commit()
    from app.evaluation.service import invalidate_cache

    invalidate_cache()
    return stats
