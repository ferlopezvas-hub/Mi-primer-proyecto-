# Trading Bot

Bot de trading de criptomonedas en Python con **backtesting**, **gestión de riesgo** y
**modo paper** (simulado) por defecto. Se conecta a más de 100 exchanges mediante
[ccxt](https://github.com/ccxt/ccxt).

> ⚠️ **Aviso:** este proyecto es educativo. Operar con criptomonedas implica riesgo de
> pérdida total. Valida siempre con backtest y modo paper antes de usar dinero real.

## Estructura

```
├── config/settings.yaml      # Símbolo, timeframe, estrategia y límites de riesgo
├── src/trading_bot/
│   ├── main.py               # CLI: backtest | run
│   ├── config.py             # Carga y validación de configuración (pydantic)
│   ├── exchange.py           # Cliente ccxt
│   ├── bot.py                # Bucle de trading en vivo
│   ├── data/                 # Descarga de velas OHLCV y carga desde CSV
│   ├── strategies/           # Estrategias (base + cruce de medias)
│   ├── risk/                 # Tamaño de posición, stop-loss, pérdida diaria máx.
│   ├── execution/            # Brokers: PaperBroker (simulado) y CcxtBroker (real)
│   ├── backtest/             # Motor de backtesting y métricas
│   └── utils/                # Logging
├── tests/                    # Pruebas con pytest (no requieren conexión)
├── notebooks/                # Análisis exploratorio
├── data/ · logs/             # Locales, ignorados por git
└── .github/workflows/ci.yml  # Lint + tests en cada push
```

## Instalación

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

## Uso

```bash
# Backtest descargando datos históricos del exchange configurado
trading-bot backtest

# Backtest con un CSV local (timestamp, open, high, low, close, volume)
trading-bot backtest --csv data/btc_1h.csv

# Bot en modo paper: una iteración o en bucle continuo
trading-bot run --once
trading-bot run
```

### Modo live (dinero real)

Requiere tres pasos deliberados:

1. Poner `EXCHANGE_API_KEY` y `EXCHANGE_API_SECRET` en `.env`.
2. Poner `TRADING_MODE=live` en `.env` (o `mode: live` en `settings.yaml`).
3. Ejecutar con `trading-bot run --confirm-live`.

Con `sandbox: true` (valor por defecto) las órdenes van a la testnet del exchange.
Crea claves **sin permiso de retirada** y, si es posible, restringidas por IP.

## Estrategia incluida: cruce de medias móviles

- **Compra** cuando la media rápida (`fast`, 20) cruza por encima de la lenta (`slow`, 50).
- **Vende** cuando cruza por debajo, o si salta el stop-loss.

Es un ejemplo para validar la arquitectura, **no** una estrategia rentable garantizada.

## Gestión de riesgo

| Parámetro            | Por defecto | Significado                                      |
|----------------------|-------------|--------------------------------------------------|
| `risk_per_trade`     | 1 %         | Capital que se arriesga hasta el stop-loss       |
| `stop_loss_pct`      | 2 %         | Distancia del stop respecto al precio de entrada |
| `max_position_pct`   | 25 %        | Tamaño máximo de una posición                    |
| `max_daily_loss_pct` | 3 %         | Pérdida diaria a partir de la cual no se opera   |

## Backtesting

El motor evita los errores más comunes:

- La señal de una vela se ejecuta en la **apertura de la siguiente** (sin mirar al futuro).
- Aplica **comisiones** en cada operación.
- El stop-loss se evalúa con el mínimo de la vela y respeta los *gaps* de apertura.

Métricas: capital final, retorno total, *max drawdown*, número de operaciones y tasa de acierto.

## Añadir una estrategia

1. Crea `src/trading_bot/strategies/mi_estrategia.py` heredando de `Strategy` e
   implementando `generate_signals(df)`, que devuelve `1` (compra), `-1` (venta) o `0`.
2. Regístrala en `STRATEGIES` dentro de `strategies/__init__.py`.
3. Selecciónala en `config/settings.yaml` (`strategy.name` y `strategy.params`).
4. Añade tests en `tests/`.

## Desarrollo

```bash
ruff check .     # lint
pytest           # tests
```

## Licencia

MIT. Ver [LICENSE](LICENSE).
