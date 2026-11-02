"""Contrato común para cualquier proveedor de datos deportivos.

Añadir un proveedor nuevo = implementar `SportsProvider` y registrarlo en
`app/providers/registry.py`. El resto del sistema (sincronización, eventos,
motores) solo conoce estos DTO normalizados.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime

from app.models import MatchStatus, Sport


class ProviderError(Exception):
    """Error permanente (credenciales, petición inválida). No se reintenta."""


class ProviderTemporaryError(ProviderError):
    """Error transitorio (timeout, 5xx, 429). La tarea se reintenta con backoff."""


class QuotaExceededError(ProviderError):
    """Se alcanzó la cuota diaria configurada. Se espera al día siguiente."""


class CircuitOpenError(ProviderTemporaryError):
    """Demasiados fallos seguidos: se deja de llamar al proveedor durante un tiempo."""


@dataclass
class TeamDTO:
    provider_id: str
    name: str
    country: str = ""
    logo_url: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class CompetitionDTO:
    provider_id: str
    name: str
    season: str = ""
    country: str = ""
    logo_url: str | None = None


@dataclass
class EventDTO:
    # goal | own_goal | penalty_goal | yellow_card | red_card | substitution | goal_cancelled | penalty_missed
    type: str
    minute: int | None
    side: str | None  # home | away
    player: str = ""
    detail: str = ""
    extra_minute: int | None = None

    def fingerprint(self) -> str:
        base = f"{self.type}:{self.side}:{self.minute}:{self.extra_minute or 0}:{self.player.strip().lower()}"
        return base[:150]


@dataclass
class MatchDTO:
    provider_id: str
    sport: Sport
    home: TeamDTO
    away: TeamDTO
    start_time: datetime
    status: MatchStatus
    status_detail: str = ""
    elapsed: int | None = None
    home_score: int | None = None
    away_score: int | None = None
    periods: dict = field(default_factory=dict)
    competition: CompetitionDTO | None = None
    venue: str = ""
    surface: str = ""
    events: list[EventDTO] | None = None  # None = el proveedor no envía eventos detallados
    stats: dict = field(default_factory=dict)


class SportsProvider(ABC):
    name: str = "base"
    sport: Sport
    supports_live: bool = True

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def fixtures(self, date_from: date, date_to: date) -> list[MatchDTO]:
        """Calendario y resultados en un rango de fechas."""

    @abstractmethod
    def live(self) -> list[MatchDTO]:
        """Partidos en juego en este momento."""

    @abstractmethod
    def by_ids(self, provider_ids: list[str]) -> list[MatchDTO]:
        """Estado actual de partidos concretos (para cerrar resultados)."""

    def history(self, competition_id: str, season: str) -> list[MatchDTO]:  # pragma: no cover - opcional
        """Temporada completa (para alimentar los modelos)."""
        return []
