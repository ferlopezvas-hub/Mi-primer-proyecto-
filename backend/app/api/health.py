from __future__ import annotations

import time

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.db import SessionLocal
from app.store import get_store

router = APIRouter(tags=["health"])
HEARTBEAT_KEY = "heartbeat:scheduler"
HEARTBEAT_MAX_AGE = 180


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(response: Response):
    checks: dict[str, dict] = {}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"ok": False, "error": type(exc).__name__}
    try:
        r = get_store()
        r.ping()
        checks["redis"] = {"ok": True}
        hb = r.get(HEARTBEAT_KEY)
        age = time.time() - float(hb) if hb else None
        checks["scheduler"] = {"ok": age is not None and age < HEARTBEAT_MAX_AGE,
                               "last_heartbeat_seconds": round(age, 1) if age is not None else None}
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = {"ok": False, "error": type(exc).__name__}
    # El planificador caído degrada pero no tumba la API: solo DB/Redis marcan 503.
    critical_ok = checks["database"]["ok"] and checks.get("redis", {}).get("ok", False)
    response.status_code = 200 if critical_ok else 503
    return {"status": "ok" if critical_ok and checks.get("scheduler", {}).get("ok") else
            ("degraded" if critical_ok else "down"), "checks": checks}


@router.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
