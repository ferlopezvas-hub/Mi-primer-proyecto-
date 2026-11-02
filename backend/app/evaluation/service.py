"""Informe de precisión: global, por deporte, competición, mercado y modo
(backtest histórico vs. predicciones nuevas guardadas antes del partido)."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.evaluation.metrics import baseline_brier_uniform, calibration, wilson_interval
from app.evaluation.resolve import VOID
from app.models import Competition, Prediction
from app.store import safe

CACHE_SECONDS = 120
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


def invalidate_cache() -> None:
    def _op(r):
        for sp in (None, "football", "basketball", "tennis"):
            for md in (None, "live", "backtest"):
                r.delete(f"eval:{sp}:{md}")

    safe(_op)


def report(db: Session, sport: str | None = None, mode: str | None = None) -> dict:
    target = get_settings().accuracy_target
    cache_key = f"eval:{sport}:{mode}"
    cached = safe(lambda r: r.get(cache_key))
    if cached:
        return json.loads(cached)
    # Solo las columnas necesarias (sin las explicaciones JSON, que pesan mucho)
    q = select(Prediction.sport, Prediction.market, Prediction.competition_id, Prediction.is_backtest,
               Prediction.probabilities, Prediction.actual_outcome, Prediction.is_correct, Prediction.brier,
               Prediction.log_loss, Prediction.confidence).where(
        Prediction.resolved_at.is_not(None), Prediction.actual_outcome != VOID)
    if sport:
        q = q.where(Prediction.sport == sport)
    if mode == "live":
        q = q.where(Prediction.is_backtest.is_(False))
    elif mode == "backtest":
        q = q.where(Prediction.is_backtest.is_(True))
    rows = list(db.execute(q).all())
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
    out = {
        "target_accuracy": target,
        "target_note": ("Los modelos nunca se ajustan para mostrar este valor. 'Predicciones nuevas' = guardadas "
                        "antes de cada partido; 'pruebas históricas' = backtest walk-forward con datos anteriores "
                        "a cada partido."),
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
        "generated_at": datetime.now(UTC).isoformat(),
    }
    safe(lambda r: r.set(cache_key, json.dumps(out, default=str), ex=CACHE_SECONDS))
    return out
