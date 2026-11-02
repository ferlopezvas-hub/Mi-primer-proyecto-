"""Creación del cliente ccxt para el exchange configurado."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ccxt

    from trading_bot.config import Settings


def create_exchange(settings: Settings, *, authenticated: bool = False) -> ccxt.Exchange:
    """Devuelve un cliente ccxt. Solo usa claves (y sandbox) si `authenticated` es True."""
    import ccxt

    try:
        exchange_cls = getattr(ccxt, settings.exchange.id)
    except AttributeError as exc:
        raise ValueError(f"Exchange no soportado por ccxt: {settings.exchange.id!r}") from exc

    options: dict = {"enableRateLimit": True}
    if authenticated:
        options["apiKey"] = settings.api_key
        options["secret"] = settings.api_secret

    exchange = exchange_cls(options)
    if authenticated and settings.exchange.sandbox:
        exchange.set_sandbox_mode(True)
    return exchange
