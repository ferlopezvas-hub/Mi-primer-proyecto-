"""Datos SINTÉTICOS para pruebas automáticas. No son resultados reales."""
from __future__ import annotations

from datetime import datetime

from app.models import MatchStatus, Sport
from app.providers.base import CompetitionDTO, EventDTO, MatchDTO, SportsProvider, TeamDTO


def fx_football(fid=1001, status="NS", elapsed=None, home=None, away=None, events=None,
                date="2026-11-08T20:00:00+00:00", league_id=140, fulltime=None):
    item = {
        "fixture": {"id": fid, "date": date, "status": {"short": status, "elapsed": elapsed},
                    "venue": {"name": "Estadio Test"}},
        "league": {"id": league_id, "name": "La Liga", "country": "Spain", "season": 2026, "logo": None},
        "teams": {"home": {"id": 1, "name": "Equipo A", "logo": None}, "away": {"id": 2, "name": "Equipo B",
                                                                              "logo": None}},
        "goals": {"home": home, "away": away},
        "score": {"halftime": {"home": None, "away": None}, "fulltime": fulltime or {"home": None, "away": None}},
    }
    if events is not None:
        item["events"] = events
    return item


def goal_ev(minute, team_id, player, detail="Normal Goal"):
    return {"time": {"elapsed": minute, "extra": None}, "team": {"id": team_id}, "player": {"name": player},
            "type": "Goal", "detail": detail}


def card_ev(minute, team_id, player, color="Yellow Card"):
    return {"time": {"elapsed": minute, "extra": None}, "team": {"id": team_id}, "player": {"name": player},
            "type": "Card", "detail": color}


def dto(pid="m1", sport=Sport.football, status=MatchStatus.scheduled, detail="NS", hs=None, as_=None,
        start=None, events=None, periods=None, home="Equipo A", away="Equipo B", comp="La Liga", surface=""):
    return MatchDTO(provider_id=pid, sport=sport, home=TeamDTO(f"{home}-id", home), away=TeamDTO(f"{away}-id", away),
                    start_time=start or datetime.fromisoformat("2026-11-08T20:00:00+00:00"), status=status,
                    status_detail=detail, home_score=hs, away_score=as_, periods=periods or {},
                    competition=CompetitionDTO("c1", comp, "2026"), events=events, surface=surface)


class FakeProvider(SportsProvider):
    def __init__(self, sport=Sport.football, name="fake"):
        self.sport = sport
        self.name = name
        self.fixtures_data: list[MatchDTO] = []
        self.live_data: list[MatchDTO] = []
        self.by_id: dict[str, MatchDTO] = {}
        self.calls: list[str] = []

    def is_configured(self):
        return True

    def fixtures(self, date_from, date_to):
        self.calls.append("fixtures")
        return list(self.fixtures_data)

    def live(self):
        self.calls.append("live")
        return list(self.live_data)

    def by_ids(self, ids):
        self.calls.append(f"by_ids:{','.join(ids)}")
        return [self.by_id[i] for i in ids if i in self.by_id]


__all__ = ["EventDTO"]
