"""Interfaz común para la ejecución de órdenes (simulada o real)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Fill:
    side: Literal["buy", "sell"]
    symbol: str
    quantity: float
    price: float
    fee: float


class Broker(ABC):
    @abstractmethod
    def get_cash(self, symbol: str) -> float:
        """Saldo disponible en la moneda de cotización (p. ej. USDT en BTC/USDT)."""

    @abstractmethod
    def get_position(self, symbol: str) -> float:
        """Cantidad mantenida de la moneda base (p. ej. BTC en BTC/USDT)."""

    @abstractmethod
    def buy(self, symbol: str, quantity: float, price: float) -> Fill:
        """Compra a mercado. `price` es el precio de referencia actual."""

    @abstractmethod
    def sell(self, symbol: str, quantity: float, price: float) -> Fill:
        """Vende a mercado. `price` es el precio de referencia actual."""
