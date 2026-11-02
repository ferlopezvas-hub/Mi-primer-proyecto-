"""Liquidación y estadísticas del diario de apuestas."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.resolve import VOID, outcome
from app.models import Bet, BetStatus, Match

SELECTIONS = {
    "1x2": {"home", "draw", "away"},
    "over_under_2.5": {"over", "under"},
    "btts": {"yes", "no"},
    "moneyline": {"home", "away"},
    "match_winner": {"home", "away"},
}
MANUAL_MARKET = "other"


def apply_result(b: Bet, status: BetStatus) -> None:
    b.status = status
    b.profit = round(b.stake * (b.odds - 1), 2) if status == BetStatus.won else (
        -round(b.stake, 2) if status == BetStatus.lost else 0.0)
    b.settled_at = datetime.now(UTC)


def settle_pending(db: Session, user_id: int | None = None) -> int:
    q = (select(Bet, Match).join(Match, Match.id == Bet.match_id)
         .where(Bet.status == BetStatus.pending, Bet.market != MANUAL_MARKET))
    if user_id is not None:
        q = q.where(Bet.user_id == user_id)
    n = 0
    for b, m in db.execute(q).all():
        res = outcome(b.market, m)
        if res is None:
            continue
        apply_result(b, BetStatus.void if res == VOID else BetStatus.won if res == b.selection else BetStatus.lost)
        n += 1
    db.commit()
    return n


def _agg(bets: list[Bet]) -> dict:
    settled = [b for b in bets if b.status in (BetStatus.won, BetStatus.lost)]
    staked = sum(b.stake for b in settled)
    profit = sum(b.profit or 0 for b in settled)
    won = sum(1 for b in settled if b.status == BetStatus.won)
    return {
        "bets": len(bets), "settled": len(settled), "won": won,
        "hit_rate": round(won / len(settled), 4) if settled else None,
        "staked": round(staked, 2), "profit": round(profit, 2),
        "roi": round(profit / staked, 4) if staked else None,
        "avg_odds": round(sum(b.odds for b in settled) / len(settled), 2) if settled else None,
    }


def summary(bets: list[Bet]) -> dict:
    def group(key):
        g: dict[str, list[Bet]] = defaultdict(list)
        for b in bets:
            g[key(b)].append(b)
        return {k: _agg(v) for k, v in sorted(g.items())}

    def vs_model(b: Bet) -> str:
        if b.model_pick is None:
            return "sin_prediccion"
        return "siguiendo_modelo" if b.model_pick == b.selection else "contra_modelo"

    series, running = [], 0.0
    for b in sorted((b for b in bets if b.settled_at and b.status != BetStatus.pending), key=lambda b: b.settled_at):
        running += b.profit or 0
        series.append({"date": b.settled_at.isoformat(), "profit": round(running, 2)})
    return {
        "overall": _agg(bets),
        "pending": sum(1 for b in bets if b.status == BetStatus.pending),
        "by_bookmaker": group(lambda b: b.bookmaker or "Sin indicar"),
        "by_market": group(lambda b: b.market),
        "by_model": group(vs_model),
        "by_timing": group(lambda b: "en_vivo" if b.in_play else "antes_del_partido"),
        "cumulative": series,
    }
