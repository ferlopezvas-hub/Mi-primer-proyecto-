"""Estrategia de cruce de medias móviles simples."""

from __future__ import annotations

import pandas as pd

from trading_bot.strategies.base import Signal, Strategy


class SmaCrossover(Strategy):
    """Compra cuando la media rápida cruza por encima de la lenta y vende al cruzar por debajo."""

    name = "sma_crossover"

    def __init__(self, fast: int = 20, slow: int = 50) -> None:
        if fast < 1 or slow < 1:
            raise ValueError("Los periodos deben ser mayores que 0.")
        if fast >= slow:
            raise ValueError("El periodo rápido debe ser menor que el lento.")
        self.fast = fast
        self.slow = slow

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        diff = close.rolling(self.fast).mean() - close.rolling(self.slow).mean()
        prev = diff.shift(1)

        signals = pd.Series(int(Signal.HOLD), index=df.index, dtype=int)
        signals[(diff > 0) & (prev <= 0)] = int(Signal.BUY)
        signals[(diff < 0) & (prev >= 0)] = int(Signal.SELL)
        return signals
