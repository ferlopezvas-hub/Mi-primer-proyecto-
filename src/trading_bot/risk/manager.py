"""Gestión de riesgo: tamaño de posición, stop-loss y límite de pérdida diaria."""

from __future__ import annotations

from trading_bot.config import RiskSettings


class RiskManager:
    def __init__(self, settings: RiskSettings) -> None:
        self.settings = settings

    def position_size(self, equity: float, price: float) -> float:
        """Cantidad a comprar para arriesgar `risk_per_trade` del capital hasta el stop.

        Se limita además a `max_position_pct` del capital.
        """
        if equity <= 0 or price <= 0:
            return 0.0
        risk_amount = equity * self.settings.risk_per_trade
        stop_distance = price * self.settings.stop_loss_pct
        quantity = risk_amount / stop_distance
        max_quantity = equity * self.settings.max_position_pct / price
        return min(quantity, max_quantity)

    def stop_price(self, entry_price: float) -> float:
        return entry_price * (1 - self.settings.stop_loss_pct)

    def daily_loss_exceeded(self, day_start_equity: float, current_equity: float) -> bool:
        if day_start_equity <= 0:
            return True
        loss = (day_start_equity - current_equity) / day_start_equity
        return loss >= self.settings.max_daily_loss_pct
