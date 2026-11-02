"""Modelo de datos de SPORT AI PREDICTOR."""
from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Sport(str, enum.Enum):
    football = "football"
    basketball = "basketball"
    tennis = "tennis"


class MatchStatus(str, enum.Enum):
    scheduled = "scheduled"
    live = "live"
    finished = "finished"
    postponed = "postponed"
    cancelled = "cancelled"
    unknown = "unknown"


class Role(str, enum.Enum):
    user = "user"
    admin = "admin"


def _enum(e):
    return Enum(e, native_enum=False, length=20, validate_strings=True)


# ---------------------------------------------------------------- Usuarios
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[Role] = mapped_column(_enum(Role), default=Role.user)
    plan_code: Mapped[str] = mapped_column(String(32), default="free")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Madrid")
    notification_prefs: Mapped[dict] = mapped_column(JSONType, default=dict)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    follows: Mapped[list[Follow]] = relationship(back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family: Mapped[str] = mapped_column(String(32), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageEvent(Base):
    """Métricas de utilización (vista de predicción, búsqueda, login...)."""

    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_user_kind_time", "user_id", "kind", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- Deporte
class Competition(Base):
    __tablename__ = "competitions"
    __table_args__ = (UniqueConstraint("provider", "provider_id", "season"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[Sport] = mapped_column(_enum(Sport), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    provider_id: Mapped[str] = mapped_column(String(64))
    season: Mapped[str] = mapped_column(String(20), default="")
    name: Mapped[str] = mapped_column(String(160), index=True)
    country: Mapped[str] = mapped_column(String(80), default="")
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Team(Base):
    """Equipo (fútbol, básquet) o jugador/a (tenis)."""

    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("provider", "provider_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[Sport] = mapped_column(_enum(Sport), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    provider_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160), index=True)
    country: Mapped[str] = mapped_column(String(80), default="")
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONType, default=dict)  # ranking, etc.


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("provider", "provider_id"),
        Index("ix_matches_sport_start", "sport", "start_time"),
        Index("ix_matches_status_start", "status", "start_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[Sport] = mapped_column(_enum(Sport))
    provider: Mapped[str] = mapped_column(String(40))
    provider_id: Mapped[str] = mapped_column(String(64))
    competition_id: Mapped[int | None] = mapped_column(ForeignKey("competitions.id"), nullable=True, index=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[MatchStatus] = mapped_column(_enum(MatchStatus), default=MatchStatus.scheduled)
    status_detail: Mapped[str] = mapped_column(String(40), default="")  # p.ej. 1H, HT, Q3, SET2
    elapsed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    periods: Mapped[dict] = mapped_column(JSONType, default=dict)  # parciales / sets
    stats: Mapped[dict] = mapped_column(JSONType, default=dict)
    venue: Mapped[str] = mapped_column(String(160), default="")
    surface: Mapped[str] = mapped_column(String(20), default="")  # tenis
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    competition: Mapped[Competition | None] = relationship()
    home: Mapped[Team] = relationship(foreign_keys=[home_id])
    away: Mapped[Team] = relationship(foreign_keys=[away_id])


class MatchEvent(Base):
    """Evento detectado (gol, tarjeta, fin de cuarto...). dedup_key evita duplicados."""

    __tablename__ = "match_events"
    __table_args__ = (UniqueConstraint("match_id", "dedup_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    dedup_key: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    fanned_out: Mapped[bool] = mapped_column(Boolean, default=False)

    match: Mapped[Match] = relationship()


# ---------------------------------------------------------------- Predicciones
class Prediction(Base):
    """Predicción inmutable. Se guarda SIEMPRE antes del inicio del encuentro."""

    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint("match_id", "market", "engine_version", "is_backtest"),
        CheckConstraint("is_backtest OR created_at < kickoff_at", name="ck_prediction_before_kickoff"),
        Index("ix_predictions_eval", "sport", "is_backtest", "resolved_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    sport: Mapped[Sport] = mapped_column(_enum(Sport))
    competition_id: Mapped[int | None] = mapped_column(ForeignKey("competitions.id"), nullable=True)
    engine: Mapped[str] = mapped_column(String(40))
    engine_version: Mapped[str] = mapped_column(String(40))
    market: Mapped[str] = mapped_column(String(40))
    probabilities: Mapped[dict] = mapped_column(JSONType)
    predicted_outcome: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[dict] = mapped_column(JSONType, default=dict)
    data_quality: Mapped[dict] = mapped_column(JSONType, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    is_backtest: Mapped[bool] = mapped_column(Boolean, default=False)
    # Último dato utilizado por el modelo (en backtest: estrictamente anterior al partido)
    data_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # resolución (solo se rellena tras el final)
    actual_outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    brier: Mapped[float | None] = mapped_column(Float, nullable=True)
    log_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    match: Mapped[Match] = relationship()


IMMUTABLE_PREDICTION_FIELDS = (
    "match_id", "market", "engine", "engine_version", "probabilities", "predicted_outcome",
    "confidence", "explanation", "data_quality", "content_hash", "created_at", "kickoff_at", "is_backtest",
    "data_cutoff_at",
)


class ImmutablePredictionError(RuntimeError):
    pass


@event.listens_for(Prediction, "before_update")
def _forbid_prediction_edits(mapper, connection, target):  # noqa: ARG001
    from sqlalchemy import inspect

    state = inspect(target)
    for f in IMMUTABLE_PREDICTION_FIELDS:
        if state.attrs[f].history.has_changes():
            raise ImmutablePredictionError(f"El campo '{f}' de una predicción no puede modificarse")


# ---------------------------------------------------------------- Notificaciones
class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("user_id", "kind", "target_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # team | match | competition
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="follows")


class UserNotification(Base):
    __tablename__ = "user_notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedup_key"),
        Index("ix_notif_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("match_events.id", ondelete="SET NULL"), nullable=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSONType, default=dict)
    dedup_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------- Operación
class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_jobruns_name_started", "name", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|ok|error|skipped
    detail: Mapped[dict] = mapped_column(JSONType, default=dict)
