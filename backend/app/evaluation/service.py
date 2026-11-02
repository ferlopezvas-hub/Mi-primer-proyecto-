"""Informe de precisión: global, por deporte, competición, mercado y modo
(backtest histórico vs. predicciones nuevas guardadas antes del partido)."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.evaluation.metrics import baseline_brier_uniform, calibration, wilson_interval
from app.evaluation.resolve import VOID
from app.models import Competition, Prediction

MIN_SAMPLE = 30  # por debajo, el porcentaje se muestra pero marcado como no concluyente


def _block(rows: list[Prediction]) -> dict:
    n = len(rows)
    hits = sum(1 for r in rows if r.is_correct)
    if n == 0:
        return {"n": 0, "accuracy": None, "accuracy_ci95": None, "brier": None, "log_loss": None,
                "conclusive": False}
    k = max(len(r.probabilities) for r in rows)
    return {
        "n": n,
        "hits": hits,
        "accuracy": round(hits / n, 4),
        "accuracy_ci95": wilson_interval(hits, n),
        "brier": round(sum(r.brier for r in rows) / n, 4),
        "brier_uniform_baseline": round(baseline_brier_uniform(k), 4),
        "log_loss": round(sum(r.log_loss for r in rows) / n, 4),
        "avg_confidence": round(sum(r.confidence for r in rows) / n, 3),
        "conclusive": n >= MIN_SAMPLE,
    }


def report(db: Session, sport: str | None = None, mode: str | None = None) -> dict:
    target = get_settings().accuracy_target
    q = select(Prediction).where(Prediction.resolved_at.is_not(None), Prediction.actual_outcome != VOID)
    if sport:
        q = q.where(Prediction.sport == sport)
    if mode == "live":
        q = q.where(Prediction.is_backtest.is_(False))
    elif mode == "backtest":
        q = q.where(Prediction.is_backtest.is_(True))
    rows = list(db.scalars(q).all())
    comp_names = {c.id: f"{c.name} {c.season}".strip() for c in db.scalars(select(Competition)).all()}

    def group(key) -> dict:
        g: dict[str, list] = defaultdict(list)
        for r in rows:
            g[key(r)].append(r)
        return {k: _block(v) for k, v in sorted(g.items())}

    def calib(rs) -> dict:
        return calibration((p, k == r.actual_outcome) for r in rs for k, p in r.probabilities.items())

    overall = _block(rows)
    pending = db.query(Prediction).filter(Prediction.resolved_at.is_(None)).count()
    markets: dict[str, list] = defaultdict(list)
    for r in rows:
        markets[f"{r.sport.value}:{r.market}"].append(r)
    return {
        "target_accuracy": target,
        "target_note": ("Objetivo experimental. Los modelos nunca se ajustan para mostrar este valor: "
                        "las cifras se calculan sobre predicciones guardadas antes de cada partido."),
        "min_sample_for_conclusions": MIN_SAMPLE,
        "overall": {**overall, "gap_to_target": None if overall["accuracy"] is None
                    else round(overall["accuracy"] - target, 4)},
        "pending_predictions": pending,
        "by_mode": group(lambda r: "backtest" if r.is_backtest else "live"),
        "by_sport": group(lambda r: r.sport.value),
        "by_market": {k: _block(v) for k, v in sorted(markets.items())},
        "by_competition": group(lambda r: comp_names.get(r.competition_id, "Sin competición")),
        "by_confidence": group(lambda r: "alta" if r.confidence >= 0.7 else "media" if r.confidence >= 0.45
                               else "baja"),
        "calibration": {k: calib(v) for k, v in sorted(markets.items())},
    }
