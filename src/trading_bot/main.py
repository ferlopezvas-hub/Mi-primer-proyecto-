"""Punto de entrada por línea de comandos.

Ejemplos:
    trading-bot backtest
    trading-bot backtest --csv data/btc_1h.csv
    trading-bot run --once
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from trading_bot.backtest import BacktestEngine
from trading_bot.bot import TradingBot
from trading_bot.config import DEFAULT_CONFIG_PATH, Settings, load_settings
from trading_bot.data import fetch_ohlcv, load_csv
from trading_bot.exchange import create_exchange
from trading_bot.execution import CcxtBroker, PaperBroker
from trading_bot.risk import RiskManager
from trading_bot.strategies import build_strategy
from trading_bot.utils.logging import setup_logging

logger = logging.getLogger("trading_bot")


def cmd_backtest(settings: Settings, args: argparse.Namespace) -> int:
    if args.csv:
        df = load_csv(args.csv)
    else:
        exchange = create_exchange(settings)
        df = fetch_ohlcv(
            exchange, settings.trading.symbol, settings.trading.timeframe,
            settings.backtest.candles,
        )
    logger.info("Backtest con %d velas (%s → %s)", len(df), df.index[0], df.index[-1])

    engine = BacktestEngine(
        strategy=build_strategy(settings.strategy.name, settings.strategy.params),
        risk=RiskManager(settings.risk),
        initial_capital=settings.backtest.initial_capital,
        fee_rate=settings.backtest.fee_rate,
    )
    result = engine.run(df)
    for key, value in result.summary().items():
        print(f"{key:>20}: {value}")
    return 0


def cmd_run(settings: Settings, args: argparse.Namespace) -> int:
    live = settings.trading.mode == "live"
    if live and not args.confirm_live:
        logger.error("Modo live configurado. Añade --confirm-live para operar con dinero real.")
        return 2

    if live:
        exchange = create_exchange(settings, authenticated=True)
        broker = CcxtBroker(exchange)
        logger.warning("MODO LIVE: se enviarán órdenes reales (sandbox=%s).",
                       settings.exchange.sandbox)
    else:
        exchange = create_exchange(settings)
        broker = PaperBroker(settings.trading.paper_initial_cash, settings.backtest.fee_rate)
        logger.info("Modo paper: las órdenes son simuladas.")

    bot = TradingBot(
        exchange=exchange,
        broker=broker,
        strategy=build_strategy(settings.strategy.name, settings.strategy.params),
        risk=RiskManager(settings.risk),
        symbol=settings.trading.symbol,
        timeframe=settings.trading.timeframe,
    )
    bot.run(once=args.once)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading-bot", description="Bot de trading en Python")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Ruta al YAML")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="Prueba la estrategia con datos históricos")
    bt.add_argument("--csv", help="Usa un CSV local en lugar de descargar datos")
    bt.set_defaults(func=cmd_backtest)

    run = sub.add_parser("run", help="Ejecuta el bot (paper por defecto)")
    run.add_argument("--once", action="store_true", help="Ejecuta una sola iteración")
    run.add_argument("--confirm-live", action="store_true", help="Confirma operar en real")
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
    except ValueError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    import ccxt

    try:
        return args.func(settings, args)
    except ccxt.NetworkError as exc:
        logger.error("No se pudo conectar con el exchange: %s", exc)
    except ccxt.BaseError as exc:
        logger.error("Error del exchange: %s", exc)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
    return 1


if __name__ == "__main__":
    sys.exit(main())
