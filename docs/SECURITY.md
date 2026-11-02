# Seguridad

| Área | Implementación | Dónde |
|---|---|---|
| Credenciales y secretos | Solo por variables de entorno (`.env` fuera de git, `.env.example` sin valores). En producción el arranque falla si `JWT_SECRET` tiene < 32 caracteres. Las API keys de proveedores nunca llegan al navegador ni a los logs (los campos con nombre sensible se enmascaran en logs JSON) | `app/config.py`, `app/logging_config.py` |
| Contraseñas | Argon2id con rehash automático; política mínima (10 caracteres, mayúsculas, minúsculas y números) | `app/security.py` |
| Sesiones | JWT de acceso de 15 min + refresh token opaco de 30 días guardado como hash SHA-256, **rotación** en cada uso y **detección de reutilización** (revoca toda la familia). `token_version` invalida todos los tokens al cambiar/restablecer contraseña, cerrar todas las sesiones o cambiar permisos | `app/api/auth.py` |
| Recuperación de contraseña | Token aleatorio de un solo uso, caduca en 30 min, guardado como hash; respuesta idéntica exista o no el email (sin enumeración de usuarios); al usarlo se cierran todas las sesiones | `app/api/auth.py` |
| Enumeración en login | Mismo mensaje y tiempo similar (verificación contra un hash ficticio) | `app/api/auth.py` |
| Control de acceso | Roles `user`/`admin` (`require_admin`), funciones por plan (`require_feature`), límites por plan (análisis/día, seguimientos), y cada usuario solo accede a sus propios datos (filtros por `user_id`) | `app/deps.py` |
| Consultas excesivas | Límite por IP en autenticación (10/min), por usuario (300/min) y anónimo; respuesta 429 con `Retry-After` | `app/ratelimit.py` |
| Límites de APIs externas | Cuota diaria y por minuto por proveedor + circuit breaker | `app/providers/http.py` |
| Cabeceras | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, HSTS en producción, `Cache-Control: no-store` en la API; CORS restringido a los orígenes configurados | `app/main.py`, `frontend/vercel.json` |
| Inyección SQL | Solo consultas parametrizadas con SQLAlchemy | — |
| Integridad de predicciones | `CHECK` antes del inicio + validación en el ORM + trigger de PostgreSQL de inmutabilidad + huella SHA-256 | `app/models.py`, migración `0002` |
| Auditoría | Cambios de rol, plan o estado y ejecuciones manuales de tareas quedan en `audit_logs` | `app/api/admin.py` |
| Privacidad (RGPD) | Borrado de cuenta por el propio usuario (con contraseña), retención limitada (uso 400 días, notificaciones 180 días), Sentry sin datos personales (`send_default_pii=False`) | `app/api/me.py`, `app/sync/jobs.py` |
| Contenedor | Usuario sin privilegios, sin `/docs` en producción, la API escucha solo en `127.0.0.1` tras Caddy (HTTPS) | `backend/Dockerfile`, `docker-compose.yml` |

## Pendiente antes de abrir al público

- Verificación de email en el registro y 2FA opcional para administradores.
- CAPTCHA o *proof-of-work* en registro si aparece abuso.
- Content-Security-Policy estricta en Vercel cuando se fijen los dominios de logos de los proveedores.
- Revisión de seguridad externa (pentest) y política de divulgación de vulnerabilidades.
- Los tokens se guardan en `localStorage`: es el compromiso habitual en SPA; si se quiere protección extra frente a XSS,
  mover el refresh token a una cookie `HttpOnly; Secure; SameSite=Strict` del dominio de la API.
