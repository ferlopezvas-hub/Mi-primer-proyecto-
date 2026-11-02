import pytest

from trading_bot.strategies import Signal, SmaCrossover, build_strategy


def test_buy_signal_on_upward_cross(ohlcv_factory):
    df = ohlcv_factory([10, 10, 10, 10, 9, 8, 12, 14, 16])
    signals = SmaCrossover(fast=2, slow=4).generate_signals(df)
    assert Signal.BUY in signals.values
    assert signals.iloc[:4].eq(Signal.HOLD).all()  # sin datos suficientes, no hay señal


def test_sell_signal_on_downward_cross(ohlcv_factory):
    df = ohlcv_factory([10, 11, 12, 13, 14, 15, 10, 8, 6])
    signals = SmaCrossover(fast=2, slow=4).generate_signals(df)
    assert Signal.SELL in signals.values


def test_signals_do_not_look_ahead(ohlcv_factory):
    df = ohlcv_factory(list(range(1, 60)) + list(range(60, 0, -1)))
    strategy = SmaCrossover(fast=5, slow=20)
    full = strategy.generate_signals(df)
    partial = strategy.generate_signals(df.iloc[:80])
    assert full.iloc[:80].equals(partial)


@pytest.mark.parametrize("fast,slow", [(10, 10), (20, 5), (0, 5)])
def test_invalid_periods(fast, slow):
    with pytest.raises(ValueError):
        SmaCrossover(fast=fast, slow=slow)


def test_build_unknown_strategy():
    with pytest.raises(ValueError, match="desconocida"):
        build_strategy("no_existe")
