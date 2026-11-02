# Despliegue

## Opciones evaluadas

| Componente | Recomendado | Alternativas | Motivo |
|---|---|---|---|
| Frontend (PWA) | **Vercel** (`frontend/vercel.json`) | Netlify, Cloudflare Pages | CDN global, HTTPS, despliegue por git, cabeceras de seguridad y `sw.js` sin caché |
| API + worker + beat | **Servidor cloud con Docker** (`docker-compose.yml`) o **Render** (`render.yaml`) | Fly.io, Railway, AWS ECS | Procesos persistentes 24/7: Vercel Functions **no sirve** para Celery ni para tareas programadas largas |
| PostgreSQL | Gestionado (Render, Neon, Supabase, RDS) o contenedor con volumen | — | Copias automáticas del proveedor + `backup.sh` propio |
| Redis | Gestionado (Render Key Value, Upstash con TCP, ElastiCache) o contenedor | — | Usar política `noeviction` (es broker de colas) |
| Monitorización | Sentry (errores), Better Stack/UptimeRobot (caídas), Prometheus+Grafana (métricas) | Datadog | Ver [OPERATIONS.md](OPERATIONS.md) |

## Opción A: un servidor (VPS) con docker-compose

1. Servidor con 2 vCPU / 4 GB RAM (p. ej. Hetzner, DigitalOcean, OVH), Docker instalado y DNS `api.tu-dominio.com` apuntando a él.
2. `git clone …` y `cp .env.example .env`; rellenar `JWT_SECRET`, `POSTGRES_PASSWORD`, `API_DOMAIN`, `CORS_ORIGINS`,
   claves de proveedores, VAPID (`docker compose run --rm api python -m app.cli vapid-keys`) y SMTP.
3. `docker compose up -d --build`. Caddy obtiene el certificado HTTPS automáticamente.
4. `docker compose exec api python -m app.cli create-admin --email tu@email.com`
5. (Opcional) `docker compose exec api python -m app.cli import-history` para entrenar con históricos.

Todos los servicios usan `restart: unless-stopped`: se recuperan solos de caídas y reinicios del servidor. `api` aplica
las migraciones al arrancar. **Solo debe haber un contenedor `beat`**; los `worker` pueden escalarse
(`docker compose up -d --scale worker=3`).

## Opción B: Render

`render.yaml` crea la API (con health check en `/health/ready`), el worker, el beat (1 instancia), PostgreSQL y Redis.
Completar en el panel las variables marcadas `sync: false`.

## Frontend en Vercel

1. Importar el repositorio y elegir `frontend` como *Root Directory* (Vercel detecta Vite).
2. Variable `VITE_API_URL=https://api.tu-dominio.com`.
3. En el backend, `CORS_ORIGINS` y `PUBLIC_WEB_URL` deben apuntar al dominio de Vercel.

## Comprobación tras desplegar

- `GET https://api.tu-dominio.com/health/ready` → `{"status":"ok"}` (base de datos, Redis y planificador vivos).
- Administración → Sistema: proveedores "Operativo" y tareas en estado `ok`.
- Configuración → Notificaciones push → Activar, seguir un equipo con partido próximo y verificar el aviso.

## Verificado en este repositorio

- Imagen Docker construida y arrancada: migraciones aplicadas, `/health/ready` OK, `/docs` oculto en producción,
  cabecera HSTS, proceso sin privilegios (`app`), worker Celery conectado. El arranque se niega con un `JWT_SECRET` débil.
- `backup.sh` probado con restauración completa en una base de datos nueva.
