"""Interfaz común para todas las estrategias."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import IntEnum

import pandas as pd


class Signal(IntEnum):
    SELL = -1
    HOLD = 0
    BUY = 1


class Strategy(ABC):
    """Una estrategia recibe velas OHLCV y devuelve una señal por vela.

    La señal de la vela `i` se calcula solo con datos hasta su cierre, por lo que
    debe ejecutarse en la vela siguiente (evita el sesgo de mirar al futuro).
    """

    name: str = "base"

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Devuelve una Serie de enteros (Signal) con el mismo índice que `df`."""
