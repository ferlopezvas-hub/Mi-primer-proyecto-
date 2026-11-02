# Publicar SPORT AI PREDICTOR con servidor (paso a paso)

Esta guía publica **todo** en [Render](https://render.com) con un solo archivo (`render.yaml`):
la web, la API, el proceso 24/7 que sigue los partidos, la base de datos y Redis.
No hace falta usar la terminal.

**Tiempo:** unos 30-45 minutos. **Coste aproximado:** ~30-45 $/mes en Render más el plan de datos
(API-Football Pro). Confirma los precios actuales en render.com/pricing y api-football.com/pricing.

---

## Paso 1. Contrata los datos deportivos (API-Football)

1. Entra en https://www.api-football.com y crea una cuenta.
2. Elige un plan de pago (**Pro** o superior). El gratuito (100 llamadas/día) no alcanza para el directo.
3. En tu panel (Dashboard → *Account* / *My Access*) copia tu **API key**. Guárdala; la pegarás en el paso 3.

> Opcional: para baloncesto, la misma cuenta da acceso a API-Basketball (misma clave, se activa por
> separado en su web). Para tenis, crea cuenta en https://api-tennis.com.

## Paso 2. Crea tu cuenta en Render y conecta GitHub

1. Entra en https://render.com → **Get Started** → regístrate con **GitHub**.
2. Autoriza a Render a leer el repositorio `Mi-primer-proyecto-`.
3. Añade un método de pago en *Billing* (los servicios 24/7 son de pago).

## Paso 3. Crea todos los servicios con el Blueprint

1. En Render: **New +** → **Blueprint**.
2. Elige el repositorio `Mi-primer-proyecto-` y la rama **`claude/sport-ai-predictor-saas`**
   (o `main`, si ya fusionaste los cambios).
3. Render leerá `render.yaml` y mostrará 5 recursos: `sportai-api`, `sportai-worker`, `sportai-web`,
   `sportai-redis` y `sportai-db`.
4. Te pedirá los valores que no puede inventar. Rellena **solo**:
   - `API_FOOTBALL_KEY` → la clave del paso 1.
   - El resto puedes dejarlo **vacío** por ahora (se explican abajo).
5. Pulsa **Apply**. Render construye todo (10-15 minutos la primera vez).

Cuando todo esté en verde (*Live*), abre el servicio **sportai-web** y copia su dirección
(algo como `https://sportai-web.onrender.com`). **Esa es la dirección de tu app.**

## Paso 4. Crea tu cuenta y conviértete en administrador

1. Abre la dirección de tu app → **Crear cuenta** con tu email y una contraseña.
2. En Render: **Env Groups** → `sportai-secrets` → busca **`ADMIN_SETUP_CODE`** → pulsa el ojo para verlo y cópialo.
3. En la app: **Perfil** → tarjeta **Configuración inicial** → pega el código → **Activar**.
   Ahora verás **Administración** en el menú. (Este código solo funciona mientras no haya ningún administrador.)

## Paso 5. Carga los datos iniciales

1. En la app: **Administración** → pestaña **Sistema**.
2. Comprueba que **api-football** aparece como *Operativo*.
3. Pulsa **Cargar históricos y predicciones**. Tarda unos minutos: descarga 2-3 temporadas, calcula la
   prueba histórica (para medir la precisión) y genera las predicciones de los próximos partidos.
4. A partir de aquí el sistema trabaja solo, 24 horas al día:
   calendario cada 6 h, directo cada minuto cuando hay partidos, resultados, predicciones y avisos.

## Paso 6 (recomendado). Activa las notificaciones push

1. En Render: servicio **sportai-api** → **Shell** → escribe `python -m app.cli vapid-keys` y pulsa Enter.
2. Copia las dos líneas que aparecen (`VAPID_PUBLIC_KEY=…` y `VAPID_PRIVATE_KEY=…`).
3. **Env Groups** → `sportai-secrets` → pega cada valor en su variable y pon en `VAPID_SUBJECT`
   `mailto:tu@email.com` → **Save**. Render reinicia los servicios solo.
4. En la app: **Configuración** → **Activar** notificaciones. En iPhone, primero *Compartir → Añadir a pantalla de inicio*
   y abre la app desde ese icono.

## Paso 7 (recomendado). Correo para recuperar contraseñas

El registro y el inicio de sesión funcionan sin esto, pero para "¿Olvidaste la contraseña?" hace falta un servicio de
correo (por ejemplo Brevo, Resend o Mailgun, que tienen planes gratuitos). Copia sus datos SMTP en
`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` y `SMTP_FROM` dentro de `sportai-secrets`.

## Comprobaciones

- `https://<tu-api>.onrender.com/health/ready` debe responder `"status":"ok"`.
- Administración → Sistema: tareas en verde (`ok`).

## Qué ligas se siguen

Por defecto: LaLiga (140), Premier League (39), Serie A (135), Bundesliga (78), Ligue 1 (61) y Champions League (2),
temporada 2026/27. Para cambiarlas, edita `API_FOOTBALL_LEAGUES` en `sportai-secrets` (formato `id:temporada`,
separadas por comas). Más ligas = más llamadas a la API: vigila la cuota en Administración → Sistema.

## Importante sobre las predicciones

Son estimaciones estadísticas y **pueden fallar**. La app muestra siempre el acierto real medido y nunca promete
resultados. Si vas a cobrar o a relacionarla con apuestas, revisa antes [LEGAL.md](LEGAL.md): en España la
promoción del juego está regulada.

## Si algo falla

| Síntoma | Solución |
|---|---|
| La web carga pero dice "Sin conexión con el servidor" | Espera a que `sportai-api` esté *Live*; revisa sus *Logs* en Render |
| Proveedor "Sin API key" | Revisa `API_FOOTBALL_KEY` en `sportai-secrets` y guarda de nuevo |
| Proveedor "Circuito abierto" | La API de datos falla o la clave no es válida; mira el último error en Administración → Sistema |
| Sin predicciones | Pulsa de nuevo **Cargar históricos y predicciones**; solo hay predicciones en las 72 h previas a cada partido |
