"""Los partidos de estas pruebas son SIMULADOS (semilla fija) para verificar que los
modelos recuperan fuerzas conocidas. No representan resultados reales."""
import math
import random
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.engines.base import HistMatch, InsufficientData, canonical, confidence_score
from app.engines.basketball import BasketballEngine
from app.engines.football import FootballEngine
from app.engines.service import generate_upcoming
from app.engines.tennis import TennisEngine
from app.evaluation.backtest import walk_forward
from app.evaluation.metrics import brier, calibration, log_loss, wilson_interval
from app.evaluation.resolve import outcome, resolve_pending
from app.models import ImmutablePredictionError, Match, MatchStatus, Prediction, Sport
from app.sync.service import process
from tests.factories import dto

T0 = datetime(2025, 8, 1, tzinfo=UTC)


def _poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def sim_league(seed=1, rounds=4, n=10):
    rng = random.Random(seed)
    strength = {f"T{i}": 0.5 - i * 0.1 for i in range(n)}  # T0 el mejor
    out, d = [], T0
    for _ in range(rounds):
        for h in strength:
            for a in strength:
                if h == a:
                    continue
                lh = math.exp(0.15 + 0.25 + strength[h] - strength[a] * 0.8)
                la = math.exp(0.15 + strength[a] - strength[h] * 0.8)
                out.append(HistMatch(d, canonical(h), canonical(a), _poisson(rng, lh), _poisson(rng, la)))
                d += timedelta(hours=8)
    return out, d


def test_football_engine_recovers_strengths_and_is_coherent():
    hist, end = sim_league()
    e = FootballEngine()
    e.fit(hist, end)
    strong_home = e.predict("t0", "t9", end + timedelta(days=1))
    weak_home = e.predict("t9", "t0", end + timedelta(days=1))
    p1, p2 = strong_home[0].probabilities, weak_home[0].probabilities
    assert abs(sum(p1.values()) - 1) < 1e-3
    assert p1["home"] > 0.6 and p2["away"] > p2["home"]
    assert e.home_adv > 0  # se detecta ventaja local
    markets = {o.market for o in strong_home}
    assert markets == {"1x2", "over_under_2.5", "btts"}
    ex = strong_home[0].explanation
    assert ex["factors_for"] and "stats_used" in ex and strong_home[0].data_quality["matches_home_team"] > 0
    assert 0 <= strong_home[0].confidence <= 1


def test_football_engine_refuses_without_data():
    hist, end = sim_league()
    e = FootballEngine()
    e.fit(hist, end)
    with pytest.raises(InsufficientData):
        e.predict("t0", "equipo desconocido", end)
    e2 = FootballEngine()
    e2.fit(hist[:5], end)
    with pytest.raises(InsufficientData):
        e2.predict("t0", "t1", end)


