"""Adaptador para football-data.org v4 (alternativa/backup de calendario y resultados).

Documentación: https://docs.football-data.org/general/v4/index.html
Plan gratuito: 10 peticiones/minuto, 12 competiciones, marcadores con retraso
(sin eventos en directo). Útil como fuente secundaria y para resultados.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.config import get_settings
from app.models import MatchStatus, Sport
from app.providers.base import CompetitionDTO, MatchDTO, SportsProvider, TeamDTO
from app.providers.http import ResilientClient

STATUS = {
    "SCHEDULED": MatchStatus.scheduled, "TIMED": MatchStatus.scheduled,
    "IN_PLAY": MatchStatus.live, "PAUSED": MatchStatus.live, "LIVE": MatchStatus.live,
    "FINISHED": MatchStatus.finished, "AWARDED": MatchStatus.finished,
    "POSTPONED": MatchStatus.postponed, "SUSPENDED": MatchStatus.postponed,
    "CANCELLED": MatchStatus.cancelled,
}


def parse_fdo_match(m: dict) -> MatchDTO:
    comp, score = m.get("competition") or {}, m.get("score") or {}
    ft, ht = score.get("fullTime") or {}, score.get("halfTime") or {}
    raw = m.get("status", "")
    season = (m.get("season") or {}).get("startDate", "")[:4]
    return MatchDTO(
        provider_id=str(m["id"]),
        sport=Sport.football,
        home=TeamDTO(str(m["homeTeam"]["id"]), m["homeTeam"].get("name") or "", logo_url=m["homeTeam"].get("crest")),
        away=TeamDTO(str(m["awayTeam"]["id"]), m["awayTeam"].get("name") or "", logo_url=m["awayTeam"].get("crest")),
        start_time=datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")),
        status=STATUS.get(raw, MatchStatus.unknown),
        status_detail="HT" if raw == "PAUSED" else raw,
        elapsed=m.get("minute") if isinstance(m.get("minute"), int) else None,
        home_score=ft.get("home"),
        away_score=ft.get("away"),
        periods={"halftime": ht} if ht.get("home") is not None else {},
        competition=CompetitionDTO(str(comp.get("id")), comp.get("name", ""), season,
                                   (m.get("area") or {}).get("name", ""), comp.get("emblem")),
        events=None,
    )


class FootballDataOrgProvider(SportsProvider):
    name = "football-data-org"
    sport = Sport.football
    supports_live = False  # en el plan gratuito los marcadores llegan con retraso

    def __init__(self, client: ResilientClient | None = None):
        s = get_settings()
        self.key = s.football_data_org_key
        self._client = client or ResilientClient(self.name, "https://api.football-data.org/v4",
                                                 headers={"X-Auth-Token": self.key},
                                                 per_minute=s.football_data_org_per_minute)

    def is_configured(self) -> bool:
        return bool(self.key)

    def fixtures(self, date_from: date, date_to: date) -> list[MatchDTO]:
        out, start = [], date_from
        while start <= date_to:  # la API limita el rango a 10 días
            end = min(date_to, start + timedelta(days=9))
            data = self._client.get_json("/matches", {"dateFrom": start.isoformat(), "dateTo": end.isoformat()})
            out.extend(parse_fdo_match(m) for m in data.get("matches") or [])
            start = end + timedelta(days=1)
        return out

    def live(self) -> list[MatchDTO]:
        today = datetime.now(UTC).date()
        return [m for m in self.fixtures(today, today) if m.status == MatchStatus.live]

    def by_ids(self, provider_ids: list[str]) -> list[MatchDTO]:
        return [parse_fdo_match(self._client.get_json(f"/matches/{pid}")) for pid in provider_ids]
