import numpy as np
import pytest

from trading_bot.backtest import BacktestEngine
from trading_bot.config import RiskSettings
from trading_bot.risk import RiskManager
from trading_bot.strategies import SmaCrossover


def make_engine(**risk_kwargs):
    return BacktestEngine(
        strategy=SmaCrossover(fast=3, slow=8),
        risk=RiskManager(RiskSettings(**risk_kwargs)),
        initial_capital=10_000,
        fee_rate=0.001,
    )


def test_flat_market_has_no_trades(ohlcv_factory):
    result = make_engine().run(ohlcv_factory([100] * 50))
    assert result.trades == []
    assert result.final_equity == pytest.approx(10_000)


def test_uptrend_after_dip_is_profitable(ohlcv_factory):
    closes = list(np.linspace(100, 90, 15)) + list(np.linspace(90, 150, 40))
    result = make_engine(stop_loss_pct=0.05, max_position_pct=1.0).run(ohlcv_factory(closes))
    assert len(result.trades) >= 1
    assert result.total_return > 0


def test_stop_loss_limits_loss(ohlcv_factory):
    closes = list(np.linspace(100, 90, 12)) + list(np.linspace(90, 110, 10)) + [60] * 10
    result = make_engine(stop_loss_pct=0.02, max_position_pct=1.0).run(ohlcv_factory(closes))
    stops = [t for t in result.trades if t.exit_reason == "stop_loss"]
    assert stops, "se esperaba al menos una salida por stop-loss"
    # La caída es del ~45%, pero con stop del 2% la pérdida total queda acotada.
    assert result.total_return > -0.05


def test_summary_keys(ohlcv_factory):
    summary = make_engine().run(ohlcv_factory(list(range(100, 160)))).summary()
    assert set(summary) == {
        "capital_inicial", "capital_final", "retorno_total_pct",
        "max_drawdown_pct", "operaciones", "tasa_acierto_pct",
    }
