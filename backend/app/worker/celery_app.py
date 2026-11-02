"""Celery: colas de procesamiento + planificador (beat) 24/7.

Procesos:
  celery -A app.worker.celery_app worker -Q default,live,notifications
  celery -A app.worker.celery_app beat
Ambos se ejecutan en el servidor, independientemente de que haya usuarios conectados.
"""
from __future__ import annotations

from celery import Celery
from celery.signals import setup_logging as celery_setup_logging

from app.config import get_settings

s = get_settings()

celery = Celery("sportai", broker=s.redis_url, backend=None, include=["app.worker.tasks"])
celery.conf.update(
    task_acks_late=True,  # si el worker muere a mitad, la tarea vuelve a la cola
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=15 * 60,
    task_soft_time_limit=12 * 60,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    timezone="UTC",
    task_default_queue="default",
    task_routes={
        "app.worker.tasks.sync_live": {"queue": "live"},
        "app.worker.tasks.sync_live_stats": {"queue": "live"},
        "app.worker.tasks.fanout_events": {"queue": "notifications"},
        "app.worker.tasks.send_push": {"queue": "notifications"},
        "app.worker.tasks.check_upcoming": {"queue": "notifications"},
    },
    beat_schedule={
        "heartbeat": {"task": "app.worker.tasks.heartbeat", "schedule": 30.0},
        "sync-live": {"task": "app.worker.tasks.sync_live", "schedule": float(s.live_poll_seconds),
                      "options": {"expires": s.live_poll_seconds}},
        "sync-fixtures": {"task": "app.worker.tasks.sync_fixtures", "schedule": float(s.fixtures_sync_seconds)},
        "sync-results": {"task": "app.worker.tasks.sync_results", "schedule": float(s.results_sync_seconds)},
        "check-upcoming": {"task": "app.worker.tasks.check_upcoming", "schedule": float(s.upcoming_check_seconds)},
        "fanout-safety-net": {"task": "app.worker.tasks.fanout_events", "schedule": 120.0},
        "generate-predictions": {"task": "app.worker.tasks.generate_predictions",
                                 "schedule": float(s.predictions_seconds)},
        "resolve-predictions": {"task": "app.worker.tasks.resolve_predictions", "schedule": 900.0},
        "watchdog": {"task": "app.worker.tasks.watchdog", "schedule": 300.0},
        "sync-live-stats": {"task": "app.worker.tasks.sync_live_stats", "schedule": float(s.live_stats_seconds),
                            "options": {"expires": s.live_stats_seconds}},
        "access-reminders": {"task": "app.worker.tasks.access_reminders", "schedule": 6 * 3600.0},
        "cleanup": {"task": "app.worker.tasks.cleanup", "schedule": 86400.0},
    },
)


@celery_setup_logging.connect
def _configure_logging(**_):
    """Celery usa nuestra configuración de logs (JSON en producción) en lugar de la suya."""
    from app.logging_config import setup_logging

    setup_logging()
