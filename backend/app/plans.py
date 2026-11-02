"""Planes de suscripción. Los pagos NO están implementados (ver docs/LEGAL.md)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    description: str
    prediction_views_per_day: int | None  # None = ilimitado
    max_follows: int
    full_explanations: bool
    push_notifications: bool
    live_events: bool
    history_days: int | None
    features: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["features"] = list(self.features)
        return d


PLANS: dict[str, Plan] = {
    "free": Plan(
        code="free", name="Gratis", description="Para descubrir la plataforma",
        prediction_views_per_day=10, max_follows=5, full_explanations=False,
        push_notifications=True, live_events=True, history_days=30,
        features=("calendar", "live", "evaluation"),
    ),
    "pro": Plan(
        code="pro", name="Pro", description="Análisis completo para aficionados exigentes",
        prediction_views_per_day=None, max_follows=50, full_explanations=True,
        push_notifications=True, live_events=True, history_days=365,
        features=("calendar", "live", "evaluation", "full_explanations", "advanced_filters"),
    ),
    "elite": Plan(
        code="elite", name="Elite", description="Para analistas y equipos",
        prediction_views_per_day=None, max_follows=500, full_explanations=True,
        push_notifications=True, live_events=True, history_days=None,
        features=("calendar", "live", "evaluation", "full_explanations", "advanced_filters", "export"),
    ),
}

DEFAULT_PLAN = "free"


def get_plan(code: str | None) -> Plan:
    return PLANS.get(code or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])
