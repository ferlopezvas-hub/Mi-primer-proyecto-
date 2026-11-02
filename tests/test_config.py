import pytest

from trading_bot.config import load_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("TRADING_MODE", "EXCHANGE_API_KEY", "EXCHANGE_API_SECRET"):
        monkeypatch.delenv(var, raising=False)


def test_loads_default_config():
    settings = load_settings("config/settings.yaml", env_file=False)
    assert settings.trading.mode == "paper"
    assert settings.strategy.name == "sma_crossover"


def test_missing_file_uses_defaults(tmp_path):
    settings = load_settings(tmp_path / "no_existe.yaml", env_file=False)
    assert settings.trading.symbol == "BTC/USDT"


def test_live_mode_requires_keys(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    with pytest.raises(ValueError, match="EXCHANGE_API_KEY"):
        load_settings("config/settings.yaml", env_file=False)


def test_live_mode_with_keys(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("EXCHANGE_API_KEY", "clave-secreta-123")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    settings = load_settings("config/settings.yaml", env_file=False)
    assert settings.trading.mode == "live"
    assert "clave-secreta-123" not in repr(settings)
