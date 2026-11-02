from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import consume_prediction_view, get_current_user
from app.models import Match, MatchStatus, Prediction, Sport, User
from app.plans import get_plan
from app.serializers import match_out

router = APIRouter(prefix="/predictions", tags=["predictions"])

MARKET_LABELS = {
    "1x2": "Resultado (1X2)", "over_under_2.5": "Más/Menos 2,5 goles", "btts": "Ambos marcan",
    "moneyline": "Ganador", "match_winner": "Ganador del partido",
}


def prediction_out(p: Prediction, full: bool = True) -> dict:
    exp = dict(p.explanation or {})
    if not full:
        exp = {"summary": exp.get("summary"), "factors_for": (exp.get("factors_for") or [])[:2],
               "factors_against": (exp.get("factors_against") or [])[:1], "trends": (exp.get("trends") or [])[:1],
               "confidence_label": exp.get("confidence_label"), "limited": True}
    return {
        "id": p.id, "match_id": p.match_id, "sport": p.sport.value, "market": p.market,
        "market_label": MARKET_LABELS.get(p.market, p.market), "engine": p.engine, "engine_version": p.engine_version,
        "probabilities": p.probabilities, "predicted_outcome": p.predicted_outcome, "confidence": p.confidence,
        "explanation": exp, "data_quality": p.data_quality, "created_at": p.created_at, "kickoff_at": p.kickoff_at,
        "content_hash": p.content_hash, "is_backtest": p.is_backtest,
        "result": None if p.resolved_at is None else {"actual_outcome": p.actual_outcome, "is_correct": p.is_correct,
                                                       "brier": p.brier, "log_loss": p.log_loss,
                                                       "resolved_at": p.resolved_at},
    }


@router.get("/match/{match_id}")
def for_match(match_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "Partido no encontrado")
    preds = db.scalars(select(Prediction).where(Prediction.match_id == match_id, Prediction.is_backtest.is_(False))
                       .order_by(Prediction.market)).all()
    mode = "live"
    if not preds:
        # Sin predicción publicada: se muestra la de la prueba histórica, claramente etiquetada.
        preds = db.scalars(select(Prediction).where(Prediction.match_id == match_id, Prediction.is_backtest.is_(True))
                           .order_by(Prediction.market)).all()
        mode = "backtest"
    if not preds:
        note = (m.stats or {}).get("prediction_note")
        return {"match": match_out(m), "predictions": [],
                "note": note or "Aún no hay predicción: se generan en las 72 h previas al inicio si hay datos "
                                "suficientes."}
    consume_prediction_view(db, user, f"match:{match_id}")
    full = get_plan(user.plan_code).full_explanations
    return {"match": match_out(m), "predictions": [prediction_out(p, full) for p in preds], "limited": not full,
            "mode": mode}


@router.get("/upcoming")
def upcoming(sport: Sport | None = None, limit: int = Query(30, le=100), _: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    q = (select(Prediction).join(Match).options(joinedload(Prediction.match).joinedload(Match.home),
                                                 joinedload(Prediction.match).joinedload(Match.away),
                                                 joinedload(Prediction.match).joinedload(Match.competition))
         .where(Prediction.is_backtest.is_(False), Match.status == MatchStatus.scheduled, Match.start_time > now,
                Prediction.market.in_(["1x2", "moneyline", "match_winner"])))
    if sport:
        q = q.where(Prediction.sport == sport)
    rows = db.scalars(q.order_by(Match.start_time).limit(limit)).unique().all()
    return [{"match": match_out(p.match), "market": p.market, "probabilities": p.probabilities,
             "predicted_outcome": p.predicted_outcome, "confidence": p.confidence,
             "confidence_label": (p.explanation or {}).get("confidence_label"),
             "data_quality_level": (p.data_quality or {}).get("level")} for p in rows]


@router.get("/history")
def history(
    sport: Sport | None = None,
    market: str | None = None,
    state: str = Query("all", pattern="^(all|resolved|pending)$"),
    include_backtest: bool = False,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = get_plan(user.plan_code)
    q = select(Prediction).options(joinedload(Prediction.match).joinedload(Match.home),
                                   joinedload(Prediction.match).joinedload(Match.away),
                                   joinedload(Prediction.match).joinedload(Match.competition))
    if not include_backtest:
        q = q.where(Prediction.is_backtest.is_(False))
    if sport:
        q = q.where(Prediction.sport == sport)
    if market:
        q = q.where(Prediction.market == market)
    if state == "resolved":
        q = q.where(Prediction.resolved_at.is_not(None))
    elif state == "pending":
        q = q.where(Prediction.resolved_at.is_(None))
    if plan.history_days is not None:
        q = q.where(Prediction.kickoff_at >= datetime.now(UTC) - timedelta(days=plan.history_days))
    rows = db.scalars(q.order_by(Prediction.kickoff_at.desc()).limit(limit).offset(offset)).unique().all()
    return [{**prediction_out(p, full=False), "match": match_out(p.match)} for p in rows]
