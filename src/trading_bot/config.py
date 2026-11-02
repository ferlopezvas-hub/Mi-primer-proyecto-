"""Carga y validación de la configuración (YAML + variables de entorno)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

DEFAULT_CONFIG_PATH = Path("config/settings.yaml")


class ExchangeSettings(BaseModel):
    id: str = "binance"
    sandbox: bool = True


class TradingSettings(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    mode: Literal["paper", "live"] = "paper"
    paper_initial_cash: float = Field(10_000.0, gt=0)


class StrategySettings(BaseModel):
    name: str = "sma_crossover"
    params: dict[str, Any] = Field(default_factory=dict)


class RiskSettings(BaseModel):
    risk_per_trade: float = Field(0.01, gt=0, le=1)
    stop_loss_pct: float = Field(0.02, gt=0, lt=1)
    max_position_pct: float = Field(0.25, gt=0, le=1)
    max_daily_loss_pct: float = Field(0.03, gt=0, le=1)


class BacktestSettings(BaseModel):
    initial_capital: float = Field(10_000.0, gt=0)
    fee_rate: float = Field(0.001, ge=0, lt=1)
    candles: int = Field(1000, gt=0)


class Settings(BaseModel):
    exchange: ExchangeSettings = Field(default_factory=ExchangeSettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    backtest: BacktestSettings = Field(default_factory=BacktestSettings)

    # Secretos: solo desde variables de entorno, nunca desde el YAML.
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    api_secret: str | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def _live_requires_keys(self) -> Settings:
        if self.trading.mode == "live" and not (self.api_key and self.api_secret):
            raise ValueError(
                "El modo live requiere EXCHANGE_API_KEY y EXCHANGE_API_SECRET en el entorno."
            )
        return self


def load_settings(path: str | Path = DEFAULT_CONFIG_PATH, *, env_file: bool = True) -> Settings:
    """Lee el YAML de configuración y aplica las variables de entorno."""
    if env_file:
        load_dotenv()

    path = Path(path)
    data: dict[str, Any] = {}
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    mode = os.getenv("TRADING_MODE")
    if mode:
        data.setdefault("trading", {})["mode"] = mode.strip().lower()

    data["api_key"] = os.getenv("EXCHANGE_API_KEY") or None
    data["api_secret"] = os.getenv("EXCHANGE_API_SECRET") or None
    return Settings.model_validate(data)
