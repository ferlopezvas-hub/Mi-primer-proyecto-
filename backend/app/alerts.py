"""Alertas operativas a un webhook (Slack, Discord, Teams...) con anti-spam."""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.store import safe

log = logging.getLogger(__name__)


def alert(key: str, text: str, every_seconds: int = 3600) -> bool:
    """Envía como máximo una alerta por `key` cada `every_seconds`."""
    if not safe(lambda r: r.set(f"alert:{key}", "1", ex=every_seconds, nx=True), default=True):
        return False
    log.error("ALERTA %s: %s", key, text)
    url = get_settings().alert_webhook_url
    if not url:
        return False
    try:
        httpx.post(url, json={"text": f"[SPORT AI PREDICTOR] {text}", "content": f"[SPORT AI PREDICTOR] {text}"},
                   timeout=10)
        return True
    except httpx.HTTPError as exc:
        log.warning("No se pudo enviar la alerta: %s", exc)
        return False
