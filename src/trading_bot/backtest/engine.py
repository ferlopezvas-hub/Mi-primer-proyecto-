"""Motor de backtesting (solo posiciones largas, una posición a la vez).

Reglas para evitar resultados engañosos:
- La señal de la vela `i` se ejecuta en la apertura de la vela `i + 1`.
- El stop-loss se comprueba con el mínimo de cada vela; si la vela abre por
  debajo del stop (gap), se sale al precio de apertura.
- Se aplican comisiones en cada compra y venta.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from trading_bot.risk import RiskManager
from trading_bot.strategies import Signal, Strategy


@dataclass(frozen=True)
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    exit_reason: str


@dataclass
class BacktestResult:
    initial_capital: float
    equity_curve: pd.Series
    trades: list[Trade] = field(default_factory=list)

    @property
    def final_equity(self) -> float:
        return float(self.equity_curve.iloc[-1]) if len(self.equity_curve) else self.initial_capital

    @property
    def total_return(self) -> float:
        return self.final_equity / self.initial_capital - 1

    @property
    def max_drawdown(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        return float((self.equity_curve / self.equity_curve.cummax() - 1).min())

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.pnl > 0 for t in self.trades) / len(self.trades)

    def summary(self) -> dict[str, float | int]:
        return {
            "capital_inicial": round(self.initial_capital, 2),
            "capital_final": round(self.final_equity, 2),
            "retorno_total_pct": round(self.total_return * 100, 2),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "operaciones": len(self.trades),
            "tasa_acierto_pct": round(self.win_rate * 100, 2),
        }


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        risk: RiskManager,
        initial_capital: float = 10_000.0,
        fee_rate: float = 0.001,
    ) -> None:
        self.strategy = strategy
        self.risk = risk
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate

    def run(self, df: pd.DataFrame) -> BacktestResult:
        signals = self.strategy.generate_signals(df)

        cash = self.initial_capital
        quantity = 0.0
        entry_price = stop = 0.0
        entry_cost = 0.0
        entry_time: pd.Timestamp | None = None
        trades: list[Trade] = []
        equity: list[float] = []

        current_day = None
        day_start_equity = cash

        def close_position(time: pd.Timestamp, price: float, reason: str) -> None:
            nonlocal cash, quantity
            proceeds = quantity * price * (1 - self.fee_rate)
            cash += proceeds
            trades.append(
                Trade(entry_time, time, entry_price, price, quantity, proceeds - entry_cost, reason)
            )
            quantity = 0.0

        for i, (time, bar) in enumerate(df.iterrows()):
            if time.date() != current_day:
                current_day = time.date()
                day_start_equity = cash + quantity * bar["open"]

            # 1) Ejecuta la señal de la vela anterior en la apertura actual.
            if i > 0:
                signal = signals.iloc[i - 1]
                if signal == Signal.SELL and quantity > 0:
                    close_position(time, bar["open"], "signal")
                elif (
                    signal == Signal.BUY
                    and quantity == 0
                    and not self.risk.daily_loss_exceeded(day_start_equity, cash)
                ):
                    price = bar["open"]
                    size = self.risk.position_size(cash, price)
                    size = min(size, cash / (price * (1 + self.fee_rate)))
                    if size > 0:
                        quantity = size
                        entry_price = price
                        entry_cost = size * price * (1 + self.fee_rate)
                        entry_time = time
                        stop = self.risk.stop_price(price)
                        cash -= entry_cost

            # 2) Stop-loss dentro de la vela.
            if quantity > 0 and bar["low"] <= stop:
                close_position(time, min(bar["open"], stop), "stop_loss")

            equity.append(cash + quantity * bar["close"])

        if quantity > 0:
            close_position(df.index[-1], df["close"].iloc[-1], "end_of_data")
            equity[-1] = cash

        return BacktestResult(
            initial_capital=self.initial_capital,
            equity_curve=pd.Series(equity, index=df.index, dtype=float),
            trades=trades,
        )
