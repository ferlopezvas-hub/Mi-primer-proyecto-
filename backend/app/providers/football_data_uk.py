"""Importador de históricos de football-data.co.uk (CSV públicos de descarga directa).

No es scraping: el sitio ofrece los ficheros CSV para su descarga. Uso pensado
para entrenar y hacer backtesting. Antes de un uso comercial, revisar sus
condiciones (ver docs/DATA_PROVIDERS.md).
"""
from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime

import httpx

from app.engines.base import canonical
from app.models import MatchStatus, Sport
from app.providers.base import CompetitionDTO, MatchDTO, TeamDTO

PROVIDER = "football-data-co-uk"
DIVISIONS = {
    "SP1": ("La Liga", "Spain"), "SP2": ("Segunda División", "Spain"),
    "E0": ("Premier League", "England"), "E1": ("Championship", "England"),
    "I1": ("Serie A", "Italy"), "D1": ("Bundesliga", "Germany"), "F1": ("Ligue 1", "France"),
    "N1": ("Eredivisie", "Netherlands"), "P1": ("Primeira Liga", "Portugal"),
}


def _date(d: str, t: str) -> datetime:
    fmt = "%d/%m/%Y" if len(d.split("/")[-1]) == 4 else "%d/%m/%y"
    dt = datetime.strptime(d, fmt)
    if t:
        hh, mm = t.split(":")[:2]
        dt = dt.replace(hour=int(hh), minute=int(mm))
    else:
        dt = dt.replace(hour=15)
    return dt.replace(tzinfo=UTC)  # hora aproximada (el CSV usa hora del Reino Unido)


BOM = "\ufeff"


def _pid(div: str, start: datetime, home: str, away: str) -> str:
    return hashlib.sha256(f"{div}|{start.date()}|{home}|{away}".encode()).hexdigest()[:24]


def parse_fixtures(text: str, season: str, now: datetime | None = None) -> list[MatchDTO]:
    """fixtures.csv: próximos partidos (todas las divisiones). Solo se importan los futuros."""
    now = now or datetime.now(UTC)
    out = []
    for row in csv.DictReader(io.StringIO(text.lstrip(BOM))):
        div = (row.get("Div") or "").strip()
        if div not in DIVISIONS or not row.get("HomeTeam"):
            continue
        name, country = DIVISIONS[div]
        home, away = row["HomeTeam"].strip(), row["AwayTeam"].strip()
        start = _date(row["Date"], row.get("Time") or "")
        if start <= now:
            continue
        out.append(MatchDTO(
            provider_id=_pid(div, start, home, away), sport=Sport.football,
            home=TeamDTO(canonical(home), home, country), away=TeamDTO(canonical(away), away, country),
            start_time=start, status=MatchStatus.scheduled, status_detail="NS",
            competition=CompetitionDTO(div, name, season, country),
        ))
    return out


def parse_csv(text: str, div: str, season: str) -> list[MatchDTO]:
    name, country = DIVISIONS.get(div, (div, ""))
    out = []
    for row in csv.DictReader(io.StringIO(text.lstrip(BOM))):
        if not row.get("HomeTeam") or row.get("FTHG") in (None, ""):
            continue
        home, away = row["HomeTeam"].strip(), row["AwayTeam"].strip()
        start = _date(row["Date"], row.get("Time") or "")
        pid = _pid(div, start, home, away)
        hg, ag = int(row["FTHG"]), int(row["FTAG"])
        periods = {"fulltime": {"home": hg, "away": ag}}
        if row.get("HTHG") not in (None, ""):
            periods["halftime"] = {"home": int(row["HTHG"]), "away": int(row["HTAG"])}
        stats = {}
        for k_csv, k in (("HS", "shots_home"), ("AS", "shots_away"), ("HST", "shots_on_target_home"),
                         ("AST", "shots_on_target_away"), ("HC", "corners_home"), ("AC", "corners_away")):
            if row.get(k_csv) not in (None, ""):
                stats[k] = int(float(row[k_csv]))
        out.append(MatchDTO(
            provider_id=pid, sport=Sport.football,
            home=TeamDTO(canonical(home), home, country), away=TeamDTO(canonical(away), away, country),
            start_time=start, status=MatchStatus.finished, status_detail="FT", home_score=hg, away_score=ag,
            periods=periods, competition=CompetitionDTO(div, name, season, country), stats=stats,
        ))
    return out


def download_fixtures(client: httpx.Client | None = None) -> str:
    c = client or httpx.Client(timeout=30, follow_redirects=True)
    r = c.get("https://www.football-data.co.uk/fixtures.csv")
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")


def download(div: str, season_code: str, client: httpx.Client | None = None) -> str:
    """season_code estilo '2324' para 2023/24."""
    url = f"https://www.football-data.co.uk/mmz4281/{season_code}/{div}.csv"
    c = client or httpx.Client(timeout=30, follow_redirects=True)
    r = c.get(url)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")
