from __future__ import annotations

from app.models import Sport
from app.providers.api_sports import ApiBasketballProvider, ApiFootballProvider
from app.providers.api_tennis import ApiTennisProvider
from app.providers.base import SportsProvider
from app.providers.football_data_org import FootballDataOrgProvider

# Orden = prioridad. Para fútbol, si hay clave de API-Football se usa esa (tiene
# eventos en directo); football-data.org queda como respaldo.
_FACTORIES = [ApiFootballProvider, FootballDataOrgProvider, ApiBasketballProvider, ApiTennisProvider]
_override: list[SportsProvider] | None = None


def set_providers(providers: list[SportsProvider] | None) -> None:
    """Inyección para tests."""
    global _override
    _override = providers


def all_providers() -> list[SportsProvider]:
    if _override is not None:
        return list(_override)
    return [f() for f in _FACTORIES]


def active_providers() -> list[SportsProvider]:
    """Un proveedor por deporte: el primero configurado."""
    chosen: dict[Sport, SportsProvider] = {}
    for p in all_providers():
        if p.is_configured() and p.sport not in chosen:
            chosen[p.sport] = p
    return list(chosen.values())


def provider_by_name(name: str) -> SportsProvider | None:
    return next((p for p in all_providers() if p.name == name), None)
