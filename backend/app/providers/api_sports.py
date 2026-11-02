"""Adaptadores para la familia API-SPORTS (API-Football v3 y API-Basketball v1).

Documentación: https://www.api-football.com/documentation-v3
               https://api-sports.io/documentation/basketball/v1
Autenticación por cabecera `x-apisports-key`. La cuota diaria depende del plan.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.config import get_settings, parse_league_list
from app.models import MatchStatus, Sport
from app.providers.base import CompetitionDTO, EventDTO, MatchDTO, ProviderError, SportsProvider, TeamDTO
from app.providers.http import ResilientClient

FOOTBALL_STATUS = {
    **{s: MatchStatus.scheduled for s in ("TBD", "NS")},
    **{s: MatchStatus.live for s in ("1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE")},
    **{s: MatchStatus.finished for s in ("FT", "AET", "PEN")},
    "PST": MatchStatus.postponed,
    **{s: MatchStatus.cancelled for s in ("CANC", "ABD", "AWD", "WO")},
}

BASKETBALL_STATUS = {
    "NS": MatchStatus.scheduled,
    **{s: MatchStatus.live for s in ("Q1", "Q2", "Q3", "Q4", "OT", "BT", "HT")},
    **{s: MatchStatus.finished for s in ("FT", "AOT")},
    "POST": MatchStatus.postponed,
    **{s: MatchStatus.cancelled for s in ("CANC", "SUSP", "AWD", "ABD")},
}


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _check_errors(data: dict) -> None:
    errors = data.get("errors")
    if errors and (isinstance(errors, dict) and errors or isinstance(errors, list) and len(errors)):
        raise ProviderError(f"API-SPORTS devolvió errores: {errors}")


# ------------------------------------------------------------------ fútbol
def parse_football_event(ev: dict, home_id: int | None) -> EventDTO | None:
    etype, detail = (ev.get("type") or "").lower(), (ev.get("detail") or "")
    dl = detail.lower()
    if etype == "goal":
        if "missed penalty" in dl:
            kind = "penalty_missed"
        elif "own goal" in dl:
            kind = "own_goal"
        elif "penalty" in dl:
            kind = "penalty_goal"
        else:
            kind = "goal"
    elif etype == "card":
        kind = "red_card" if "red" in dl else "yellow_card"
    elif etype == "subst":
        kind = "substitution"
    elif etype == "var" and ("cancel" in dl or "disallow" in dl):
        kind = "goal_cancelled"
    else:
        return None
    team_id = (ev.get("team") or {}).get("id")
    side = None if team_id is None or home_id is None else ("home" if team_id == home_id else "away")
    t = ev.get("time") or {}
    return EventDTO(type=kind, minute=t.get("elapsed"), extra_minute=t.get("extra"), side=side,
                    player=((ev.get("player") or {}).get("name") or ""), detail=detail)


def parse_football_fixture(item: dict) -> MatchDTO:
    fx, lg, teams = item["fixture"], item.get("league") or {}, item["teams"]
    goals, score = item.get("goals") or {}, item.get("score") or {}
    status = fx.get("status") or {}
    short = status.get("short") or ""
    home_id = teams["home"].get("id")
    events = None
    if "events" in item and item["events"] is not None:
        events = [e for e in (parse_football_event(ev, home_id) for ev in item["events"]) if e]
    return MatchDTO(
        provider_id=str(fx["id"]),
        sport=Sport.football,
        home=TeamDTO(str(home_id), teams["home"]["name"], logo_url=teams["home"].get("logo")),
        away=TeamDTO(str(teams["away"]["id"]), teams["away"]["name"], logo_url=teams["away"].get("logo")),
        start_time=_parse_dt(fx["date"]),
        status=FOOTBALL_STATUS.get(short, MatchStatus.unknown),
        status_detail=short,
        elapsed=status.get("elapsed"),
        home_score=goals.get("home"),
        away_score=goals.get("away"),
        periods={k: v for k, v in score.items() if v and v.get("home") is not None},
        competition=CompetitionDTO(str(lg.get("id")), lg.get("name", ""), str(lg.get("season", "")),
                                   lg.get("country", ""), lg.get("logo")) if lg else None,
        venue=((fx.get("venue") or {}).get("name") or ""),
        events=events,
    )


class ApiFootballProvider(SportsProvider):
    name = "api-football"
    sport = Sport.football

    def __init__(self, client: ResilientClient | None = None):
        s = get_settings()
        self.key = s.api_football_key
        self.leagues = parse_league_list(s.api_football_leagues)
        self._client = client or ResilientClient(
            self.name, "https://v3.football.api-sports.io", headers={"x-apisports-key": self.key},
            daily_quota=s.api_football_daily_quota,
        )

    def is_configured(self) -> bool:
        return bool(self.key)

    def _get(self, path: str, params: dict) -> list[dict]:
        data = self._client.get_json(path, params)
        _check_errors(data)
        return data.get("response") or []

    def _league_ids(self) -> set[str]:
        return {lid for lid, _ in self.leagues}

    def fixtures(self, date_from: date, date_to: date) -> list[MatchDTO]:
        out: list[MatchDTO] = []
        for lid, season in self.leagues:
            items = self._get("/fixtures", {"league": lid, "season": season,
                                            "from": date_from.isoformat(), "to": date_to.isoformat()})
            out.extend(parse_football_fixture(i) for i in items)
        return out

    def live(self) -> list[MatchDTO]:
        ids = self._league_ids()
        # live=all acepta filtrar ligas con guiones: una sola llamada para todas
        items = self._get("/fixtures", {"live": "-".join(sorted(ids)) if ids else "all"})
        return [parse_football_fixture(i) for i in items]

    def by_ids(self, provider_ids: list[str]) -> list[MatchDTO]:
        out: list[MatchDTO] = []
        for i in range(0, len(provider_ids), 20):  # la API admite hasta 20 ids por llamada
            chunk = provider_ids[i:i + 20]
            out.extend(parse_football_fixture(x) for x in self._get("/fixtures", {"ids": "-".join(chunk)}))
        return out

    def history(self, competition_id: str, season: str) -> list[MatchDTO]:
        return [parse_football_fixture(i) for i in self._get("/fixtures", {"league": competition_id,
                                                                            "season": season})]


# ------------------------------------------------------------------ baloncesto
def _quarters(scores: dict) -> dict:
    out = {}
    for k in ("quarter_1", "quarter_2", "quarter_3", "quarter_4", "over_time"):
        v = scores.get(k)
        if v is not None:
            out[k] = v
    return out


def parse_basketball_game(item: dict) -> MatchDTO:
    lg, teams, scores = item.get("league") or {}, item["teams"], item.get("scores") or {}
    status = item.get("status") or {}
    short = status.get("short") or ""
    hs, as_ = scores.get("home") or {}, scores.get("away") or {}
    timer = status.get("timer")
    return MatchDTO(
        provider_id=str(item["id"]),
        sport=Sport.basketball,
        home=TeamDTO(str(teams["home"]["id"]), teams["home"]["name"], logo_url=teams["home"].get("logo")),
        away=TeamDTO(str(teams["away"]["id"]), teams["away"]["name"], logo_url=teams["away"].get("logo")),
        start_time=_parse_dt(item["date"]),
        status=BASKETBALL_STATUS.get(short, MatchStatus.unknown),
        status_detail=short,
        elapsed=int(timer) if str(timer or "").isdigit() else None,
        home_score=hs.get("total"),
        away_score=as_.get("total"),
        periods={"home": _quarters(hs), "away": _quarters(as_)},
        competition=CompetitionDTO(str(lg.get("id")), lg.get("name", ""), str(lg.get("season", "")),
                                   (item.get("country") or {}).get("name", ""), lg.get("logo")) if lg else None,
    )


class ApiBasketballProvider(SportsProvider):
    name = "api-basketball"
    sport = Sport.basketball

    def __init__(self, client: ResilientClient | None = None):
        s = get_settings()
        self.key = s.api_basketball_key
        self.leagues = parse_league_list(s.api_basketball_leagues)
        self._client = client or ResilientClient(
            self.name, "https://v1.basketball.api-sports.io", headers={"x-apisports-key": self.key},
            daily_quota=s.api_basketball_daily_quota,
        )

    def is_configured(self) -> bool:
        return bool(self.key)

    def _get(self, path: str, params: dict) -> list[dict]:
        data = self._client.get_json(path, params)
        _check_errors(data)
        return data.get("response") or []

    def _games_on(self, d: date) -> list[MatchDTO]:
        ids = {lid for lid, _ in self.leagues}
        # Una llamada por día devuelve todas las ligas; se filtran las configuradas.
        items = self._get("/games", {"date": d.isoformat()})
        return [parse_basketball_game(i) for i in items if str((i.get("league") or {}).get("id")) in ids]

    def fixtures(self, date_from: date, date_to: date) -> list[MatchDTO]:
        out, d = [], date_from
        while d <= date_to:
            out.extend(self._games_on(d))
            d += timedelta(days=1)
        return out

    def live(self) -> list[MatchDTO]:
        today = datetime.now(UTC).date()
        return [m for m in self._games_on(today) if m.status == MatchStatus.live]

    def by_ids(self, provider_ids: list[str]) -> list[MatchDTO]:
        out = []
        for pid in provider_ids:
            out.extend(parse_basketball_game(i) for i in self._get("/games", {"id": pid}))
        return out

    def history(self, competition_id: str, season: str) -> list[MatchDTO]:
        return [parse_basketball_game(i) for i in self._get("/games", {"league": competition_id, "season": season})]
