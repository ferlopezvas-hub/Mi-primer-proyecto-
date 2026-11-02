import pytest

from trading_bot.config import RiskSettings
from trading_bot.risk import RiskManager


@pytest.fixture
def risk():
    return RiskManager(
        RiskSettings(
            risk_per_trade=0.01, stop_loss_pct=0.02, max_position_pct=0.5, max_daily_loss_pct=0.03
        )
    )


def test_position_size_risks_fixed_fraction(risk):
    # 1% de 10.000 = 100 de riesgo; stop a 2 por unidad (2% de 100) -> 50 unidades,
    # pero el máximo es 50% del capital = 5.000 / 100 = 50 unidades.
    assert risk.position_size(10_000, 100) == pytest.approx(50)


def test_position_size_is_capped():
    tight = RiskManager(RiskSettings(risk_per_trade=0.05, stop_loss_pct=0.01, max_position_pct=0.1))
    assert tight.position_size(10_000, 100) == pytest.approx(10)  # 10% de 10.000 / 100


def test_position_size_invalid_inputs(risk):
    assert risk.position_size(0, 100) == 0
    assert risk.position_size(10_000, 0) == 0


def test_stop_price(risk):
    assert risk.stop_price(100) == pytest.approx(98)


def test_daily_loss_limit(risk):
    assert not risk.daily_loss_exceeded(10_000, 9_800)
    assert risk.daily_loss_exceeded(10_000, 9_700)
