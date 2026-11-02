"""Logs estructurados en JSON (stdout) para agregadores como Better Stack, Loki o Datadog."""
from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from app.config import get_settings

_SECRET_HINTS = ("password", "token", "secret", "authorization", "api_key", "apikey")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in getattr(record, "extra_fields", {}).items():
            data[k] = "***" if any(h in k.lower() for h in _SECRET_HINTS) else v
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str, ensure_ascii=False)


def setup_logging() -> None:
    s = get_settings()
    root = logging.getLogger()
    if getattr(root, "_sportai_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if s.environment == "production" else
                         logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.handlers = [handler]
    root.setLevel(s.log_level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    root._sportai_configured = True  # type: ignore[attr-defined]
    if s.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=s.sentry_dsn, environment=s.environment, traces_sample_rate=0.05,
                        send_default_pii=False)
