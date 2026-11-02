#!/bin/sh
set -e
case "$ROLE" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    exec celery -A app.worker.celery_app worker -Q default,live,notifications --concurrency "${WORKER_CONCURRENCY:-2}" -l info
    ;;
  worker-beat)
    # Worker y planificador en un mismo proceso (ahorra un servicio). Usar UNA sola instancia.
    exec celery -A app.worker.celery_app worker -B -Q default,live,notifications --concurrency "${WORKER_CONCURRENCY:-2}" -l info --schedule /tmp/celerybeat-schedule
    ;;
  beat)
    # ¡Solo UNA instancia de beat! Si hubiera dos, las tareas se programarían por duplicado.
    exec celery -A app.worker.celery_app beat -l info --schedule /tmp/celerybeat-schedule
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  *) echo "ROLE desconocido: $ROLE"; exit 1 ;;
esac
