"""Registro de estrategias disponibles."""

from __future__ import annotations

from typing import Any

from trading_bot.strategies.base import Signal, Strategy
from trading_bot.strategies.sma_crossover import SmaCrossover

STRATEGIES: dict[str, type[Strategy]] = {
    SmaCrossover.name: SmaCrossover,
}


def build_strategy(name: str, params: dict[str, Any] | None = None) -> Strategy:
    try:
        cls = STRATEGIES[name]
    except KeyError as exc:
        available = ", ".join(sorted(STRATEGIES))
        raise ValueError(f"Estrategia desconocida {name!r}. Disponibles: {available}") from exc
    return cls(**(params or {}))


__all__ = ["STRATEGIES", "Signal", "Strategy", "SmaCrossover", "build_strategy"]
