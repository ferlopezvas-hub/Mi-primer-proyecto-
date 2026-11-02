# Motores de análisis y evaluación

Tres motores independientes con una interfaz común (`app/engines/base.py`): `fit(histórico, fecha_corte)` y
`predict(local, visitante, inicio, superficie)`. El histórico solo incluye partidos **anteriores** a la fecha de corte.

| Motor | Modelo | Mercados |
|---|---|---|
| **Football AI** (`football.py`) | Dixon-Coles (1997): Poisson con ataque/defensa por equipo, ventaja local estimada, corrección de marcadores bajos (ρ), decaimiento temporal ξ = 0,0019/día y regularización L2. Ventana de 2 años, por competición | 1X2, Más/Menos 2,5, Ambos marcan |
| **Basketball AI** (`basketball.py`) | Elo con multiplicador por margen de victoria y regresión a la media entre temporadas; ventaja de campo **estimada de los datos**; puntos esperados por medias ponderadas | Ganador (moneyline) + puntos y margen esperados informativos |
| **Tennis AI** (`tennis.py`) | Elo global + Elo por superficie (K dinámico 250/(n+5)^0,4), mezcla 50/50 si la superficie se conoce | Ganador del partido |

## Qué muestra cada predicción

- **Probabilidad estimada** de cada resultado (suma 1).
- **Confianza del modelo** (0-100, etiqueta alta/media/baja). *No es una probabilidad de acierto*: combina claridad de la
  predicción (60 %), suficiencia de datos (25 %) y actualidad (15 %).
- **Estadísticas utilizadas**: goles/puntos esperados, índices de ataque y defensa, Elo, forma, medias, cara a cara,
  marcadores más probables, nº de partidos en el modelo.
- **Tendencias** (rachas, forma reciente), **factores a favor** y **en contra** del resultado más probable.
- **Calidad y antigüedad de los datos**: partidos de cada equipo, días desde el último dato, fecha de corte, avisos.
- **Trazabilidad**: fecha de creación, inicio del partido, versión del motor y huella SHA-256.

Si no hay datos suficientes (p. ej. un equipo con < 5 partidos en la competición) **no se publica predicción** y se
explica el motivo. Es preferible no predecir a inventar.

## Integridad de las predicciones

1. Se guardan en `predictions` antes del partido: restricción `CHECK (is_backtest OR created_at < kickoff_at)`.
2. No se pueden modificar: validación en el ORM **y** trigger de PostgreSQL (migración `0002`) que rechaza cualquier
   cambio de probabilidades, resultado predicho, confianza, fechas o huella. Solo se rellenan los campos de resolución.
3. Una predicción por partido, mercado y versión del motor (restricción única): no se puede "probar suerte" varias veces.
4. Las predicciones de backtest se marcan `is_backtest = true`, guardan su `data_cutoff_at` y **nunca se mezclan** con las
   predicciones nuevas en la vista "Predicciones nuevas".

## Evaluación

`app/evaluation/` calcula sobre predicciones resueltas (excluye anuladas: partidos cancelados, retiradas en tenis,
empates en mercados de ganador):

- Porcentaje de aciertos con **intervalo de confianza del 95 %** (Wilson). Con < 30 casos se marca "muestra pequeña".
- **Brier** multiclase (0 = perfecto; se muestra junto al Brier de repartir la probabilidad a partes iguales).
- **Log loss**.
- **Calibración**: diagrama de fiabilidad por mercado y ECE.
- Desgloses por deporte, competición, tipo de predicción, nivel de confianza y modo (backtest / nuevas).
- Fútbol se liquida a 90 minutos (sin prórroga ni penaltis).

## Objetivo del 70 %

El objetivo es **experimental** y la plataforma lo muestra como referencia, nunca como resultado. Ningún parámetro
se ajusta para acercarse a él. Hay que tener en cuenta que en 1X2 de fútbol hay tres resultados posibles y el empate es
difícil de anticipar: la literatura y las propias casas de apuestas se mueven en torno al 50-55 % de acierto en ligas
grandes, así que un 70 % global en ese mercado no es realista. Donde sí puede acercarse es en **subconjuntos de alta
confianza**, y eso es lo que el panel permite comprobar.

## Resultados reales

Backtest *walk-forward* ejecutado el 2 de noviembre de 2026 con datos reales de football-data.co.uk (temporadas
2021/22 a 2026/27 en curso de LaLiga, Premier League, Serie A, Bundesliga y Ligue 1). Período evaluado:
1-ago-2023 → 2-nov-2026. Reajuste del modelo cada 7 días con datos estrictamente anteriores. 5.703 partidos; en 177 no
se predijo por datos insuficientes (equipos recién ascendidos al inicio de temporada). Reproducible con:

