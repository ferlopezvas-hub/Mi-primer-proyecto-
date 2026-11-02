"""Configuración centralizada de logs (consola + archivo)."""

from __future__ import annotations

import logging
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO", log_dir: str | Path | None = "logs") -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_dir / "trading_bot.log", encoding="utf-8"))

    logging.basicConfig(level=level.upper(), format=LOG_FORMAT, handlers=handlers, force=True)
