"""Acceso a Redis con degradación elegante.

Redis se usa para: límites de peticiones, cuotas de APIs, circuit breakers,
locks de tareas y latidos (heartbeat) del planificador. Si Redis cae, la API
sigue respondiendo usando un almacén en memoria del proceso.
"""
from __future__ import annotations

import logging
import threading
import time

import redis

from app.config import get_settings

log = logging.getLogger(__name__)


class MemoryStore:
    """Subconjunto mínimo de la API de Redis, para tests y modo degradado."""

    def __init__(self):
        self._d: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.Lock()

    def _alive(self, k):
        v = self._d.get(k)
        if v is None:
            return None
        if v[1] is not None and v[1] < time.time():
            del self._d[k]
            return None
        return v

    def get(self, k):
        with self._lock:
            v = self._alive(k)
            return v[0] if v else None

    def set(self, k, val, ex=None, nx=False):
        with self._lock:
            if nx and self._alive(k):
                return None
            self._d[k] = (str(val), time.time() + ex if ex else None)
            return True

    def incr(self, k, amount=1):
        with self._lock:
            v = self._alive(k)
            n = int(v[0]) + amount if v else amount
            self._d[k] = (str(n), v[1] if v else None)
            return n

    def expire(self, k, seconds):
        with self._lock:
            v = self._alive(k)
            if v:
                self._d[k] = (v[0], time.time() + seconds)
            return bool(v)

    def delete(self, *keys):
        with self._lock:
            return sum(1 for k in keys if self._d.pop(k, None) is not None)

    def ping(self):
        return True

    def flushall(self):
        with self._lock:
            self._d.clear()


_client = None
_memory = MemoryStore()


def get_store():
    global _client
    if _client is None:
        url = get_settings().redis_url
        if url.startswith("memory://"):
            _client = _memory
        else:
            _client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
    return _client


def set_store(client) -> None:
    global _client
    _client = client


def safe(fn, default=None):
    """Ejecuta una operación sobre Redis; si falla, usa el almacén en memoria."""
    try:
        return fn(get_store())
    except redis.RedisError as exc:  # pragma: no cover - depende de la red
        log.warning("Redis no disponible, modo degradado: %s", exc)
        try:
            return fn(_memory)
        except Exception:  # noqa: BLE001 - modo degradado: nunca romper la petición
            return default


def hit_counter(key: str, window_seconds: int) -> int:
    def _op(r):
        n = r.incr(key)
        if n == 1:
            r.expire(key, window_seconds)
        return n

    return safe(_op, default=0)


def acquire_lock(name: str, ttl: int) -> bool:
    return bool(safe(lambda r: r.set(f"lock:{name}", "1", ex=ttl, nx=True), default=False))


def release_lock(name: str) -> None:
    safe(lambda r: r.delete(f"lock:{name}"))
