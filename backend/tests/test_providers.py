import httpx
import pytest

from app.models import MatchStatus
from app.providers.api_sports import (
    ApiBasketballProvider,
    ApiFootballProvider,
    parse_basketball_game,
    parse_football_fixture,
)
from app.providers.api_tennis import parse_tennis_event
from app.providers.base import CircuitOpenError, ProviderError, ProviderTemporaryError, QuotaExceededError
from app.providers.football_data_org import parse_fdo_match
from app.providers.football_data_uk import parse_csv
from app.providers.http import ResilientClient, circuit_state, quota_used
from tests.factories import card_ev, fx_football, goal_ev


def _client(handler, **kw):
    return ResilientClient("test-prov", "https://api.test", transport=httpx.MockTransport(handler),
                           sleep=lambda s: None, **kw)


def test_parse_football_fixture_with_events():
    item = fx_football(status="2H", elapsed=67, home=2, away=1, events=[
        goal_ev(10, 1, "Pérez"), goal_ev(30, 2, "Smith"), goal_ev(60, 1, "Gómez", "Penalty"),
        card_ev(40, 2, "Jones"), card_ev(80, 2, "Brown", "Red Card"),
        {"time": {"elapsed": 50}, "team": {"id": 1}, "player": {"name": "X"}, "type": "subst", "detail": "Sub 1"},
    ])
    d = parse_football_fixture(item)
    assert d.status == MatchStatus.live and d.status_detail == "2H" and d.elapsed == 67
    assert (d.home_score, d.away_score) == (2, 1)
    types = [e.type for e in d.events]
    assert types == ["goal", "goal", "penalty_goal", "yellow_card", "red_card", "substitution"]
    assert d.events[1].side == "away"
    assert d.competition.name == "La Liga"


@pytest.mark.parametrize("short,expected", [("NS", MatchStatus.scheduled), ("HT", MatchStatus.live),
                                            ("FT", MatchStatus.finished), ("PEN", MatchStatus.finished),
                                            ("PST", MatchStatus.postponed), ("CANC", MatchStatus.cancelled),
                                            ("XYZ", MatchStatus.unknown)])
def test_football_status_mapping(short, expected):
    assert parse_football_fixture(fx_football(status=short)).status == expected


def test_parse_basketball_game():
    item = {"id": 55, "date": "2026-11-08T19:00:00+00:00", "status": {"short": "Q3", "timer": "4"},
            "league": {"id": 12, "name": "NBA", "season": "2026-2027"}, "country": {"name": "USA"},
            "teams": {"home": {"id": 1, "name": "Home BC"}, "away": {"id": 2, "name": "Away BC"}},
            "scores": {"home": {"quarter_1": 20, "quarter_2": 25, "quarter_3": 5, "total": 50},
                       "away": {"quarter_1": 22, "quarter_2": 18, "quarter_3": 2, "total": 42}}}
    d = parse_basketball_game(item)
    assert d.status == MatchStatus.live and d.status_detail == "Q3" and d.elapsed == 4
    assert d.home_score == 50 and d.periods["home"]["quarter_2"] == 25


def test_parse_tennis_event():
    item = {"event_key": 9, "event_date": "2026-11-08", "event_time": "12:30", "event_first_player": "P. Uno",
            "first_player_key": 1, "event_second_player": "P. Dos", "second_player_key": 2,
            "event_final_result": "1 - 0", "event_game_result": "30 - 15", "event_serve": "First Player",
            "event_winner": None, "event_status": "Set 2", "event_type_type": "Atp Singles",
            "tournament_name": "Test Open", "tournament_key": 77, "tournament_season": "2026", "event_live": "1",
            "scores": [{"score_first": "6", "score_second": "4", "score_set": "1"},
                       {"score_first": "2", "score_second": "3", "score_set": "2"}]}
    d = parse_tennis_event(item)
    assert d.status == MatchStatus.live
    assert (d.home_score, d.away_score) == (1, 0)
    assert d.periods["sets"][1] == {"set": 2, "home": 2, "away": 3}
    item.update(event_status="Finished", event_live="0", event_winner="First Player", event_final_result="2 - 0")
    d2 = parse_tennis_event(item)
    assert d2.status == MatchStatus.finished and d2.periods["winner"] == "home"


def test_parse_football_data_org():
    m = {"id": 1, "utcDate": "2026-11-08T20:00:00Z", "status": "PAUSED", "minute": 45,
         "competition": {"id": 2014, "name": "Primera Division"}, "area": {"name": "Spain"},
         "season": {"startDate": "2026-08-15"},
         "homeTeam": {"id": 10, "name": "A"}, "awayTeam": {"id": 11, "name": "B"},
         "score": {"fullTime": {"home": 1, "away": 0}, "halfTime": {"home": 1, "away": 0}}}
    d = parse_fdo_match(m)
    assert d.status == MatchStatus.live and d.status_detail == "HT" and d.home_score == 1


