"""Bucle de trading en vivo (paper o real)."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from trading_bot.data import fetch_ohlcv
from trading_bot.execution import Broker
from trading_bot.risk import RiskManager
from trading_bot.strategies import Signal, Strategy

logger = logging.getLogger(__name__)


class TradingBot:
    def __init__(
        self,
        exchange,
        broker: Broker,
        strategy: Strategy,
        risk: RiskManager,
        symbol: str,
        timeframe: str,
        history: int = 200,
    ) -> None:
        self.exchange = exchange
        self.broker = broker
        self.strategy = strategy
        self.risk = risk
        self.symbol = symbol
        self.timeframe = timeframe
        self.history = history

        self.stop_price: float | None = None
        self._day = None
        self._day_start_equity = 0.0

    def _equity(self, price: float) -> float:
        return self.broker.get_cash(self.symbol) + self.broker.get_position(self.symbol) * price

    def step(self) -> None:
        """Una iteración: descarga velas, evalúa la señal y actúa."""
        df = fetch_ohlcv(self.exchange, self.symbol, self.timeframe, self.history + 1)
        closed = df.iloc[:-1]  # la última vela aún no ha cerrado
        if closed.empty:
            logger.warning("Sin datos suficientes todavía.")
            return

        signal = int(self.strategy.generate_signals(closed).iloc[-1])
        price = float(df["close"].iloc[-1])
        position = self.broker.get_position(self.symbol)
        equity = self._equity(price)

        today = datetime.now(UTC).date()
        if today != self._day:
            self._day, self._day_start_equity = today, equity

        logger.info(
            "Precio=%.2f señal=%s posición=%.6f capital=%.2f",
            price, Signal(signal).name, position, equity,
        )

        if position > 0 and self.stop_price is not None and price <= self.stop_price:
            logger.warning("Stop-loss alcanzado (%.2f). Cerrando posición.", self.stop_price)
            self._log_fill(self.broker.sell(self.symbol, position, price))
            self.stop_price = None
        elif signal == Signal.SELL and position > 0:
            self._log_fill(self.broker.sell(self.symbol, position, price))
            self.stop_price = None
        elif signal == Signal.BUY and position == 0:
            if self.risk.daily_loss_exceeded(self._day_start_equity, equity):
                logger.warning("Límite de pérdida diaria alcanzado: no se abren posiciones.")
                return
            cash = self.broker.get_cash(self.symbol)
            size = min(self.risk.position_size(equity, price), cash / price * 0.995)
            if size > 0:
                self._log_fill(self.broker.buy(self.symbol, size, price))
                self.stop_price = self.risk.stop_price(price)

    def run(self, once: bool = False) -> None:
        interval = self.exchange.parse_timeframe(self.timeframe)
        logger.info("Bot iniciado: %s %s (cada %ss)", self.symbol, self.timeframe, interval)
        while True:
            try:
                self.step()
            except Exception:
                logger.exception("Error en la iteración; se reintentará en el próximo ciclo.")
            if once:
                return
            time.sleep(interval)

    @staticmethod
    def _log_fill(fill) -> None:
        logger.info(
            "Orden ejecutada: %s %.6f %s @ %.2f (comisión %.4f)",
            fill.side, fill.quantity, fill.symbol, fill.price, fill.fee,
        )
