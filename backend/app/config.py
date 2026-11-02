"""Configuración central. Todos los secretos llegan por variables de entorno."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "SPORT AI PREDICTOR"
    public_web_url: str = "http://localhost:5173"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    log_level: str = "INFO"

    # --- Infraestructura ---
    database_url: str = "postgresql+psycopg://sportai:sportai@localhost:5432/sportai"
    redis_url: str = "redis://localhost:6379/0"

    # --- Seguridad ---
    jwt_secret: str = "dev-only-change-me-dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    password_reset_minutes: int = 30
    min_password_length: int = 10

    # Límites de peticiones de la API pública (por minuto)
    rate_limit_anonymous_per_min: int = 60
    rate_limit_auth_per_min: int = 10
    rate_limit_user_per_min: int = 120

    # --- Proveedores de datos (vacío = desactivado) ---
    api_football_key: str = ""
    api_basketball_key: str = ""
    api_tennis_key: str = ""
    football_data_org_key: str = ""
    # Cuotas diarias que el sistema NO superará (ajustar al plan contratado)
    api_football_daily_quota: int = 100
    api_basketball_daily_quota: int = 100
    api_tennis_daily_quota: int = 1000
    football_data_org_per_minute: int = 10
    # Competiciones a seguir por proveedor: "id:temporada" separados por coma
    api_football_leagues: str = "140:2026,39:2026,2:2026"
    api_basketball_leagues: str = "12:2026-2027,120:2026-2027"
    fixture_horizon_days: int = 7

    # --- Planificación 24/7 (segundos) ---
    live_poll_seconds: int = 60
    fixtures_sync_seconds: int = 6 * 3600
    results_sync_seconds: int = 15 * 60
    predictions_seconds: int = 3600
    upcoming_check_seconds: int = 300
    prediction_horizon_hours: int = 72

    # --- Notificaciones ---
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@example.com"
    alert_webhook_url: str = ""  # Slack/Discord/Teams para alertas operativas

    # --- Observabilidad ---
    sentry_dsn: str = ""

    # --- Modelos ---
    accuracy_target: float = 0.70  # objetivo experimental, nunca se fuerza

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _check_production(self):
        if self.environment == "production":
            if self.jwt_secret.startswith("dev-only") or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET debe definirse con al menos 32 caracteres en producción")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def parse_league_list(raw: str) -> list[tuple[str, str]]:
    out = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        lid, _, season = item.partition(":")
        out.append((lid.strip(), season.strip()))
    return out
