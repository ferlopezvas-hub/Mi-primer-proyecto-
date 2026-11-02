"""Protección contra consultas excesivas (ventana fija por minuto)."""
from __future__ import annotations

import time

from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.store import hit_counter


def client_ip(request: Request) -> str:
    # Detrás de un proxy de confianza (Render/Fly/Nginx) se respeta X-Forwarded-For.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(bucket: str, identity: str, limit: int, window: int = 60) -> None:
    slot = int(time.time() // window)
    n = hit_counter(f"rl:{bucket}:{identity}:{slot}", window)
    if n > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas peticiones. Inténtalo de nuevo en unos segundos.",
            headers={"Retry-After": str(window - int(time.time()) % window)},
        )


def auth_rate_limit(request: Request) -> None:
    enforce("auth", client_ip(request), get_settings().rate_limit_auth_per_min)


def anon_rate_limit(request: Request) -> None:
    enforce("anon", client_ip(request), get_settings().rate_limit_anonymous_per_min)
