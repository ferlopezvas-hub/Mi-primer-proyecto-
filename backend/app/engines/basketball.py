"""Basketball AI: Elo con margen de victoria + modelo de puntos por equipo.

- Elo con multiplicador por margen de victoria (enfoque publicado por
  FiveThirtyEight para la NBA) y regresión a la media entre temporadas.
- La ventaja de campo se estima a partir de los datos (porcentaje de victorias
  locales del histórico), no se fija a mano.
- Puntos esperados: media ponderada exponencialmente de puntos anotados y
  recibidos de cada equipo, ajustada por la media de la liga.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from app.engines.base import (
    Engine,
    HistMatch,
    InsufficientData,
    PredictionOutput,
    confidence_label,
    confidence_score,
    split_factors,
)
from app.engines.stats import days_between, h2h, streak, summary

BASE = 1500.0


class BasketballEngine(Engine):
    name = "basketball-ai"
    version = "elo-mov-1.0"
    sport = "basketball"

    def __init__(self, k: float = 20.0, season_gap_days: int = 60, season_regression: float = 0.25,
                 window_days: int = 1100, min_matches: int = 5, half_life_games: float = 10.0):
        self.k = k
        self.season_gap_days = season_gap_days
        self.season_regression = season_regression
        self.window_days = window_days
        self.min_matches = min_matches
        self.alpha = 1 - 0.5 ** (1 / half_life_games)
        self.fitted = False

    def fit(self, history: list[HistMatch], as_of: datetime) -> None:
        start = as_of - timedelta(days=self.window_days)
        hist = sorted([m for m in history if start <= m.date < as_of], key=lambda m: m.date)
        self.history, self.as_of = hist, as_of
        if len(hist) < 30:
            self.fitted = False
            return
        home_wins = sum(1 for m in hist if m.home_score > m.away_score)
        p = min(0.75, max(0.5, home_wins / len(hist)))
        self.hca = 400 * math.log10(p / (1 - p))
        self.home_win_rate = home_wins / len(hist)
        elo: dict[str, float] = {}
        off: dict[str, float] = {}
        deff: dict[str, float] = {}
        last_seen: dict[str, datetime] = {}
        pts = [m.home_score for m in hist] + [m.away_score for m in hist]
        self.league_avg = sum(pts) / len(pts)
        margins_resid = []
        for m in hist:
            for t in (m.home, m.away):
                if t in last_seen and (m.date - last_seen[t]).days > self.season_gap_days:
                    elo[t] = elo[t] * (1 - self.season_regression) + BASE * self.season_regression
                last_seen[t] = m.date
            eh, ea = elo.get(m.home, BASE), elo.get(m.away, BASE)
            diff = eh + (0 if m.neutral else self.hca) - ea
            p_home = 1 / (1 + 10 ** (-diff / 400))
            margin = m.home_score - m.away_score
            margins_resid.append(margin - diff / 28)  # ~28 puntos Elo por punto de margen
            winner_diff = diff if margin > 0 else -diff
            mult = ((abs(margin) + 3) ** 0.8) / (7.5 + 0.006 * winner_diff)
            delta = self.k * mult * ((1 if margin > 0 else 0) - p_home)
            elo[m.home], elo[m.away] = eh + delta, ea - delta
            for t, scored, conceded in ((m.home, m.home_score, m.away_score), (m.away, m.away_score, m.home_score)):
                off[t] = off.get(t, self.league_avg) * (1 - self.alpha) + scored * self.alpha
                deff[t] = deff.get(t, self.league_avg) * (1 - self.alpha) + conceded * self.alpha
        self.elo, self.off, self.deff = elo, off, deff
        mean = sum(margins_resid) / len(margins_resid)
        self.margin_sigma = math.sqrt(sum((r - mean) ** 2 for r in margins_resid) / len(margins_resid))
        self.n_matches = len(hist)
        self.fitted = True

    def predict(self, home: str, away: str, kickoff: datetime, surface: str = "") -> list[PredictionOutput]:
        if not self.fitted:
            raise InsufficientData("Histórico insuficiente (mínimo 30 partidos)")
        sh, sa = summary(self.history, home, venue="home"), summary(self.history, away, venue="away")
        if sh["matches"] < self.min_matches or sa["matches"] < self.min_matches:
            raise InsufficientData(f"Datos insuficientes: local {sh['matches']} y visitante {sa['matches']} partidos")
        eh, ea = self.elo.get(home, BASE), self.elo.get(away, BASE)
        diff = eh + self.hca - ea
        p_home = 1 / (1 + 10 ** (-diff / 400))
        exp_home = (self.off.get(home, self.league_avg) + self.deff.get(away, self.league_avg)) / 2
        exp_away = (self.off.get(away, self.league_avg) + self.deff.get(home, self.league_avg)) / 2
        probs = {"home": round(p_home, 4), "away": round(1 - p_home, 4)}
        pick = max(probs, key=probs.get)
        last_dates = [d for d in (sh["last_date"], sa["last_date"]) if d is not None]
        days_since = days_between(min(last_dates), kickoff) if last_dates else None
        conf = confidence_score(min(sh["matches"], sa["matches"]), 25, days_since, list(probs.values()))
        signals = [
            {"text": f"Rating Elo: local {eh:.0f} vs visitante {ea:.0f}", "value": (eh - ea) / 100},
            {"text": f"Ventaja de campo estimada: +{self.hca:.0f} puntos Elo "
                     f"(los locales ganan el {self.home_win_rate * 100:.0f} % en este histórico)",
             "value": self.hca / 100},
            {"text": f"Puntos esperados: local {exp_home:.1f} vs visitante {exp_away:.1f}",
             "value": (exp_home - exp_away) / 10},
            {"text": f"Forma (últimos 5): local {sh['form'].count('W')}V vs visitante {sa['form'].count('W')}V",
             "value": (sh["form"].count("W") - sa["form"].count("W")) / 5},
        ]
        pro, con = split_factors([{**s, "value": round(s["value"], 3)} for s in signals], 1 if pick == "home" else -1)
        trends = []
        for label, s in (("Local", sh), ("Visitante", sa)):
            r, n = streak(s["form"])
            if n >= 3:
                trends.append(f"{label}: racha de {n} {'victorias' if r == 'W' else 'derrotas'}")
        warnings = []
        if min(sh["matches"], sa["matches"]) < 15:
            warnings.append("Muestra reducida para al menos un equipo")
        if days_since is not None and days_since > 90:
            warnings.append(f"El último dato tiene {days_since:.0f} días (posible inicio de temporada)")
        quality = {
            "matches_home_team": sh["matches"], "matches_away_team": sa["matches"],
            "matches_in_model": self.n_matches, "data_until": self.as_of.isoformat(),
            "days_since_last_match": round(days_since, 1) if days_since is not None else None,
            "level": "alta" if not warnings else "media" if len(warnings) == 1 else "baja", "warnings": warnings,
        }
        stats_used = {
            "elo": {"home": round(eh), "away": round(ea)},
            "home_court_elo": round(self.hca, 1),
            "expected_points": {"home": round(exp_home, 1), "away": round(exp_away, 1),
                                "total": round(exp_home + exp_away, 1)},
            "expected_margin": round(diff / 28, 1),
            "margin_std_dev": round(self.margin_sigma, 1),
            "form_last5": {"home": sh["form"], "away": sa["form"]},
            "avg_points_last10": {"home": {"for": sh["avg_for"], "against": sh["avg_against"]},
                                  "away": {"for": sa["avg_for"], "against": sa["avg_against"]}},
            "head_to_head": h2h(self.history, home, away),
        }
        label = "Victoria local" if pick == "home" else "Victoria visitante"
        return [PredictionOutput("moneyline", probs, pick, conf, {
            "summary": f"{label} ({probs[pick] * 100:.0f} %). Margen esperado {abs(diff / 28):.1f} puntos",
            "factors_for": pro, "factors_against": con, "trends": trends, "stats_used": stats_used,
            "confidence_label": confidence_label(conf),
        }, quality)]