```bash
python -m app.cli import-history --divisions SP1,E0,I1,D1,F1 --seasons 2122,2223,2324,2425,2526,2627
python -m app.cli backtest --sport football --from 2023-08-01 --to 2026-11-03
python -m app.cli evaluation --mode backtest --full
```

| Mercado | N | Acierto | IC 95 % | Brier (azar) | Log loss | ECE |
|---|---|---|---|---|---|---|
| 1X2 | 5.526 | **52,9 %** | 51,6-54,2 % | 0,587 (0,667) | 0,985 | 0,007 |
| Ambos marcan | 5.526 | 55,2 % | 53,9-56,5 % | 0,497 (0,500) | 0,690 | 0,026 |
| Más/Menos 2,5 | 5.526 | 57,3 % | 56,0-58,6 % | 0,488 (0,500) | 0,682 | 0,031 |

Acierto por nivel de confianza (backtest):

| Mercado | Alta | Media | Baja |
|---|---|---|---|
| 1X2 | **65,7 %** (n = 2.147) | 45,5 % (n = 2.964) | 39,0 % (n = 415) |
| Más/Menos 2,5 | 64,0 % (n = 1.232) | 56,1 % (n = 3.300) | 52,6 % (n = 994) |
| Ambos marcan | 60,0 % (n = 527) | 54,7 % (n = 3.717) | 54,6 % (n = 1.282) |

1X2 por liga: Serie A 53,9 %, Ligue 1 53,1 %, LaLiga 53,0 %, Premier League 52,5 %, Bundesliga 51,6 %.

**Lectura honesta**
- 1X2 está **lejos del 70 %** (52,9 %), aunque muy bien calibrado (ECE 0,007): cuando dice 60 %, ocurre ~60 % de las veces.
- "Ambos marcan" apenas mejora al azar (Brier 0,497 frente a 0,500): tiene poco valor predictivo y la interfaz lo refleja
  con confianzas mayoritariamente medias/bajas. Más/Menos 2,5 aporta algo más. Ambos mercados son algo
  **sobreconfiados en los extremos** (el modelo de Poisson no recoge toda la variabilidad real).
- La confianza "alta" en 1X2 acierta 65,7 %. Advertencia: los pesos de la confianza se eligieron mirando este mismo
  backtest, así que la cifra puede ser algo optimista; la validación real será la de las **predicciones nuevas**, que la
  plataforma irá acumulando de forma inmutable.
- Baloncesto y tenis tienen sus motores probados con datos **simulados** en los tests (para verificar que recuperan
  fuerzas conocidas), pero **todavía no tienen backtest con datos reales**: no hay un histórico abierto con licencia
  comercial integrado. En cuanto se conecte API-Basketball o API-Tennis, `python -m app.cli backtest --sport basketball …`
  produce el mismo informe.

## Rentabilidad simulada con cuotas reales

Acertar no equivale a ganar dinero: depende de la cuota. Simulación con apuesta fija de 1 unidad a cada predicción del
backtest, usando la **cuota media del mercado** previa al partido que publica football-data.co.uk (mismo período y ligas):

| Estrategia | Apuestas | Beneficio | ROI |
|---|---|---|---|
| 1X2 · todas | 5.526 | −169,9 u | **−3,1 %** |
| 1X2 · solo confianza alta | 2.147 | −38,0 u | **−1,8 %** |
| 1X2 · "valor" (prob. × cuota > 1,05) | 1.545 | −134,7 u | −8,7 % |
| 1X2 · valor y confianza alta | 510 | −25,1 u | −4,9 % |
| Más/Menos 2,5 · todas | 5.526 | −238,9 u | −4,3 % |
| Más/Menos 2,5 · confianza alta | 1.232 | −61,8 u | −5,0 % |

**Ninguna estrategia es rentable.** La confianza alta acierta más (65,7 %), pero son sobre todo favoritos con cuotas
bajas, y el margen de las casas de apuestas se come la ventaja. El modelo no supera al mercado de apuestas, así que
la app **no debe venderse ni usarse como sistema de apuestas ganadoras**.

## Mejoras previstas (por orden de impacto esperado)

1. Calibración posterior (isotónica/Platt) entrenada en temporadas pasadas para corregir la sobreconfianza en Más/Menos y Ambos marcan.
2. Variables adicionales: tiros a puerta y córners (ya importados en `matches.stats`), descanso entre partidos, bajas.
3. Distribución binomial negativa para goles (sobredispersión).
4. Backtest real de baloncesto y tenis en cuanto haya proveedor contratado.
Cada cambio debe publicarse como nueva `engine_version`: las predicciones antiguas se conservan tal cual.
