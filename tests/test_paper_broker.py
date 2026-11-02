import pytest

from trading_bot.execution import PaperBroker


def test_buy_and_sell_updates_balances():
    broker = PaperBroker(initial_cash=1_000, fee_rate=0.001)
    broker.buy("BTC/USDT", 1, 100)
    assert broker.get_position("BTC/USDT") == 1
    assert broker.get_cash("BTC/USDT") == pytest.approx(1_000 - 100.1)

    broker.sell("BTC/USDT", 1, 110)
    assert broker.get_position("BTC/USDT") == 0
    assert broker.get_cash("BTC/USDT") == pytest.approx(899.9 + 110 * 0.999)


def test_cannot_overspend_or_oversell():
    broker = PaperBroker(initial_cash=100)
    with pytest.raises(ValueError):
        broker.buy("BTC/USDT", 2, 100)
    with pytest.raises(ValueError):
        broker.sell("BTC/USDT", 1, 100)
