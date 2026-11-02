"""Diario de apuestas personal: el usuario anota lo que apuesta en su casa de apuestas
y la plataforma liquida y mide su rentabilidad real. La plataforma NO acepta apuestas."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.bets import MANUAL_MARKET, SELECTIONS, apply_result, settle_pending, summary
from app.db import get_db
from app.deps import get_current_user
from app.models import Bet, BetStatus, Match, MatchStatus, Prediction, User
from app.serializers import match_out

router = APIRouter(prefix="/bets", tags=["bets"])


class BetIn(BaseModel):
    match_id: int | None = None
    description: str = Field(default="", max_length=200)
    market: str = Field(max_length=40)
    selection: str = Field(max_length=40)
    odds: float = Field(gt=1, le=1000)
    stake: float = Field(ge=0, le=1_000_000)
    bookmaker: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=300)


class BetPatch(BaseModel):
    status: BetStatus | None = None
    note: str | None = Field(default=None, max_length=300)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def bet_out(b: Bet) -> dict:
    return {"id": b.id, "match": match_out(b.match) if b.match else None, "description": b.description,
            "market": b.market, "selection": b.selection, "odds": b.odds, "stake": b.stake,
            "bookmaker": b.bookmaker, "note": b.note, "placed_at": b.placed_at, "in_play": b.in_play,
            "model_pick": b.model_pick, "model_probability": b.model_probability, "status": b.status.value,
            "profit": b.profit, "settled_at": b.settled_at,
            "expected_value": round(b.model_probability * b.odds - 1, 4) if b.model_probability else None}


@router.post("", status_code=201)
def create_bet(body: BetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    market = body.market.strip()
    selection = body.selection.strip().lower() if market != MANUAL_MARKET else body.selection.strip()
    b = Bet(user_id=user.id, market=market, selection=selection, odds=body.odds, stake=body.stake,
            bookmaker=body.bookmaker.strip(), note=body.note.strip(), description=body.description.strip())
    if body.match_id is not None:
        m = db.get(Match, body.match_id)
        if not m:
            raise HTTPException(404, "Partido no encontrado")
        if m.status in (MatchStatus.finished, MatchStatus.cancelled):
            raise HTTPException(400, "El partido ya terminó: solo se registran apuestas antes del final")
        if market != MANUAL_MARKET and selection not in SELECTIONS.get(market, set()):
            raise HTTPException(400, f"Selección no válida para el mercado {market}")
        b.match_id = m.id
        b.in_play = m.status == MatchStatus.live or _aware(m.start_time) <= datetime.now(UTC)
        pred = db.scalar(select(Prediction).where(Prediction.match_id == m.id, Prediction.market == market,
                                                  Prediction.is_backtest.is_(False)))
        if pred:
            b.model_pick = pred.predicted_outcome
            b.model_probability = pred.probabilities.get(selection)
        if not b.description:
            b.description = f"{m.home.name} vs {m.away.name}"
    elif market != MANUAL_MARKET:
        raise HTTPException(400, "Sin partido asociado usa el mercado 'other' y liquídala tú")
    elif not b.description:
        raise HTTPException(400, "Describe la apuesta")
    db.add(b)
    db.commit()
    return bet_out(b)


@router.get("")
def list_bets(status: BetStatus | None = None, limit: int = Query(100, le=500), offset: int = 0,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settle_pending(db, user.id)
    q = select(Bet).options(joinedload(Bet.match).joinedload(Match.home), joinedload(Bet.match).joinedload(Match.away),
                            joinedload(Bet.match).joinedload(Match.competition)).where(Bet.user_id == user.id)
    if status:
        q = q.where(Bet.status == status)
    rows = db.scalars(q.order_by(Bet.placed_at.desc()).limit(limit).offset(offset)).unique().all()
    return [bet_out(b) for b in rows]


@router.get("/summary")
def bets_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settle_pending(db, user.id)
    return summary(list(db.scalars(select(Bet).where(Bet.user_id == user.id)).all()))


@router.patch("/{bet_id}")
def update_bet(bet_id: int, body: BetPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = db.scalar(select(Bet).where(Bet.id == bet_id, Bet.user_id == user.id))
    if not b:
        raise HTTPException(404, "No encontrada")
    if body.note is not None:
        b.note = body.note.strip()
    if body.status is not None:
        if b.market != MANUAL_MARKET:
            raise HTTPException(400, "Esta apuesta se liquida sola con el resultado oficial")
        if body.status == BetStatus.pending:
            b.status, b.profit, b.settled_at = BetStatus.pending, None, None
        else:
            apply_result(b, body.status)
    db.commit()
    return bet_out(b)


@router.delete("/{bet_id}", status_code=204)
def delete_bet(bet_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = db.scalar(select(Bet).where(Bet.id == bet_id, Bet.user_id == user.id))
    if not b:
        raise HTTPException(404, "No encontrada")
    if b.status != BetStatus.pending:
        raise HTTPException(400, "Las apuestas liquidadas no se borran: así el balance es real")
    db.delete(b)
    db.commit()
