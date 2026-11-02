import pytest

from app.config import Settings


def test_cors_origins_comma_separated(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.com, https://b.com")
    assert Settings().cors_origins == ["https://a.com", "https://b.com"]


def test_production_requires_strong_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "dev-only-change-me-dev-only-change-me")
    with pytest.raises(ValueError):
        Settings()
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    assert Settings().environment == "production"
