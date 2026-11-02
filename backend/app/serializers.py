from __future__ import annotations

from app.models import Competition, Match, MatchEvent, Team


def team_out(t: Team | None) -> dict | None:
    if t is None:
        return None
    return {"id": t.id, "name": t.name, "country": t.country, "logo_url": t.logo_url, "sport": t.sport.value,
            "extra": t.extra or {}}


def competition_out(c: Competition | None) -> dict | None:
    if c is None:
        return None
    return {"id": c.id, "name": c.name, "country": c.country, "season": c.season, "sport": c.sport.value,
            "logo_url": c.logo_url}


def match_out(m: Match, brief: bool = True) -> dict:
    d = {
        "id": m.id,
        "sport": m.sport.value,
        "start_time": m.start_time,
        "status": m.status.value,
        "status_detail": m.status_detail,
        "elapsed": m.elapsed,
        "home": team_out(m.home),
        "away": team_out(m.away),
        "home_score": m.home_score,
        "away_score": m.away_score,
        "periods": m.periods or {},
        "competition": competition_out(m.competition),
        "surface": m.surface or None,
        "last_synced_at": m.last_synced_at,
        "source": m.provider,
    }
    if not brief:
        d["venue"] = m.venue
        d["stats"] = m.stats or {}
    return d


def event_out(e: MatchEvent) -> dict:
    return {"id": e.id, "type": e.type, "payload": e.payload, "created_at": e.created_at}
