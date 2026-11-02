"""Obtención de datos de mercado (velas OHLCV)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import ccxt

COLUMNS = ["open", "high", "low", "close", "volume"]


def ohlcv_to_dataframe(rows: list[list[float]]) -> pd.DataFrame:
    """Convierte la respuesta de ccxt ([ts, o, h, l, c, v]) en un DataFrame indexado por fecha."""
    df = pd.DataFrame(rows, columns=["timestamp", *COLUMNS])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


def fetch_ohlcv(
    exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int = 500
) -> pd.DataFrame:
    """Descarga las últimas `limit` velas, paginando si el exchange limita el tamaño."""
    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000
    since = exchange.milliseconds() - limit * timeframe_ms
    rows: list[list[float]] = []

    while len(rows) < limit:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=min(limit, 1000))
        if not batch:
            break
        rows.extend(batch)
        next_since = batch[-1][0] + timeframe_ms
        if next_since <= since:
            break
        since = next_since

    return ohlcv_to_dataframe(rows).tail(limit)


def load_csv(path: str | Path) -> pd.DataFrame:
    """Carga velas desde un CSV con columnas timestamp, open, high, low, close, volume."""
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en el CSV: {sorted(missing)}")
    return df.set_index("timestamp")[COLUMNS].astype(float).sort_index()
