"""Cliente HTTP resiliente: reintentos con backoff, circuit breaker y cuotas diarias."""
from __future__ import annotations

import logging
import random
import time
from datetime import UTC, datetime

import httpx
from prometheus_client import Counter

from app.providers.base import CircuitOpenError, ProviderError, ProviderTemporaryError, QuotaExceededError
from app.store import safe

log = logging.getLogger(__name__)
PROVIDER_CALLS = Counter("provider_requests_total", "Llamadas a proveedores", ["provider", "outcome"])

FAILURE_THRESHOLD = 5
OPEN_SECONDS = 300


def _day() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def quota_used(provider: str) -> int:
    v = safe(lambda r: r.get(f"quota:{provider}:{_day()}"), default=0)
    return int(v or 0)


def circuit_state(provider: str) -> dict:
    opened = safe(lambda r: r.get(f"cb:{provider}:open"))
    fails = safe(lambda r: r.get(f"cb:{provider}:fails"))
    last_ok = safe(lambda r: r.get(f"cb:{provider}:last_ok"))
    last_err = safe(lambda r: r.get(f"cb:{provider}:last_error"))
    return {"open": bool(opened), "consecutive_failures": int(fails or 0),
            "last_success": float(last_ok) if last_ok else None, "last_error": last_err}


class ResilientClient:
    def __init__(self, provider: str, base_url: str, headers: dict | None = None, daily_quota: int | None = None,
                 per_minute: int | None = None, timeout: float = 15.0, max_attempts: int = 3,
                 transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.provider = provider
        self.daily_quota = daily_quota
        self.per_minute = per_minute
        self.max_attempts = max_attempts
        self._sleep = sleep
        self._client = httpx.Client(base_url=base_url, headers=headers or {}, timeout=timeout, transport=transport)

    # -------------------------------------------------- control de cuotas
    def _reserve(self) -> None:
        if safe(lambda r: r.get(f"cb:{self.provider}:open")):
            raise CircuitOpenError(f"{self.provider}: circuito abierto tras fallos repetidos")
        if self.daily_quota is not None:
            key = f"quota:{self.provider}:{_day()}"

            def _op(r):
                n = r.incr(key)
                if n == 1:
                    r.expire(key, 2 * 86400)
                return n

            n = safe(_op, default=0)
            if n > self.daily_quota:
                PROVIDER_CALLS.labels(self.provider, "quota").inc()
                raise QuotaExceededError(f"{self.provider}: cuota diaria ({self.daily_quota}) alcanzada")
        if self.per_minute is not None:
            key = f"quota:{self.provider}:min:{int(time.time() // 60)}"

            def _opm(r):
                n = r.incr(key)
                if n == 1:
                    r.expire(key, 120)
                return n

            if safe(_opm, default=0) > self.per_minute:
                raise ProviderTemporaryError(f"{self.provider}: límite por minuto alcanzado")

    def _success(self) -> None:
        def _op(r):
            r.delete(f"cb:{self.provider}:fails")
            r.set(f"cb:{self.provider}:last_ok", str(time.time()))

        safe(_op)
        PROVIDER_CALLS.labels(self.provider, "ok").inc()

    def _failure(self, reason: str) -> None:
        def _op(r):
            n = r.incr(f"cb:{self.provider}:fails")
            r.set(f"cb:{self.provider}:last_error", reason[:300])
            if n >= FAILURE_THRESHOLD:
                r.set(f"cb:{self.provider}:open", "1", ex=OPEN_SECONDS)
                r.delete(f"cb:{self.provider}:fails")
                log.error("Circuito abierto para %s durante %ss: %s", self.provider, OPEN_SECONDS, reason)

        safe(_op)
        PROVIDER_CALLS.labels(self.provider, "error").inc()

    # -------------------------------------------------- petición
    def get_json(self, path: str, params: dict | None = None) -> dict | list:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._reserve()
            try:
                resp = self._client.get(path, params=params)
            except httpx.TimeoutException as exc:
                last_exc = ProviderTemporaryError(f"{self.provider}: timeout")
                self._failure(f"timeout: {exc}")
            except httpx.TransportError as exc:
                last_exc = ProviderTemporaryError(f"{self.provider}: error de red")
                self._failure(f"network: {exc}")
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = ProviderTemporaryError(f"{self.provider}: HTTP {resp.status_code}")
                    self._failure(f"HTTP {resp.status_code}")
                elif resp.status_code in (401, 403):
                    self._failure(f"HTTP {resp.status_code} (credenciales)")
                    raise ProviderError(f"{self.provider}: credenciales no válidas o sin permiso")
                elif resp.status_code >= 400:
                    raise ProviderError(f"{self.provider}: HTTP {resp.status_code}")
                else:
                    try:
                        data = resp.json()
                    except ValueError:
                        last_exc = ProviderTemporaryError(f"{self.provider}: respuesta no JSON")
                        self._failure("invalid json")
                    else:
                        self._success()
                        return data
            if attempt < self.max_attempts:
                delay = min(30.0, (2 ** (attempt - 1)) + random.uniform(0, 0.5))
                self._sleep(delay)
        assert last_exc is not None
        raise last_exc

    def close(self) -> None:
        self._client.close()