def test_football_fit_ignores_future_data():
    hist, end = sim_league()
    cut = hist[len(hist) // 2].date
    e = FootballEngine()
    e.fit(hist, cut)
    assert all(m.date < cut for m in e.history)


def test_basketball_engine():
    rng = random.Random(3)
    rating = {f"B{i}": 10 - 2 * i for i in range(8)}
    hist, d = [], T0
    for _ in range(6):
        for h in rating:
            for a in rating:
                if h != a:
                    margin = rating[h] - rating[a] + 3 + rng.gauss(0, 11)
                    hp = int(105 + margin / 2)
                    ap = int(105 - margin / 2)
                    if hp == ap:
                        hp += 1
                    hist.append(HistMatch(d, canonical(h), canonical(a), hp, ap))
                    d += timedelta(hours=6)
    e = BasketballEngine()
    e.fit(hist, d)
    out = e.predict("b0", "b7", d + timedelta(days=1))[0]
    assert out.market == "moneyline" and out.probabilities["home"] > 0.75
    assert e.hca > 0


def test_tennis_engine_surface():
    rng = random.Random(5)
    skill = {"p0": 400, "p1": 200, "p2": 0, "p3": -200}
    clay_bonus = {"p3": 500}
    hist, d = [], T0
    players = list(skill)
    for _ in range(300):
        a, b = rng.sample(players, 2)
        surf = rng.choice(["hard", "clay"])
        sa = skill[a] + (clay_bonus.get(a, 0) if surf == "clay" else 0)
        sb = skill[b] + (clay_bonus.get(b, 0) if surf == "clay" else 0)
        p = 1 / (1 + 10 ** (-(sa - sb) / 400))
        hist.append(HistMatch(d, a, b, 2, 0, surf) if rng.random() < p else HistMatch(d, a, b, 0, 2, surf))
        d += timedelta(days=1)
    e = TennisEngine()
    e.fit(hist, d)
    hard = e.predict("p3", "p1", d, "hard")[0].probabilities["home"]
    clay = e.predict("p3", "p1", d, "clay")[0].probabilities["home"]
    assert clay > hard  # el especialista en tierra mejora en tierra
    assert e.predict("p0", "p3", d, "")[0].data_quality["warnings"]


def test_metrics():
    assert brier({"home": 1.0, "draw": 0, "away": 0}, "home") == 0
    assert brier({"home": 0.5, "away": 0.5}, "home") == pytest.approx(0.5)
    assert log_loss({"home": 0.5, "away": 0.5}, "home") == pytest.approx(math.log(2))
    assert log_loss({"home": 0.0, "away": 1.0}, "home") < 40  # recortado, no infinito
    c = calibration([(0.8, True), (0.8, False), (0.2, False)])
    assert c["n_points"] == 3 and c["ece"] is not None
    lo, hi = wilson_interval(70, 100)
    assert lo < 0.7 < hi
    assert confidence_score(30, 30, 3, [0.9, 0.1]) > confidence_score(3, 30, 300, [0.5, 0.5])


def _seed_league_in_db(db, n_finished_rounds=3):
    hist, end = sim_league(rounds=n_finished_rounds, n=6)
    dtos = [dto(pid=f"h{i}", start=h.date, status=MatchStatus.finished, detail="FT", hs=h.home_score,
                as_=h.away_score, home=h.home.upper(), away=h.away.upper()) for i, h in enumerate(hist)]
    process(db, "fake", dtos, notify=False)
    return end


def test_generate_predictions_are_stored_before_kickoff_and_immutable(db):
    _seed_league_in_db(db)
    now = datetime.now(UTC)
    process(db, "fake", [dto(pid="future", start=now + timedelta(hours=20), home="T0", away="T5"),
                         dto(pid="unknown", start=now + timedelta(hours=20), home="Nuevo", away="T1"),
                         dto(pid="far", start=now + timedelta(days=10), home="T1", away="T2")])
    # Fijamos 'now' dentro de la temporada simulada para que haya datos recientes
    stats = generate_upcoming(db, horizon_hours=72)
    assert stats["created"] == 3 and stats["insufficient"] == 1
    preds = db.scalars(select(Prediction)).all()
    assert all(p.created_at < p.kickoff_at and not p.is_backtest for p in preds)
    assert len({p.content_hash for p in preds}) == 3
    again = generate_upcoming(db, horizon_hours=72)
    assert again["created"] == 0 and again["already"] == 1
    p = preds[0]
    p.probabilities = {"home": 1.0, "draw": 0.0, "away": 0.0}
    with pytest.raises(ImmutablePredictionError):
        db.commit()
    db.rollback()
    m = db.scalar(select(Match).where(Match.provider_id == "unknown"))
    assert "insuficientes" in m.stats["prediction_note"]


def test_prediction_after_kickoff_rejected_by_database(db):
    process(db, "fake", [dto(pid="x", start=datetime.now(UTC) - timedelta(minutes=5))])
    m = db.scalar(select(Match))
    db.add(Prediction(match_id=m.id, sport=Sport.football, engine="e", engine_version="v", market="1x2",
                      probabilities={"home": 1}, predicted_outcome="home", confidence=0.5, content_hash="h",
                      created_at=datetime.now(UTC), kickoff_at=m.start_time, is_backtest=False))
    with pytest.raises(Exception):  # noqa: B017 - violación de CHECK
        db.commit()
    db.rollback()


def test_resolution_and_evaluation_api(client, db, auth):
    _seed_league_in_db(db)
    now = datetime.now(UTC)
    process(db, "fake", [dto(pid="f1", start=now + timedelta(hours=5), home="T0", away="T5")])
    generate_upcoming(db)
    process(db, "fake", [dto(pid="f1", start=now + timedelta(hours=5), home="T0", away="T5",
                             status=MatchStatus.finished, detail="FT", hs=3, as_=1)], notify=False)
    assert resolve_pending(db) == 3
    rep = client.get("/api/v1/evaluation?mode=live", headers=auth).json()
    assert rep["target_accuracy"] == 0.7
    assert rep["overall"]["n"] == 3 and rep["overall"]["conclusive"] is False
    assert set(rep["by_market"]) == {"football:1x2", "football:over_under_2.5", "football:btts"}
    assert rep["calibration"]["football:1x2"]["n_points"] == 3
    hist = client.get("/api/v1/predictions/history?state=resolved", headers=auth).json()
    assert len(hist) == 3 and hist[0]["result"]["actual_outcome"] in {"home", "over", "yes", "no", "under"}


def test_outcome_rules():
    class M:
        pass

    m = M()
    m.sport = Sport.football
    m.status = MatchStatus.finished
    m.home_score, m.away_score = 2, 2
    m.periods = {"fulltime": {"home": 1, "away": 1}}
    m.status_detail = "PEN"
    assert outcome("1x2", m) == "draw"  # se liquida a 90'
    assert outcome("over_under_2.5", m) == "under"
    m.status = MatchStatus.cancelled
    assert outcome("1x2", m) == "void"
    t = M()
    t.sport, t.status, t.status_detail = Sport.tennis, MatchStatus.finished, "Retired"
    t.home_score, t.away_score, t.periods = 1, 0, {"winner": "home"}
    assert outcome("match_winner", t) == "void"


def test_walk_forward_backtest_has_no_leakage(db):
    _seed_league_in_db(db, n_finished_rounds=4)
    first = db.scalar(select(Match.start_time).order_by(Match.start_time))
    last = db.scalar(select(Match.start_time).order_by(Match.start_time.desc()))
    start = first + (last - first) / 2
    stats = walk_forward(db, Sport.football, start, last + timedelta(days=1))
    assert stats["predictions"] > 0
    preds = db.scalars(select(Prediction).where(Prediction.is_backtest.is_(True))).all()
    for p in preds:
        assert p.data_cutoff_at <= p.kickoff_at
        assert p.resolved_at is not None
    # re-ejecutar no duplica
    assert walk_forward(db, Sport.football, start, last + timedelta(days=1))["predictions"] == 0


def test_prediction_view_limits_free_plan(client, db, auth, monkeypatch):
    from app.plans import PLANS

    _seed_league_in_db(db)
    now = datetime.now(UTC)
    process(db, "fake", [dto(pid=f"u{i}", start=now + timedelta(hours=5 + i), home="T0", away=f"T{i + 1}")
                         for i in range(3)])
    generate_upcoming(db)
    ids = [m.id for m in db.scalars(select(Match).where(Match.provider_id.like("u%"))).all()]
    from dataclasses import replace

    monkeypatch.setitem(PLANS, "free", replace(PLANS["free"], prediction_views_per_day=2))
    r = [client.get(f"/api/v1/predictions/match/{i}", headers=auth) for i in ids]
    assert [x.status_code for x in r] == [200, 200, 402]
    assert r[0].json()["limited"] is True and "stats_used" not in r[0].json()["predictions"][0]["explanation"]
    assert client.get(f"/api/v1/predictions/match/{ids[0]}", headers=auth).status_code == 200  # ya vista
