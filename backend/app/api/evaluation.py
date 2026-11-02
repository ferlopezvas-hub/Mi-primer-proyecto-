from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.evaluation.service import report
from app.models import User

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("")
def evaluation(sport: str | None = Query(None, pattern="^(football|basketball|tennis)$"),
               mode: str | None = Query(None, pattern="^(live|backtest)$"),
               _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Transparencia: disponible para todos los planes."""
    return report(db, sport=sport, mode=mode)
