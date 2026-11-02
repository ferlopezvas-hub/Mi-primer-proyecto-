"""Broker real a través de ccxt. Envía órdenes de mercado al exchange."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from trading_bot.execution.base import Broker, Fill

if TYPE_CHECKING:
    import ccxt

logger = logging.getLogger(__name__)


class CcxtBroker(Broker):
    def __init__(self, exchange: ccxt.Exchange) -> None:
        self.exchange = exchange

    def _free_balance(self, currency: str) -> float:
        balance = self.exchange.fetch_balance()
        return float(balance.get("free", {}).get(currency) or 0.0)

    def get_cash(self, symbol: str) -> float:
        return self._free_balance(symbol.split("/")[1])

    def get_position(self, symbol: str) -> float:
        return self._free_balance(symbol.split("/")[0])

    def _fill_from_order(self, side: str, symbol: str, order: dict, price: float) -> Fill:
        fee = (order.get("fee") or {}).get("cost") or 0.0
        return Fill(
            side=side,  # type: ignore[arg-type]
            symbol=symbol,
            quantity=float(order.get("filled") or order.get("amount") or 0.0),
            price=float(order.get("average") or order.get("price") or price),
            fee=float(fee),
        )

    def buy(self, symbol: str, quantity: float, price: float) -> Fill:
        amount = float(self.exchange.amount_to_precision(symbol, quantity))
        logger.info("Enviando orden REAL de compra: %s %s", amount, symbol)
        order = self.exchange.create_market_buy_order(symbol, amount)
        return self._fill_from_order("buy", symbol, order, price)

    def sell(self, symbol: str, quantity: float, price: float) -> Fill:
        amount = float(self.exchange.amount_to_precision(symbol, quantity))
        logger.info("Enviando orden REAL de venta: %s %s", amount, symbol)
        order = self.exchange.create_market_sell_order(symbol, amount)
        return self._fill_from_order("sell", symbol, order, price)
