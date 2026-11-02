"""Estadísticas descriptivas compartidas por los motores."""
from __future__ import annotations

from datetime import datetime

from app.engines.base import HistMatch


def team_matches(history: list[HistMatch], key: str) -> list[HistMatch]:
    return [m for m in history if m.home == key or m.away == key]


def result_for(m: HistMatch, key: str) -> str:
    mine, theirs = (m.home_score, m.away_score) if m.home == key else (m.away_score, m.home_score)
    return "W" if mine > theirs else "L" if mine < theirs else "D"


def summary(history: list[HistMatch], key: str, last_n: int = 10, form_n: int = 5,
            venue: str | None = None) -> dict:
    ms = sorted(team_matches(history, key), key=lambda m: m.date)
    if venue == "home":
        ms_v = [m for m in ms if m.home == key]
    elif venue == "away":
        ms_v = [m for m in ms if m.away == key]
    else:
        ms_v = ms
    recent = ms[-last_n:]
    gf = [m.home_score if m.home == key else m.away_score for m in recent]
    ga = [m.away_score if m.home == key else m.home_score for m in recent]
    form = [result_for(m, key) for m in ms[-form_n:]]
    vrec = ms_v[-last_n:]
    vres = [result_for(m, key) for m in vrec]
    return {
        "matches": len(ms),
        "last_date": ms[-1].date if ms else None,
        "form": form,
        "form_points": sum(3 if r == "W" else 1 if r == "D" else 0 for r in form),
        "avg_for": round(sum(gf) / len(gf), 2) if gf else None,
        "avg_against": round(sum(ga) / len(ga), 2) if ga else None,
        "venue_matches": len(vrec),
        "venue_win_rate": round(vres.count("W") / len(vres), 3) if vres else None,
    }


def streak(form: list[str]) -> tuple[str, int]:
    if not form:
        return "", 0
    last = form[-1]
    n = 0
    for r in reversed(form):
        if r != last:
            break
        n += 1
    return last, n


def h2h(history: list[HistMatch], a: str, b: str, n: int = 5) -> list[dict]:
    """Últimos enfrentamientos. 'winner' es relativo al partido a predecir:
    team_a = el local del partido a predecir, team_b = el visitante."""
    ms = sorted([m for m in history if {m.home, m.away} == {a, b}], key=lambda m: m.date)[-n:]
    out = []
    for m in ms:
        if m.home_score == m.away_score:
            w = "draw"
        else:
            w = "team_a" if (m.home == a) == (m.home_score > m.away_score) else "team_b"
        out.append({"date": m.date.date().isoformat(), "home": m.home, "away": m.away,
                    "score": f"{m.home_score}-{m.away_score}", "winner": w})
    return out


def days_between(a: datetime | None, b: datetime) -> float | None:
    if a is None:
        return None
    return (b - a).total_seconds() / 86400
