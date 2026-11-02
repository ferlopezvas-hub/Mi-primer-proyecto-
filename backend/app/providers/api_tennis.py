"""Adaptador para API-Tennis (api-tennis.com).

Documentación: https://api-tennis.com/documentation  (métodos get_fixtures y get_livescore)
La API key se envía como parámetro `APIkey` (así lo exige el proveedor). El cliente
HTTP nunca registra URLs completas, para no filtrarla en los logs.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from app.config import get_settings
from app.models import MatchStatus, Sport
from app.providers.base import CompetitionDTO, MatchDTO, ProviderError, SportsProvider, TeamDTO
from app.providers.http import ResilientClient


def _status(raw: str, live_flag: str) -> tuple[MatchStatus, str]:
    r = (raw or "").strip()
    rl = r.lower()
    if rl in ("finished", "retired", "walk over", "walkover") or rl.startswith("finished"):
        return MatchStatus.finished, r
    if rl in ("cancelled", "canceled", "abandoned"):
        return MatchStatus.cancelled, r
    if rl in ("postponed", "interrupted") and live_flag != "1":
        return MatchStatus.postponed, r
    if live_flag == "1" or rl.startswith("set"):
        return MatchStatus.live, r
    return MatchStatus.scheduled, r


def parse_tennis_event(item: dict) -> MatchDTO:
    status, detail = _status(item.get("event_status", ""), str(item.get("event_live", "0")))
    sets = []
    for s in item.get("scores") or []:
        try:
            sets.append({"set": int(s.get("score_set")), "home": int(float(s.get("score_first") or 0)),
                         "away": int(float(s.get("score_second") or 0))})
        except (TypeError, ValueError):
            continue
    sets.sort(key=lambda x: x["set"])
    home_sets = away_sets = None
    final = item.get("event_final_result") or ""
    if "-" in final:
        a, _, b = final.partition("-")
        if a.strip().isdigit() and b.strip().isdigit():
            home_sets, away_sets = int(a), int(b)
    start = datetime.fromisoformat(f"{item['event_date']}T{item.get('event_time') or '00:00'}")
    start = start.replace(tzinfo=UTC)  # api-tennis permite fijar la zona con `timezone`; pedimos UTC
    winner = item.get("event_winner") or ""
    return MatchDTO(
        provider_id=str(item["event_key"]),
        sport=Sport.tennis,
        home=TeamDTO(str(item.get("first_player_key")), item.get("event_first_player", ""),
                     logo_url=item.get("event_first_player_logo")),
        away=TeamDTO(str(item.get("second_player_key")), item.get("event_second_player", ""),
                     logo_url=item.get("event_second_player_logo")),
        start_time=start,
        status=status,
        status_detail=detail,
        home_score=home_sets,
        away_score=away_sets,
        periods={"sets": sets, "game": item.get("event_game_result") or "", "serve": item.get("event_serve"),
                 "winner": "home" if winner.startswith("First") else "away" if winner.startswith("Second") else None,
                 "round": item.get("tournament_round") or "", "type": item.get("event_type_type") or ""},
        competition=CompetitionDTO(str(item.get("tournament_key")), item.get("tournament_name", ""),
                                   str(item.get("tournament_season", ""))),
        surface=(item.get("tournament_surface") or item.get("event_surface") or "").lower(),
    )


class ApiTennisProvider(SportsProvider):
    name = "api-tennis"
    sport = Sport.tennis
    singles_only = True

    def __init__(self, client: ResilientClient | None = None):
        s = get_settings()
        self.key = s.api_tennis_key
        self._client = client or ResilientClient(self.name, "https://api.api-tennis.com",
                                                 daily_quota=s.api_tennis_daily_quota)

    def is_configured(self) -> bool:
        return bool(self.key)

    def _get(self, params: dict) -> list[dict]:
        data = self._client.get_json("/tennis/", {**params, "APIkey": self.key, "timezone": "UTC"})
        if isinstance(data, dict) and str(data.get("success")) not in ("1", "True", "true"):
            if data.get("error") or data.get("result") is None:
                raise ProviderError(f"api-tennis: {data.get('error') or 'respuesta sin éxito'}")
        items = (data or {}).get("result") or []
        if self.singles_only:
            items = [i for i in items if "doubles" not in (i.get("event_type_type") or "").lower()]
        return items

    def fixtures(self, date_from: date, date_to: date) -> list[MatchDTO]:
        return [parse_tennis_event(i) for i in self._get({"method": "get_fixtures",
                                                          "date_start": date_from.isoformat(),
                                                          "date_stop": date_to.isoformat()})]

    def live(self) -> list[MatchDTO]:
        return [parse_tennis_event(i) for i in self._get({"method": "get_livescore"})]

    def by_ids(self, provider_ids: list[str]) -> list[MatchDTO]:
        out = []
        for pid in provider_ids:
            out.extend(parse_tennis_event(i) for i in self._get({"method": "get_fixtures", "event_key": pid}))
        return out