def test_parse_football_data_uk_csv():
    csv = ("Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS\n"
           "SP1,11/08/2023,18:30,Almeria,Vallecano,0,2,A,0,2,A,19,10\n"
           "SP1,12/08/2023,,Sevilla,Valencia,1,2,A,0,0,D,9,10\n")
    rows = parse_csv(csv, "SP1", "2023")
    assert len(rows) == 2
    assert rows[0].away.provider_id == "rayo vallecano"  # alias normalizado
    assert rows[0].periods["fulltime"] == {"home": 0, "away": 2}
    assert rows[1].start_time.hour == 15


def test_resilient_client_retries_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json={"ok": True})

    assert _client(handler).get_json("/x") == {"ok": True}
    assert calls["n"] == 3
    assert circuit_state("test-prov")["consecutive_failures"] == 0


def test_resilient_client_gives_up_with_temporary_error():
    c = _client(lambda req: httpx.Response(500), max_attempts=2)
    with pytest.raises(ProviderTemporaryError):
        c.get_json("/x")


def test_auth_errors_are_permanent():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401)

    with pytest.raises(ProviderError) as e:
        _client(handler).get_json("/x")
    assert not isinstance(e.value, ProviderTemporaryError)
    assert calls["n"] == 1  # sin reintentos


def test_daily_quota_enforced():
    c = _client(lambda req: httpx.Response(200, json={}), daily_quota=2)
    c.get_json("/a")
    c.get_json("/b")
    with pytest.raises(QuotaExceededError):
        c.get_json("/c")
    assert quota_used("test-prov") == 3


def test_circuit_breaker_opens():
    c = _client(lambda req: httpx.Response(502), max_attempts=5)
    with pytest.raises(ProviderTemporaryError):
        c.get_json("/x")
    assert circuit_state("test-prov")["open"] is True
    with pytest.raises(CircuitOpenError):
        c.get_json("/x")


def test_api_football_provider_uses_header_and_leagues(monkeypatch):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"errors": [], "response": [fx_football()]})

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "api_football_key", "KEY")
    monkeypatch.setattr(get_settings(), "api_football_leagues", "140:2026")
    p = ApiFootballProvider(client=ResilientClient("api-football", "https://x", headers={"x-apisports-key": "KEY"},
                                                   transport=httpx.MockTransport(handler)))
    from datetime import date

    out = p.fixtures(date(2026, 11, 1), date(2026, 11, 8))
    assert len(out) == 1
    assert seen[0].headers["x-apisports-key"] == "KEY"
    assert seen[0].url.params["league"] == "140"
    p.live()
    assert seen[1].url.params["live"] == "140"


def test_api_sports_error_payload_is_error(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "api_basketball_key", "KEY")
    p = ApiBasketballProvider(client=ResilientClient(
        "api-basketball", "https://x",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"errors": {"token": "invalid"}}))))
    with pytest.raises(ProviderError):
        p.live()


def test_parse_fixtures_only_future():
    from datetime import UTC, datetime

    from app.providers.football_data_uk import parse_fixtures

    csv = ("Div,Date,Time,HomeTeam,AwayTeam\nSP1,01/11/2026,15:15,Betis,Malaga\nSP1,08/11/2026,18:30,Betis,Celta\n"
           "XX9,08/11/2026,18:30,A,B\n")
    out = parse_fixtures(csv, "2026", now=datetime(2026, 11, 2, tzinfo=UTC))
    assert len(out) == 1 and out[0].status == MatchStatus.scheduled and out[0].home.provider_id == "real betis"
    # mismo identificador que tendrá el resultado al importarse después
    res = parse_csv("Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG\nSP1,08/11/2026,18:30,Betis,Celta,1,0\n", "SP1", "2026")
    assert res[0].provider_id == out[0].provider_id


def test_parse_football_statistics():
    from app.providers.api_sports import parse_football_statistics

    items = [{"team": {"id": 1}, "statistics": [{"type": "Corner Kicks", "value": 6}, {"type": "Offsides", "value": 2},
                                                {"type": "Ball Possession", "value": "58%"},
                                                {"type": "Yellow Cards", "value": None},
                                                {"type": "expected_goals", "value": "1.43"}]},
             {"team": {"id": 2}, "statistics": [{"type": "Corner Kicks", "value": 3},
                                                {"type": "Shots on Goal", "value": 4}]}]
    s = parse_football_statistics(items, "1")
    assert s["home"] == {"corners": 6, "offsides": 2, "possession": 58, "yellow_cards": 0, "xg": 1.43}
    assert s["away"] == {"corners": 3, "shots_on_target": 4}
