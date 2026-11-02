# SPORT AI PREDICTOR

Plataforma SaaS de inteligencia deportiva para **fútbol, baloncesto y tenis**: calendario, partidos en directo,
notificaciones push y predicciones estadísticas **transparentes y auditables**.

> Las predicciones son estimaciones estadísticas. **No se inventan datos, resultados ni niveles de precisión**: todas las
> cifras de acierto que muestra la plataforma se calculan sobre predicciones guardadas (e inmutables) antes de cada partido
> o sobre un backtest *walk-forward* sin fuga de información.

## Qué incluye

| Módulo | Contenido | Documentación |
|---|---|---|
| Sistema 24/7 | Celery worker + beat, colas `default`/`live`/`notifications`, locks, reintentos con *backoff*, *circuit breaker*, cuotas diarias por API, *watchdog* con alertas | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Notificaciones | Detección de eventos (goles, tarjetas, descanso, cuartos, sets...), deduplicación en BD, preferencias por usuario y deporte, horas de silencio, Web Push (VAPID) + PWA + centro de notificaciones | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#notificaciones) |
| Motores | Football AI (Dixon-Coles), Basketball AI (Elo + margen), Tennis AI (Elo por superficie) con probabilidad, confianza, factores, tendencias y calidad de datos | [docs/MODELS.md](docs/MODELS.md) |
| Evaluación | Acierto (con IC 95 %), Brier, log loss, calibración (ECE), por deporte/competición/mercado/confianza, backtest vs. predicciones nuevas | [docs/MODELS.md](docs/MODELS.md#resultados-reales) |
| Datos | Conectores modulares: API-Football, API-Basketball, API-Tennis, football-data.org, históricos de football-data.co.uk | [docs/DATA_PROVIDERS.md](docs/DATA_PROVIDERS.md) |
| Interfaz | PWA React responsive (iPhone, Android, tablet, escritorio), modo claro/oscuro, panel de administración | `frontend/` |
| SaaS | Registro, login, recuperación de contraseña, planes Free/Pro/Elite con límites, roles, auditoría, métricas de uso. **Pagos no implementados** (ver [docs/LEGAL.md](docs/LEGAL.md)) | [docs/SECURITY.md](docs/SECURITY.md) |
| Operación | Docker, docker-compose, blueprint de Render, Vercel, copias de seguridad, Prometheus, Sentry, health checks | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md), [docs/OPERATIONS.md](docs/OPERATIONS.md) |

## Arranque rápido (desarrollo)

Requisitos: Python 3.12+, Node 20+, PostgreSQL 16 y Redis 7 (o `docker compose up db redis`).

```bash
# Backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://sportai:sportai@localhost:5432/sportai REDIS_URL=redis://localhost:6379/0
alembic upgrade head
python -m app.cli create-admin --email tu@email.com
uvicorn app.main:app --reload                                   # API en :8000 (docs en /docs)
celery -A app.worker.celery_app worker -B -Q default,live,notifications -l info   # 24/7 (en producción: beat aparte)

# Datos históricos reales para entrenar y evaluar (football-data.co.uk)
python -m app.cli import-history --divisions SP1,E0,I1,D1,F1 --seasons 2223,2324,2425,2526,2627
python -m app.cli backtest --sport football --from 2023-08-01 --to 2026-11-03
python -m app.cli evaluation --mode backtest

# Frontend
cd ../frontend && npm install && npm run dev                    # http://localhost:5173 (proxy a la API)
```

Para recibir datos en directo, define al menos una API key en `.env` (ver `.env.example` y
[docs/DATA_PROVIDERS.md](docs/DATA_PROVIDERS.md)). Sin claves, la plataforma funciona con los históricos importados,
pero no tendrá directo ni calendario futuro.

## Pruebas

```bash
cd backend && pytest -q && ruff check .        # 65 pruebas (SQLite por defecto; con DATABASE_URL de PostgreSQL también pasan)
cd frontend && npm run typecheck && npm test && npm run build
```

La integración continua (`.github/workflows/ci.yml`) ejecuta lo anterior contra PostgreSQL y Redis reales, comprueba las
migraciones (subida, bajada y sin cambios pendientes) y construye la imagen Docker.

## Estructura

```
backend/
  app/api/            Endpoints REST (auth, me, sports, predictions, evaluation, notifications, admin, health)
  app/providers/      Conectores de datos (contrato común en base.py, cliente resiliente en http.py)
  app/sync/           Sincronización idempotente, detector de eventos y trabajos periódicos
  app/notifications/  Preferencias, textos, reparto (fan-out) y Web Push
  app/engines/        Football AI, Basketball AI, Tennis AI y orquestación de predicciones
  app/evaluation/     Métricas, resolución de resultados, informe y backtest walk-forward
  app/worker/         Celery (planificación 24/7 y tareas)
  alembic/            Migraciones (incluye trigger de inmutabilidad de predicciones)
frontend/             PWA React + Vite + Tailwind (service worker en public/sw.js)
docs/                 Arquitectura, modelos, proveedores, despliegue, seguridad, operación y aspectos legales
```
