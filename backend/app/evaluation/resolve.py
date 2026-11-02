"""Resolución de predicciones una vez finaliza el partido."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.metrics import brier, log_loss
from app.models import Match, MatchStatus, Prediction

VOID = "void"


def regulation_score(m: Match) -> tuple[int | None, int | None]:
    """Fútbol: los mercados se liquidan a 90 minutos (sin prórroga ni penaltis)."""
    ft = (m.periods or {}).get("fulltime")
    if m.sport.value == "football" and isinstance(ft, dict) and ft.get("home") is not None:
        return ft["home"], ft["away"]
    return m.home_score, m.away_score


def outcome(market: str, m: Match) -> str | None:
    if m.status in (MatchStatus.cancelled, MatchStatus.postponed):
        return VOID
    if m.status != MatchStatus.finished:
        return None
    h, a = regulation_score(m)
    if market == "match_winner":
        detail = (m.status_detail or "").lower()
        if "retired" in detail or "walk" in detail:
            return VOID  # retiradas y walkovers no cuentan
        w = (m.periods or {}).get("winner")
        if w in ("home", "away"):
            return w
    if h is None or a is None:
        return None
    if market == "1x2":
        return "home" if h > a else "away" if a > h else "draw"
    if market == "over_under_2.5":
        return "over" if h + a > 2.5 else "under"
    if market == "btts":
        return "yes" if h > 0 and a > 0 else "no"
    if market in ("moneyline", "match_winner"):
        if h == a:
            return VOID
        return "home" if h > a else "away"
    return None


def resolve_prediction(p: Prediction, m: Match) -> bool:
    out = outcome(p.market, m)
    if out is None:
        return False
    p.actual_outcome = out
    p.resolved_at = datetime.now(UTC)
    if out != VOID:
        p.is_correct = p.predicted_outcome == out
        p.brier = round(brier(p.probabilities, out), 6)
        p.log_loss = round(log_loss(p.probabilities, out), 6)
    return True


def resolve_pending(db: Session, limit: int = 2000) -> int:
    rows = db.execute(
        select(Prediction, Match).join(Match, Match.id == Prediction.match_id)
        .where(Prediction.resolved_at.is_(None),
               Match.status.in_([MatchStatus.finished, MatchStatus.cancelled, MatchStatus.postponed]))
        .limit(limit)
    ).all()
    n = 0
    for p, m in rows:
        if m.status == MatchStatus.postponed:
            continue  # se reprogramará; la predicción original queda pendiente
        n += resolve_prediction(p, m)
    db.commit()
    if n:
        from app.evaluation.service import invalidate_cache

        invalidate_cache()
    return n
