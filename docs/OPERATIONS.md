# Operación y monitorización

## Salud del sistema

| Endpoint | Uso |
|---|---|
| `GET /health/live` | Proceso vivo (health check del contenedor) |
| `GET /health/ready` | 200 si PostgreSQL y Redis responden; `status: degraded` si el planificador no ha dado señal en 3 min; 503 si falla la base de datos o Redis |
| `GET /metrics` | Métricas Prometheus: `http_requests_total`, `http_request_seconds`, `provider_requests_total{provider,outcome}` |

## Alertas de caídas

1. **Externa** (imprescindible): Better Stack / UptimeRobot / Pingdom vigilando `https://api.…/health/ready` cada minuto
   y avisando por email/SMS/Slack. Es lo único que detecta que el servidor entero se ha caído.
2. **Interna**: la tarea `watchdog` envía a `ALERT_WEBHOOK_URL` (Slack, Discord, Teams) si un proveedor tiene el
   circuito abierto, lleva > 6 h sin responder bien o no hay ningún proveedor configurado. Máximo una alerta igual por hora.
3. **Errores de código**: `SENTRY_DSN` activa Sentry en API y workers.
4. **Logs**: JSON a stdout en producción (agregables con Loki, Better Stack, Datadog…).

## Recuperación automática

- Contenedores con `restart: unless-stopped` y health checks.
- Tareas Celery con `acks_late`: un worker que muere no pierde trabajo.
- Reintentos con backoff exponencial y circuit breaker frente a fallos temporales de proveedores.
- Si Redis no responde, la API sigue sirviendo (límites en memoria); los workers reconectan solos al broker.
- Tras una caída larga, la sincronización se pone al día sin enviar notificaciones antiguas (ventana de 6 h).

## Copias de seguridad

- Servicio `backup` en docker-compose: `pg_dump` diario en formato custom, verificación de lectura, rotación (14 días)
  y copia opcional a S3 (`BACKUP_S3_URI`).
- Restaurar: `pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" fichero.dump`.
- Recomendado además: copias automáticas y PITR del PostgreSQL gestionado, y un **simulacro de restauración mensual**.

## Tareas habituales

```bash
python -m app.cli sync fixtures|live|results|predictions|resolve   # forzar una sincronización
python -m app.cli evaluation [--mode live|backtest]                 # informe de precisión
python -m app.cli create-admin --email …                             # crear/promocionar administrador
```
También desde Administración → Sistema (botones para lanzar cada tarea, estado de proveedores y cuotas, historial de ejecuciones).
