"""Detección de eventos comparando el estado anterior y el nuevo de un partido.

Cada evento lleva una `dedup_key` estable: aunque el mismo dato llegue diez
veces (reintentos, varias tareas, proveedor que repite), solo se registra una vez
(restricción única match_id + dedup_key en base de datos).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Match, MatchStatus, Sport
from app.providers.base import EventDTO

GOAL_TYPES = {"goal", "own_goal", "penalty_goal"}


@dataclass
class DetectedEvent:
    type: str
    dedup_key: str
    payload: dict = field(default_factory=dict)


def snapshot(m: Match) -> dict:
    return {"status": m.status, "detail": m.status_detail or "", "home": m.home_score, "away": m.away_score,
            "periods": dict(m.periods or {}), "elapsed": m.elapsed}


def _score(m: Match) -> dict:
    return {"home": m.home_score, "away": m.away_score}


def detect(sport: Sport, prev: dict | None, m: Match, events: list[EventDTO] | None,
           cancellations: int = 0) -> list[DetectedEvent]:
    if prev is None:
        return []
    if sport == Sport.football:
        return _football(prev, m, events, cancellations)
    if sport == Sport.basketball:
        return _basketball(prev, m)
    if sport == Sport.tennis:
        return _tennis(prev, m)
    return []


# ------------------------------------------------------------------ fútbol
def _football(prev: dict, m: Match, events: list[EventDTO] | None, cancellations: int) -> list[DetectedEvent]:
    out: list[DetectedEvent] = []
    st, pst = m.status, prev["status"]
    detail, pdetail = m.status_detail or "", prev["detail"]
    started = pst != MatchStatus.live and st == MatchStatus.live
    if started or (pst == MatchStatus.scheduled and st == MatchStatus.finished):
        out.append(DetectedEvent("kickoff", "kickoff", {"score": _score(m)}))
    if detail == "HT" and pdetail != "HT":
        out.append(DetectedEvent("halftime_start", "ht_start", {"score": _score(m)}))
    if pdetail == "HT" and detail in ("2H", "ET", "P", "FT", "AET", "PEN"):
        out.append(DetectedEvent("halftime_end", "ht_end", {"score": _score(m)}))

    # Goles: el marcador es la fuente canónica (los eventos solo enriquecen).
    h0, a0 = prev["home"] or 0, prev["away"] or 0
    h1, a1 = m.home_score or 0, m.away_score or 0
    goal_events = {"home": [], "away": []}
    for e in events or []:
        if e.type in GOAL_TYPES and e.side in goal_events:
            goal_events[e.side].append(e)
    for side in goal_events:
        goal_events[side].sort(key=lambda e: ((e.minute or 0), (e.extra_minute or 0)))
    for side, start, end in (("home", h0, h1), ("away", a0, a1)):
        for n in range(start + 1, end + 1):
            idx = n - 1
            ev = goal_events[side][idx] if idx < len(goal_events[side]) else None
            out.append(DetectedEvent("goal", f"goal:{side}:{n}:c{cancellations}", {
                "side": side, "score": _score(m), "side_goal_number": n,
                "minute": ev.minute if ev else m.elapsed, "player": ev.player if ev else "",
                "detail": ev.detail if ev else "",
            }))
    if h1 < h0 or a1 < a0:
        out.append(DetectedEvent("goal_cancelled", f"cancel:{h0}-{a0}->{h1}-{a1}:c{cancellations}",
                                 {"score": {"home": h1, "away": a1}}))

    yellow_seen: dict[str, int] = {}
    for e in events or []:
        player = e.player.strip().lower()
        if e.type == "yellow_card":
            k = f"{e.side}:{player}"
            yellow_seen[k] = yellow_seen.get(k, 0) + 1
            key = f"yellow:{k}:{yellow_seen[k]}"
        elif e.type == "red_card":
            key = f"red:{e.side}:{player}"
        elif e.type == "substitution":
            key = f"sub:{e.side}:{player}:{e.minute}"
        elif e.type == "penalty_missed":
            key = f"penmiss:{e.side}:{player}:{e.minute}"
        else:
            continue
        out.append(DetectedEvent(e.type, key[:150], {"side": e.side, "minute": e.minute, "player": e.player,
                                                       "detail": e.detail, "score": _score(m)}))

    if st == MatchStatus.finished and pst != MatchStatus.finished:
        out.append(DetectedEvent("full_time", "ft", {"score": _score(m), "detail": detail}))
    return out


# ------------------------------------------------------------------ baloncesto
_BB_PERIODS = ("Q1", "Q2", "Q3", "Q4", "OT")


def _basketball(prev: dict, m: Match) -> list[DetectedEvent]:
    out: list[DetectedEvent] = []
    st, pst = m.status, prev["status"]
    detail, pdetail = m.status_detail or "", prev["detail"]
    if pst != MatchStatus.live and st == MatchStatus.live:
        out.append(DetectedEvent("tipoff", "tipoff", {"score": _score(m)}))
    if pdetail in _BB_PERIODS and detail != pdetail and st != MatchStatus.finished:
        out.append(DetectedEvent("period_end", f"period_end:{pdetail}", {"period": pdetail, "score": _score(m)}))
    h0, a0 = prev["home"] or 0, prev["away"] or 0
    h1, a1 = m.home_score or 0, m.away_score or 0
    m0, m1 = h0 - a0, h1 - a1
    if st == MatchStatus.live and detail in ("Q4", "OT") and m0 != 0 and m1 != 0 and (m0 > 0) != (m1 > 0):
        out.append(DetectedEvent("lead_change", f"lead:{detail}:{h1}-{a1}",
                                 {"leader": "home" if m1 > 0 else "away", "score": _score(m), "period": detail}))
    if st == MatchStatus.live:
        stats = dict(m.stats or {})
        run = stats.get("run") or {"min": m0, "max": m0}
        run["min"], run["max"] = min(run["min"], m1), max(run["max"], m1)
        if m1 - run["min"] >= 10 or run["max"] - m1 >= 10:
            side = "home" if m1 - run["min"] >= 10 else "away"
            swing = (m1 - run["min"]) if side == "home" else (run["max"] - m1)
            out.append(DetectedEvent("big_run", f"run:{detail}:{h1}-{a1}",
                                     {"side": side, "swing": swing, "score": _score(m), "period": detail}))
            run = {"min": m1, "max": m1}
        stats["run"] = run
        m.stats = stats
    if st == MatchStatus.finished and pst != MatchStatus.finished:
        out.append(DetectedEvent("full_time", "ft", {"score": _score(m), "detail": detail}))
    return out


# ------------------------------------------------------------------ tenis
def _tennis(prev: dict, m: Match) -> list[DetectedEvent]:
    out: list[DetectedEvent] = []
    st, pst = m.status, prev["status"]
    if pst != MatchStatus.live and st == MatchStatus.live:
        out.append(DetectedEvent("match_start", "start", {}))
    sets_now = (m.periods or {}).get("sets") or []
    p_done = (prev["home"] or 0) + (prev["away"] or 0)
    n_done = (m.home_score or 0) + (m.away_score or 0)
    for n in range(p_done + 1, n_done + 1):
        set_score = next((s for s in sets_now if s.get("set") == n), None)
        out.append(DetectedEvent("set_end", f"set_end:{n}", {"set": n, "set_score": set_score,
                                                              "sets": {"home": m.home_score, "away": m.away_score}}))
    if st == MatchStatus.live and sets_now:
        cur = sets_now[-1]
        prev_sets = (prev["periods"] or {}).get("sets") or []
        pcur = next((s for s in prev_sets if s.get("set") == cur.get("set")), None)
        if pcur is None or (pcur.get("home"), pcur.get("away")) != (cur.get("home"), cur.get("away")):
            games = {"home": cur.get("home"), "away": cur.get("away")}
            out.append(DetectedEvent("game_score", f"game:{cur.get('set')}:{games['home']}-{games['away']}",
                                     {"set": cur.get("set"), "games": games}))
    if st == MatchStatus.finished and pst != MatchStatus.finished:
        out.append(DetectedEvent("full_time", "ft", {"sets": {"home": m.home_score, "away": m.away_score},
                                                     "winner": (m.periods or {}).get("winner")}))
    return out
