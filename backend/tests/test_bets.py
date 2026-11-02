from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Match, MatchStatus, Prediction, Sport
from app.sync.service import process
from tests.factories import dto


def _match(db, pid="b1", hours=3, **kw):
    process(db, "fake", [dto(pid=pid, start=datetime.now(UTC) + timedelta(hours=hours), **kw)])
    return db.scalar(select(Match).where(Match.provider_id == pid))


def test_bet_lifecycle_and_roi(client, db, auth):
    m = _match(db)
    db.add(Prediction(match_id=m.id, sport=Sport.football, engine="e", engine_version="v", market="1x2",
                      probabilities={"home": 0.55, "draw": 0.25, "away": 0.2}, predicted_outcome="home",
                      confidence=0.7, content_hash="h", created_at=datetime.now(UTC), kickoff_at=m.start_time))
    db.commit()
    r = client.post("/api/v1/bets", headers=auth, json={"match_id": m.id, "market": "1x2", "selection": "home",
                                                        "odds": 2.0, "stake": 10, "bookmaker": "Ecuabet"})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["model_pick"] == "home" and b["model_probability"] == 0.55 and b["expected_value"] == 0.1
    assert b["in_play"] is False
    r2 = client.post("/api/v1/bets", headers=auth, json={"match_id": m.id, "market": "over_under_2.5",
                                                         "selection": "over", "odds": 1.9, "stake": 10,
                                                         "bookmaker": "Betcris"})
    assert r2.status_code == 201 and r2.json()["model_pick"] is None
    assert client.post("/api/v1/bets", headers=auth, json={"match_id": m.id, "market": "1x2", "selection": "x",
                                                           "odds": 2, "stake": 1}).status_code == 400
    # termina 2-0: gana la 1 (home), gana la 2 (over) ... 2 goles -> under: pierde
    process(db, "fake", [dto(pid="b1", start=m.start_time, status=MatchStatus.finished, detail="FT", hs=2, as_=0)],
            notify=False)
    bets = {x["market"]: x for x in client.get("/api/v1/bets", headers=auth).json()}
    assert bets["1x2"]["status"] == "won" and bets["1x2"]["profit"] == 10.0
    assert bets["over_under_2.5"]["status"] == "lost" and bets["over_under_2.5"]["profit"] == -10.0
    s = client.get("/api/v1/bets/summary", headers=auth).json()
    assert s["overall"]["profit"] == 0.0 and s["overall"]["roi"] == 0.0 and s["overall"]["hit_rate"] == 0.5
    assert s["by_bookmaker"]["Ecuabet"]["profit"] == 10.0
    assert s["by_model"]["siguiendo_modelo"]["won"] == 1 and s["by_model"]["sin_prediccion"]["won"] == 0
    assert len(s["cumulative"]) == 2
    # las liquidadas no se pueden borrar
    assert client.delete(f"/api/v1/bets/{b['id']}", headers=auth).status_code == 400


def test_cannot_register_bet_on_finished_match(client, db, auth):
    m = _match(db, pid="old", hours=-5, status=MatchStatus.finished, detail="FT", hs=1, as_=0)
    r = client.post("/api/v1/bets", headers=auth, json={"match_id": m.id, "market": "1x2", "selection": "home",
                                                        "odds": 1.5, "stake": 5})
    assert r.status_code == 400


def test_live_bet_flag_and_manual_market(client, db, auth):
    m = _match(db, pid="live", hours=-1, status=MatchStatus.live, detail="2H", hs=0, as_=0)
    r = client.post("/api/v1/bets", headers=auth, json={"match_id": m.id, "market": "1x2", "selection": "draw",
                                                        "odds": 3.1, "stake": 5})
    assert r.json()["in_play"] is True
    r = client.post("/api/v1/bets", headers=auth, json={"market": "other", "selection": "Más de 9,5 córners",
                                                        "description": "Barcelona vs Alavés", "odds": 1.8, "stake": 4})
    bid = r.json()["id"]
    assert client.patch(f"/api/v1/bets/{bid}", headers=auth, json={"status": "won"}).json()["profit"] == 3.2
    other = client.get("/api/v1/bets/summary", headers=auth).json()["by_market"]["other"]
    assert other["profit"] == 3.2


def test_bets_are_private(client, db, auth):
    from tests.conftest import login, make_user

    r = client.post("/api/v1/bets", headers=auth, json={"market": "other", "selection": "x", "description": "d",
                                                        "odds": 2, "stake": 1})
    make_user(db, "otro@example.com")
    other = login(client, "otro@example.com")
    assert client.get("/api/v1/bets", headers=other).json() == []
    assert client.delete(f"/api/v1/bets/{r.json()['id']}", headers=other).status_code == 404
