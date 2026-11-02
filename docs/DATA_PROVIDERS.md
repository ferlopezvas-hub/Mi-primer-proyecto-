# Proveedores de datos deportivos

Investigación realizada el 2 de noviembre de 2026. **Los precios y condiciones cambian a menudo y varias fuentes de
terceros se contradicen**: antes de contratar, confirma en la web oficial de cada proveedor, y para uso comercial pide
confirmación por escrito de que su licencia permite redistribuir datos (aunque sean derivados) a usuarios de pago.

## Resumen y recomendación

| Proveedor | Deportes | Directo | Plan gratuito | Precio orientativo | Uso comercial | Conector |
|---|---|---|---|---|---|---|
| **API-Football** (api-sports.io) | Fútbol (todas las ligas en todos los planes) | Sí, con eventos (goles, tarjetas, cambios) | 100 peticiones/día | Pro 7.500/día, Ultra 75.000/día; hasta 1,5 M/día. Las cifras en $/€ varían según la fuente: confirmar en la web | Revisar sus términos; los planes de pago están pensados para apps en producción | `ApiFootballProvider` ✅ |
| **API-Basketball** (api-sports.io) | NBA, Euroliga, ACB y otras | Marcador por cuartos | 100 peticiones/día | Misma estructura que API-Football | Igual que el anterior | `ApiBasketballProvider` ✅ |
| **API-Tennis** (api-tennis.com) | ATP, WTA, ITF, Challenger | Sí (sets, juego, saque) | Prueba | Desde ~40 $/mes (fuente de terceros, sin confirmar) | Confirmar con el proveedor | `ApiTennisProvider` ✅ |
| **football-data.org** | Fútbol (12 competiciones gratis) | En el plan gratuito los marcadores llegan con retraso | 10 peticiones/min | Planes de pago para directo | Términos sin cláusula clara para uso comercial gratuito: consultar | `FootballDataOrgProvider` ✅ (respaldo) |
| **Sportmonks** | Fútbol (2.200+ ligas), también cricket y F1 | Sí | Ligas seleccionadas para evaluación; prueba de 14 días | Desde 29 €/mes; planes con más ligas y llamadas; -20 % anual | Planes de pago y acuerdos a medida | Pendiente (implementable con el mismo contrato `SportsProvider`) |
| **Sportradar** | Todos | Sí, de grado profesional | No | Empresarial, bajo presupuesto | Sí, con contrato | No (para fase de escala) |
| **Goalserve** | Muchos, incluido tenis | Sí | Prueba de 30 días | Tenis ~150 $/mes (las páginas muestran cifras distintas) | Con contrato | No |
| **balldontlie** | NBA | Parcial | 5 peticiones/min (sin `/stats`, según un informe de terceros) | 9,99 $/mes (60/min), 39,99 $/mes (600/min) | No consta: consultar | No |
| **football-data.co.uk** | Históricos de fútbol en CSV (resultados, tiros, córners, cuotas) | No | Descarga libre de ficheros | Gratis | Revisar sus condiciones antes de uso comercial | Importador histórico ✅ |

**Recomendación para el lanzamiento**
1. **Fútbol**: API-Football en plan de pago (≥ Pro) como fuente principal: un único `live=<ligas>` cubre todos los
   partidos en juego en una llamada y trae los eventos que necesitan las notificaciones. football-data.org como respaldo
   de calendario y resultados.
2. **Baloncesto**: API-Basketball (misma cuenta y formato).
3. **Tenis**: API-Tennis.
4. **Históricos para entrenar**: football-data.co.uk (fútbol) + `history()` de API-Football/API-Basketball
   (una llamada por liga y temporada).
5. Al crecer: evaluar Sportmonks o Sportradar con contrato comercial explícito.

**Consumo estimado con API-Football** (por defecto): directo cada 60 s solo cuando hay partidos (≈ 1 llamada/minuto en
franjas de partido), calendario cada 6 h (1 llamada por liga), cierre de resultados cada 15 min (1 llamada por cada 20
partidos). Con 3 ligas y una jornada de fin de semana completa quedan unas 300-700 llamadas/día: **no cabe en el plan
gratuito de 100/día**; el sistema respeta igualmente la cuota configurada y lo indica en Administración.

## Lo que NO se hace

- **No hay scraping** de webs de resultados (Flashscore, SofaScore, etc.): sus condiciones lo prohíben. Los "scrapers" de
  marketplaces de terceros que aparecieron en la búsqueda se descartaron por ese motivo.
- No se usan los datos de tenis de Jeff Sackmann (licencia CC BY-NC-SA 4.0, **no comercial**) en producción.
- Las API keys nunca se envían al navegador ni se registran en logs.

## Añadir un proveedor

1. Crear `app/providers/<nombre>.py` con una clase que herede de `SportsProvider` e implemente `is_configured`,
   `fixtures`, `live` y `by_ids` (y opcionalmente `history`) devolviendo `MatchDTO`.
2. Usar `ResilientClient` para heredar reintentos, circuit breaker y cuotas.
3. Registrarlo en `app/providers/registry.py` (el orden define la prioridad por deporte).
4. Añadir pruebas de parseo con respuestas de ejemplo en `tests/test_providers.py`.

## Fuentes consultadas

- API-Football, precios: https://www.api-football.com/pricing · guía de cuotas: https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage
- Sportmonks, planes: https://www.sportmonks.com/football-api/plans-pricing · https://www.sportmonks.com/football-api/
- football-data.org, términos: https://api.football-data.org/register · límites del plan gratuito (terceros): https://www.thestatsapi.com/blog/football-data-org-free-tier-limits-2026
- Goalserve tenis: https://www.goalserve.com/sport-data-feeds/tennis-api/prices
- balldontlie: https://www.balldontlie.io/account/ · https://highlightly.net/blogs/best-nba-apis-in-2026
- Comparativas de terceros: https://highlightly.net/blogs/best-football-apis-in-2026 · https://api.market/blog/recodex/allsportsapi/best-sports-api
- football-data.co.uk (descarga de CSV): https://www.football-data.co.uk/
