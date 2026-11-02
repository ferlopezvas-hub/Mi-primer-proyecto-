"""Catálogo de eventos notificables y preferencias por defecto."""
from __future__ import annotations

import copy

EVENT_CATALOG: dict[str, dict[str, dict]] = {
    "football": {
        "upcoming": {"label": "Partido próximo", "default": True},
        "kickoff": {"label": "Inicio del partido", "default": True},
        "halftime_start": {"label": "Inicio del descanso", "default": True},
        "halftime_end": {"label": "Final del descanso", "default": False},
        "goal": {"label": "Goles", "default": True},
        "goal_cancelled": {"label": "Gol anulado (VAR)", "default": True},
        "yellow_card": {"label": "Tarjetas amarillas", "default": False},
        "red_card": {"label": "Tarjetas rojas", "default": True},
        "penalty_missed": {"label": "Penalti fallado", "default": True},
        "substitution": {"label": "Cambios de jugadores", "default": False},
        "full_time": {"label": "Final del encuentro", "default": True},
    },
    "basketball": {
        "upcoming": {"label": "Partido próximo", "default": True},
        "tipoff": {"label": "Inicio del encuentro", "default": True},
        "period_end": {"label": "Final de cada cuarto", "default": True},
        "lead_change": {"label": "Cambio de líder (último cuarto)", "default": True},
        "big_run": {"label": "Parcial importante (≥10 puntos)", "default": True},
        "full_time": {"label": "Final del encuentro", "default": True},
    },
    "tennis": {
        "upcoming": {"label": "Partido próximo", "default": True},
        "match_start": {"label": "Inicio del partido", "default": True},
        "set_end": {"label": "Final de cada set", "default": True},
        "game_score": {"label": "Cambio de marcador (cada juego)", "default": False},
        "full_time": {"label": "Final del partido", "default": True},
    },
}

DEFAULT_CHANNELS = {"push": True}  # el centro de notificaciones siempre registra
DEFAULT_UPCOMING_MINUTES = 30
ALLOWED_UPCOMING_MINUTES = (10, 15, 30, 60, 120)


def default_prefs() -> dict:
    return {
        "channels": dict(DEFAULT_CHANNELS),
        "upcoming_minutes": DEFAULT_UPCOMING_MINUTES,
        "quiet_hours": None,  # {"start": "23:00", "end": "08:00"} -> sin push en ese tramo
        "events": {sport: {k: v["default"] for k, v in evs.items()} for sport, evs in EVENT_CATALOG.items()},
    }


def merged_prefs(stored: dict | None) -> dict:
    prefs = default_prefs()
    stored = copy.deepcopy(stored or {})
    prefs["channels"].update({k: bool(v) for k, v in (stored.get("channels") or {}).items() if k in DEFAULT_CHANNELS})
    if stored.get("upcoming_minutes") in ALLOWED_UPCOMING_MINUTES:
        prefs["upcoming_minutes"] = stored["upcoming_minutes"]
    if "quiet_hours" in stored:
        prefs["quiet_hours"] = stored["quiet_hours"]
    for sport, evs in (stored.get("events") or {}).items():
        if sport in EVENT_CATALOG:
            for k, v in (evs or {}).items():
                if k in EVENT_CATALOG[sport]:
                    prefs["events"][sport][k] = bool(v)
    return prefs


def wants(prefs: dict, sport: str, event_type: str) -> bool:
    return bool(prefs["events"].get(sport, {}).get(event_type, False))
