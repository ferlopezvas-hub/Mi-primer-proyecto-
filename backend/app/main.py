from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram

from app.api import admin, auth, evaluation, health, me, notifications, predictions, sports
from app.config import get_settings
from app.logging_config import setup_logging

log = logging.getLogger("app")
REQUESTS = Counter("http_requests_total", "Peticiones HTTP", ["method", "route", "status"])
LATENCY = Histogram("http_request_seconds", "Latencia HTTP", ["route"])


def create_app() -> FastAPI:
    setup_logging()
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="1.0.0",
        docs_url="/docs" if s.environment != "production" else None,
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def observability(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("Error no controlado rid=%s %s %s", rid, request.method, request.url.path)
            response = JSONResponse({"detail": "Error interno", "request_id": rid}, status_code=500)
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        REQUESTS.labels(request.method, path, response.status_code).inc()
        LATENCY.labels(path).observe(time.perf_counter() - start)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        if s.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    app.include_router(health.router)
    for r in (auth.router, me.router, sports.router, predictions.router, evaluation.router,
              notifications.router, admin.router):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
