"""Calendario, buscador, partidos en directo, equipos y competiciones."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import get_current_user
from app.models import Competition, Match, MatchEvent, MatchStatus, Prediction, Sport, Team, UsageEvent, User
from app.serializers import competition_out, event_out, match_out, team_out

router = APIRouter(prefix="/sports", tags=["sports"])


def _base_query():
    return select(Match).options(joinedload(Match.home), joinedload(Match.away), joinedload(Match.competition))


@router.get("/matches")
def list_matches(
    sport: Sport | None = None,
    status: MatchStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    team_id: int | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _base_query()
    if sport:
        q = q.where(Match.sport == sport)
    if status:
        q = q.where(Match.status == status)
    if date_from:
        q = q.where(Match.start_time >= datetime.combine(date_from, datetime.min.time(), UTC))
    if date_to:
        q = q.where(Match.start_time < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), UTC))
    if competition_id:
        q = q.where(Match.competition_id == competition_id)
    if team_id:
        q = q.where(or_(Match.home_id == team_id, Match.away_id == team_id))
    q = q.order_by(Match.start_time).limit(limit).offset(offset)
    return [match_out(m) for m in db.scalars(q).unique().all()]


@router.get("/live")
def live_matches(sport: Sport | None = None, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = _base_query().where(Match.status == MatchStatus.live)
    if sport:
        q = q.where(Match.sport == sport)
    return [match_out(m) for m in db.scalars(q.order_by(Match.start_time)).unique().all()]


@router.get("/calendar")
def calendar(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    sport: Sport | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    y, m = map(int, month.split("-"))
    if not 1 <= m <= 12:
        raise HTTPException(400, "Mes no válido")
    start = datetime(y, m, 1, tzinfo=UTC)
    end = datetime(y + (m == 12), (m % 12) + 1, 1, tzinfo=UTC)
    q = select(Match.start_time, Match.sport).where(Match.start_time >= start, Match.start_time < end)
    if sport:
        q = q.where(Match.sport == sport)
    days: dict[str, dict[str, int]] = {}
    for st, sp in db.execute(q):
        key = st.date().isoformat()
        days.setdefault(key, {}).setdefault(sp.value, 0)
        days[key][sp.value] += 1
    return {"month": month, "days": days}


@router.get("/search")
def search(
    q: str = Query(..., min_length=2, max_length=60),
    sport: Sport | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    like = f"%{q.lower()}%"
    tq = select(Team).where(func.lower(Team.name).like(like))
    cq = select(Competition).where(func.lower(Competition.name).like(like))
    if sport:
        tq, cq = tq.where(Team.sport == sport), cq.where(Competition.sport == sport)
    teams = db.scalars(tq.order_by(Team.name).limit(15)).all()
    comps = db.scalars(cq.order_by(Competition.name).limit(10)).all()
    team_ids = [t.id for t in teams]
    matches = []
    if team_ids:
        now = datetime.now(UTC)
        mq = _base_query().where(or_(Match.home_id.in_(team_ids), Match.away_id.in_(team_ids)),
                                 Match.start_time >= now - timedelta(days=1)).order_by(Match.start_time).limit(10)
        matches = [match_out(m) for m in db.scalars(mq).unique().all()]
    db.add(UsageEvent(user_id=user.id, kind="search", ref=q[:80]))
    db.commit()
    return {"teams": [team_out(t) for t in teams], "competitions": [competition_out(c) for c in comps],
            "matches": matches}


@router.get("/matches/{match_id}")
def match_detail(match_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.scalars(_base_query().where(Match.id == match_id)).unique().first()
    if not m:
        raise HTTPException(404, "Partido no encontrado")
    events = db.scalars(select(MatchEvent).where(MatchEvent.match_id == m.id).order_by(MatchEvent.created_at)).all()
    markets = db.scalars(select(Prediction.market).where(Prediction.match_id == m.id,
                                                         Prediction.is_backtest.is_(False))).all()
    return {"match": match_out(m, brief=False), "events": [event_out(e) for e in events],
            "prediction_markets": markets}


@router.get("/teams/{team_id}")
def team_detail(team_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.get(Team, team_id)
    if not t:
        raise HTTPException(404, "No encontrado")
    recent = db.scalars(
        _base_query().where(or_(Match.home_id == t.id, Match.away_id == t.id), Match.status == MatchStatus.finished)
        .order_by(Match.start_time.desc()).limit(10)
    ).unique().all()
    upcoming = db.scalars(
        _base_query().where(or_(Match.home_id == t.id, Match.away_id == t.id), Match.status == MatchStatus.scheduled)
        .order_by(Match.start_time).limit(5)
    ).unique().all()
    form = []
    for m in recent:
        if m.home_score is None or m.away_score is None:
            continue
        mine, theirs = (m.home_score, m.away_score) if m.home_id == t.id else (m.away_score, m.home_score)
        form.append("W" if mine > theirs else "L" if mine < theirs else "D")
    return {"team": team_out(t), "form": form, "recent": [match_out(m) for m in recent],
            "upcoming": [match_out(m) for m in upcoming]}


@router.get("/competitions")
def competitions(sport: Sport | None = None, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(Competition)
    if sport:
        q = q.where(Competition.sport == sport)
    return [competition_out(c) for c in db.scalars(q.order_by(Competition.sport, Competition.name)).all()]
