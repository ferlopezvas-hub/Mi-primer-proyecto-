# Arquitectura

```
                ┌──────────────┐  HTTPS   ┌───────────────┐
 Navegador/PWA ─┤  Vercel (CDN)├─────────►│  API FastAPI  │◄── /health, /metrics (Prometheus)
 (iOS/Android/  └──────────────┘          └──────┬────────┘
  escritorio)        ▲  Web Push (VAPID)          │ SQL           ┌──────────────┐
                     │                            ├──────────────►│ PostgreSQL   │◄── backup diario (pg_dump)
                     │                            │               └──────────────┘
          ┌──────────┴─────────┐   colas Redis    │               ┌──────────────┐
          │ Celery worker(s)   │◄─────────────────┴──────────────►│ Redis        │ (broker, locks, cuotas,
          │  default/live/     │                                  │              │  rate limit, heartbeat, caché)
          │  notifications     │◄── Celery beat (1 instancia) ───►└──────────────┘
          └─────────┬──────────┘
                    │ HTTPS con reintentos, circuit breaker y cuota diaria
          ┌─────────▼──────────────────────────────────────────┐
          │ API-Football · API-Basketball · API-Tennis ·        │
          │ football-data.org · football-data.co.uk (históricos)│
          └─────────────────────────────────────────────────────┘
```

Todo el trabajo de actualización ocurre **en el servidor** (worker + beat). El navegador solo consulta la API y recibe
push: la plataforma sigue funcionando con el navegador cerrado o el teléfono apagado.

## Sistema automático 24/7

| Tarea (beat) | Frecuencia por defecto | Qué hace |
|---|---|---|
| `heartbeat` | 30 s | Marca de vida del planificador (la usa `/health/ready`) |
| `sync_live` | `LIVE_POLL_SECONDS` (60 s) | Solo si hay partidos en juego o a punto de empezar (ahorra cuota). Detecta eventos y cierra partidos que desaparecen del feed |
| `sync_fixtures` | 6 h | Calendario de ayer a +7 días: partidos nuevos, cambios de hora, aplazamientos |
| `sync_results` | 15 min | Cierra partidos que deberían haber terminado y siguen abiertos |
| `check_upcoming` | 5 min | Aviso de "partido próximo" según la antelación de cada usuario |
| `fanout_events` | 2 min (+ inmediato tras cada sync) | Reparte eventos pendientes a usuarios |
| `generate_predictions` | 1 h | Predicciones para partidos de las próximas 72 h |
| `resolve_predictions` | 15 min | Liquida predicciones de partidos finalizados |
| `watchdog` | 5 min | Alerta si un proveedor tiene el circuito abierto o lleva > 6 h sin respuestas válidas |
| `cleanup` | 24 h | Retención de datos (uso 400 d, notificaciones 180 d, tokens caducados) |

**Gestión de errores**
- `ResilientClient` (`app/providers/http.py`): hasta 3 intentos con backoff exponencial + *jitter* ante timeouts,
  errores de red, HTTP 429 y 5xx. Los 401/403 se tratan como permanentes (no se insiste con credenciales malas).
- *Circuit breaker*: 5 fallos consecutivos abren el circuito 5 minutos para no castigar a un proveedor caído.
- Cuota diaria por proveedor en Redis: nunca se supera el límite contratado (`*_DAILY_QUOTA`).
- Celery: `acks_late` + `reject_on_worker_lost` (si un worker muere, la tarea vuelve a la cola), reintentos con
  backoff en `sync_fixtures`/`sync_results`, límites de tiempo por tarea y *locks* en Redis que evitan ejecuciones solapadas.
- Si Redis cae, la API sigue respondiendo (límites y cuotas pasan a memoria del proceso).
- Cada ejecución se registra en `job_runs` (visible en Administración → Sistema).

**Idempotencia**: los partidos se identifican por `(proveedor, id_proveedor)`; reprocesar los mismos datos no
duplica nada. Las carreras entre tareas se resuelven con `SELECT … FOR UPDATE` y restricciones únicas.

## Notificaciones

1. `app/sync/detector.py` compara el estado anterior y el nuevo de cada partido y genera eventos:
   - Fútbol: inicio, inicio/fin del descanso, goles (el **marcador** es la fuente canónica; los eventos del proveedor solo
     aportan goleador y minuto), gol anulado (el marcador baja), amarillas, rojas, penalti fallado, cambios, final.
   - Básquet: inicio, final de cada cuarto, cambio de líder en el último cuarto/prórroga, parciales ≥ 10 puntos, final.
   - Tenis: inicio, final de cada set, cambio de marcador por juego, final.
2. Cada evento tiene una `dedup_key` estable con restricción única `(match_id, dedup_key)`: aunque el proveedor repita
   el dato o una tarea se reintente, el evento existe una sola vez. La primera vez que se ve un partido, o si empezó hace
   más de 6 h, los eventos se registran **sin notificar** (evita avalanchas tras una caída o una importación).
3. *Fan-out* (`app/notifications/service.py`): usuarios que siguen el partido, alguno de los equipos/jugadores o la
   competición → filtro por preferencias (por deporte y tipo de evento) → `user_notifications` con restricción única
   `(user_id, dedup_key)` → envío push si el usuario lo permite y no está en horas de silencio.
4. Web Push con VAPID (`pywebpush`). Las suscripciones caducadas (404/410) se eliminan solas. La notificación usa `tag`
   por partido para que el móvil agrupe las actualizaciones.

**Compatibilidad móvil**: Chrome/Edge/Firefox de escritorio y Android reciben push sin instalar nada. En iPhone/iPad
(iOS/iPadOS 16.4 o posterior) Apple solo permite Web Push si la web está **añadida a la pantalla de inicio**; la pantalla
de Configuración lo explica al usuario. Notificaciones nativas fuera de la PWA (FCM/APNs con app propia) quedarían para
una app nativa futura; el modelo de datos (`push_subscriptions`, preferencias, fan-out) ya está separado del canal.

## Datos principales (PostgreSQL)

`users`, `refresh_tokens`, `password_reset_tokens`, `usage_events`, `audit_logs`, `competitions`, `teams` (equipos y
jugadores de tenis), `matches`, `match_events`, `predictions`, `follows`, `user_notifications`, `push_subscriptions`,
`job_runs`. Migraciones en `backend/alembic/versions`.
