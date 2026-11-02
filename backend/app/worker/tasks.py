"""Tareas Celery: envuelven la lógica de app.sync.jobs con locks, registro y reintentos."""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from functools import wraps

from app.alerts import alert
from app.api.health import HEARTBEAT_KEY
from app.config import get_settings
from app.db import SessionLocal
from app.engines.service import generate_upcoming
from app.evaluation.resolve import resolve_pending
from app.models import JobRun
from app.notifications.service import PushSender, fanout_pending, notify_upcoming
from app.providers.base import ProviderTemporaryError
from app.providers.http import circuit_state
from app.providers.registry import active_providers
from app.store import acquire_lock, release_lock, safe
from app.sync import jobs
from app.worker.celery_app import celery

log = logging.getLogger(__name__)


def tracked(name: str, lock_ttl: int = 600):
    """Evita ejecuciones solapadas (lock en Redis) y registra cada ejecución en job_runs."""

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not acquire_lock(name, lock_ttl):
                return {"skipped": "ya en ejecución"}
            db = SessionLocal()
            run = JobRun(name=name)
            db.add(run)
            db.commit()
            try:
                result = fn(db, *args, **kwargs) or {}
                run.status = "skipped" if result.get("skipped") else "ok"
                run.detail = {k: v for k, v in result.items() if k != "event_ids"}
                return result
            except Exception as exc:
                db.rollback()
                run.status = "error"
                run.detail = {"error": f"{type(exc).__name__}: {exc}"[:500]}
                raise
            finally:
                run.finished_at = datetime.now(UTC)
                try:
                    db.merge(run)
                    db.commit()
                finally:
                    db.close()
                    release_lock(name)

        return wrapper

    return deco


def _dispatch_events(result: dict) -> None:
    if result.get("event_ids"):
        fanout_events.delay()


@celery.task(name="app.worker.tasks.heartbeat")
def heartbeat():
    safe(lambda r: r.set(HEARTBEAT_KEY, str(time.time()), ex=3600))
    return "ok"


@celery.task(name="app.worker.tasks.sync_fixtures", bind=True, max_retries=5)
def sync_fixtures(self):
    result = tracked("sync_fixtures", 1800)(jobs.run_sync_fixtures)()
    _dispatch_events(result)
    if jobs.has_temporary_errors(result):
        raise self.retry(countdown=min(3600, 60 * 2 ** self.request.retries))
    return result


@celery.task(name="app.worker.tasks.sync_live")
def sync_live():
    # Sin reintentos: el siguiente ciclo (cada LIVE_POLL_SECONDS) ya vuelve a consultar.
    result = tracked("sync_live", 120)(jobs.run_sync_live)()
    _dispatch_events(result)
    return {k: v for k, v in result.items() if k != "event_ids"}


@celery.task(name="app.worker.tasks.sync_results", bind=True, max_retries=5)
def sync_results(self):
    result = tracked("sync_results", 900)(jobs.run_sync_results)()
    _dispatch_events(result)
    if jobs.has_temporary_errors(result):
        raise self.retry(countdown=min(3600, 60 * 2 ** self.request.retries))
    return result


@celery.task(name="app.worker.tasks.fanout_events")
def fanout_events():
    ids = tracked("fanout_events", 120)(lambda db: {"push": fanout_pending(db)})().get("push") or []
    for nid in ids:
        send_push.delay(nid)
    return {"queued_push": len(ids)}


@celery.task(name="app.worker.tasks.check_upcoming")
def check_upcoming():
    ids = tracked("check_upcoming", 300)(lambda db: {"push": notify_upcoming(db)})().get("push") or []
    for nid in ids:
        send_push.delay(nid)
    return {"queued_push": len(ids)}


@celery.task(name="app.worker.tasks.send_push", bind=True, max_retries=4,
             autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True)
def send_push(self, notification_id: int):
    db = SessionLocal()
    try:
        res = PushSender().send(db, notification_id)
    finally:
        db.close()
    if res.get("retry"):
        raise self.retry(countdown=30 * 2 ** self.request.retries)
    return res


@celery.task(name="app.worker.tasks.generate_predictions", autoretry_for=(ProviderTemporaryError,),
             retry_backoff=True, max_retries=3)
def generate_predictions():
    hours = get_settings().prediction_horizon_hours
    return tracked("generate_predictions", 3000)(lambda db: generate_upcoming(db, hours))()


@celery.task(name="app.worker.tasks.resolve_predictions")
def resolve_predictions():
    return tracked("resolve_predictions", 900)(lambda db: {"resolved": resolve_pending(db)})()


@celery.task(name="app.worker.tasks.bootstrap_history", time_limit=3 * 3600, soft_time_limit=3 * 3600 - 60)
def bootstrap_history():
    return tracked("bootstrap_history", 3 * 3600)(jobs.run_bootstrap)()


@celery.task(name="app.worker.tasks.cleanup")
def cleanup():
    return tracked("cleanup", 3600)(jobs.run_cleanup)()


@celery.task(name="app.worker.tasks.watchdog")
def watchdog():
    """Vigila proveedores y avisa al equipo si algo falla de forma sostenida."""
    issues = []
    for p in active_providers():
        st = circuit_state(p.name)
        if st["open"]:
            issues.append(f"{p.name}: circuito abierto ({st['last_error']})")
        elif st["last_success"] and time.time() - st["last_success"] > 6 * 3600:
            issues.append(f"{p.name}: sin respuestas correctas desde hace más de 6 h")
    if not active_providers():
        issues.append("No hay ningún proveedor de datos configurado (revisa las API keys)")
    for i in issues:
        alert(f"watchdog:{i[:40]}", i)
    return {"issues": issues}
