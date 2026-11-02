"""Broker simulado: no envía órdenes reales, solo actualiza saldos en memoria."""

from __future__ import annotations

from collections import defaultdict

from trading_bot.execution.base import Broker, Fill


class PaperBroker(Broker):
    def __init__(self, initial_cash: float, fee_rate: float = 0.001) -> None:
        self.cash = initial_cash
        self.fee_rate = fee_rate
        self.positions: defaultdict[str, float] = defaultdict(float)

    def get_cash(self, symbol: str) -> float:
        return self.cash

    def get_position(self, symbol: str) -> float:
        return self.positions[symbol]

    def buy(self, symbol: str, quantity: float, price: float) -> Fill:
        if quantity <= 0:
            raise ValueError("La cantidad debe ser positiva.")
        cost = quantity * price
        fee = cost * self.fee_rate
        if cost + fee > self.cash + 1e-9:
            raise ValueError("Saldo insuficiente para la compra simulada.")
        self.cash -= cost + fee
        self.positions[symbol] += quantity
        return Fill("buy", symbol, quantity, price, fee)

    def sell(self, symbol: str, quantity: float, price: float) -> Fill:
        if quantity <= 0 or quantity > self.positions[symbol] + 1e-12:
            raise ValueError("Cantidad de venta no válida.")
        proceeds = quantity * price
        fee = proceeds * self.fee_rate
        self.cash += proceeds - fee
        self.positions[symbol] -= quantity
        return Fill("sell", symbol, quantity, price, fee)
