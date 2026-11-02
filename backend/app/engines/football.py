"""Football AI: modelo Dixon-Coles (Poisson bivariado corregido) con decaimiento temporal.

Referencias:
- Dixon, M. & Coles, S. (1997). Modelling Association Football Scores and
  Inefficiencies in the Football Betting Market. JRSS C 46(2).
- Maher, M. (1982). Modelling association football scores. Statistica Neerlandica.

Cada equipo tiene un parámetro de ataque y otro de defensa; se estiman por
máxima verosimilitud ponderando más los partidos recientes (xi) y con
regularización L2 para equipos con pocos datos. A partir de los goles
esperados se obtiene la matriz de marcadores y de ella los mercados
1X2, más/menos de 2,5 goles y ambos marcan.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

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

MAX_GOALS = 10


class FootballEngine(Engine):
    name = "football-ai"
    version = "dixon-coles-1.0"
    sport = "football"

    def __init__(self, xi: float = 0.0019, reg: float = 1.0, window_days: int = 730, min_matches: int = 5):
        self.xi = xi
        self.reg = reg
        self.window_days = window_days
        self.min_matches = min_matches
        self.fitted = False

    # ------------------------------------------------------------------ ajuste
    def fit(self, history: list[HistMatch], as_of: datetime) -> None:
        start = as_of - timedelta(days=self.window_days)
        hist = [m for m in history if start <= m.date < as_of]
        self.history = hist
        self.as_of = as_of
        teams = sorted({m.home for m in hist} | {m.away for m in hist})
        self.idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        if len(hist) < 20 or n < 4:
            self.fitted = False
            return
        hi = np.array([self.idx[m.home] for m in hist])
        ai = np.array([self.idx[m.away] for m in hist])
        yh = np.array([m.home_score for m in hist], dtype=float)
        ya = np.array([m.away_score for m in hist], dtype=float)
        days = np.array([(as_of - m.date).total_seconds() / 86400 for m in hist])
        w = np.exp(-self.xi * days)
        reg = self.reg

        def nll(theta):
            mu, h = theta[0], theta[1]
            a, d = theta[2:2 + n], theta[2 + n:]
            lh = mu + h + a[hi] - d[ai]
            la = mu + a[ai] - d[hi]
            eh, ea = np.exp(lh), np.exp(la)
            f = np.sum(w * (eh - yh * lh + ea - ya * la)) + 0.5 * reg * (a @ a + d @ d)
            gh, ga = w * (eh - yh), w * (ea - ya)
            g = np.zeros_like(theta)
            g[0] = gh.sum() + ga.sum()
            g[1] = gh.sum()
            ga_ = np.zeros(n)
            gd_ = np.zeros(n)
            np.add.at(ga_, hi, gh)
            np.add.at(gd_, ai, -gh)
            np.add.at(ga_, ai, ga)
            np.add.at(gd_, hi, -ga)
            g[2:2 + n] = ga_ + reg * a
            g[2 + n:] = gd_ + reg * d
            return f, g

        theta0 = np.zeros(2 + 2 * n)
        theta0[0] = math.log(max(0.1, (yh.mean() + ya.mean()) / 2))
        res = minimize(nll, theta0, jac=True, method="L-BFGS-B")
        th = res.x
        self.mu, self.home_adv = float(th[0]), float(th[1])
        self.attack, self.defence = th[2:2 + n], th[2 + n:]
        # rho de Dixon-Coles por búsqueda en rejilla
        lh = np.exp(self.mu + self.home_adv + self.attack[hi] - self.defence[ai])
        la = np.exp(self.mu + self.attack[ai] - self.defence[hi])
        best, best_ll = 0.0, -np.inf
        for rho in np.linspace(-0.2, 0.2, 41):
            tau = np.ones_like(lh)
            m00 = (yh == 0) & (ya == 0)
            m01 = (yh == 0) & (ya == 1)
            m10 = (yh == 1) & (ya == 0)
            m11 = (yh == 1) & (ya == 1)
            tau[m00] = 1 - lh[m00] * la[m00] * rho
            tau[m01] = 1 + lh[m01] * rho
            tau[m10] = 1 + la[m10] * rho
            tau[m11] = 1 - rho
            if np.any(tau <= 0):
                continue
            ll = float(np.sum(w * np.log(tau)))
            if ll > best_ll:
                best, best_ll = float(rho), ll
        self.rho = best
        self.n_matches = len(hist)
        self.fitted = True

    # ------------------------------------------------------------------ predicción
    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        ih, ia = self.idx.get(home), self.idx.get(away)
        ah = self.attack[ih] if ih is not None else 0.0
        dh = self.defence[ih] if ih is not None else 0.0
        aa = self.attack[ia] if ia is not None else 0.0
        da = self.defence[ia] if ia is not None else 0.0
        return math.exp(self.mu + self.home_adv + ah - da), math.exp(self.mu + aa - dh)

    def score_matrix(self, lh: float, la: float) -> np.ndarray:
        g = np.arange(MAX_GOALS + 1)
        mat = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
        r = self.rho
        mat[0, 0] *= 1 - lh * la * r
        mat[0, 1] *= 1 + lh * r
        mat[1, 0] *= 1 + la * r
        mat[1, 1] *= 1 - r
        return mat / mat.sum()

    def predict(self, home: str, away: str, kickoff: datetime, surface: str = "") -> list[PredictionOutput]:
        if not self.fitted:
            raise InsufficientData("Histórico de la competición insuficiente (mínimo 20 partidos)")
        sh, sa = summary(self.history, home, venue="home"), summary(self.history, away, venue="away")
        if sh["matches"] < self.min_matches or sa["matches"] < self.min_matches:
            raise InsufficientData(
                f"Datos insuficientes: local {sh['matches']} y visitante {sa['matches']} partidos "
                f"(mínimo {self.min_matches})")
        lh, la = self.expected_goals(home, away)
        mat = self.score_matrix(lh, la)
        p_home = float(np.tril(mat, -1).sum())
        p_draw = float(np.trace(mat))
        p_away = float(np.triu(mat, 1).sum())
        totals = np.add.outer(np.arange(MAX_GOALS + 1), np.arange(MAX_GOALS + 1))
        p_over = float(mat[totals > 2.5].sum())
        p_btts = float(mat[1:, 1:].sum())
        top_scores = sorted(((float(mat[i, j]), f"{i}-{j}") for i in range(6) for j in range(6)), reverse=True)[:3]

        last_dates = [d for d in (sh["last_date"], sa["last_date"]) if d is not None]
        days_since = days_between(min(last_dates), kickoff) if last_dates else None
        quality = self._quality(sh, sa, days_since, kickoff)
        ih, ia = self.idx.get(home), self.idx.get(away)
        att_h = math.exp(self.attack[ih]) if ih is not None else 1.0
        def_h = math.exp(-self.defence[ih]) if ih is not None else 1.0
        att_a = math.exp(self.attack[ia]) if ia is not None else 1.0
        def_a = math.exp(-self.defence[ia]) if ia is not None else 1.0
        stats_used = {
            "expected_goals": {"home": round(lh, 2), "away": round(la, 2)},
            "attack_index": {"home": round(att_h, 2), "away": round(att_a, 2)},
            "goals_conceded_index": {"home": round(def_h, 2), "away": round(def_a, 2)},
            "home_advantage_goals_factor": round(math.exp(self.home_adv), 3),
            "form_last5": {"home": sh["form"], "away": sa["form"]},
            "avg_goals_last10": {"home": {"for": sh["avg_for"], "against": sh["avg_against"]},
                                 "away": {"for": sa["avg_for"], "against": sa["avg_against"]}},
            "home_win_rate_at_home": sh["venue_win_rate"],
            "away_win_rate_away": sa["venue_win_rate"],
            "head_to_head": h2h(self.history, home, away),
            "most_likely_scores": [{"score": s, "p": round(p, 3)} for p, s in top_scores],
            "matches_in_model": self.n_matches,
        }
        signals = self._signals(sh, sa, lh, la, att_h, att_a, def_h, def_a, stats_used["head_to_head"])
        trends = self._trends(sh, sa)
        out = []

        probs = {"home": round(p_home, 4), "draw": round(p_draw, 4), "away": round(p_away, 4)}
        pick = max(probs, key=probs.get)
        sign = {"home": 1, "away": -1, "draw": 0}[pick]
        if sign:
            pro, con = split_factors(signals, sign)
        else:
            ordered = sorted(signals, key=lambda s: abs(s["value"]))
            pro, con = ordered[:3], ordered[::-1][:3]
        conf = confidence_score(min(sh["matches"], sa["matches"]), 30, days_since, list(probs.values()))
        out.append(PredictionOutput("1x2", probs, pick, conf, {
            "summary": self._summary_1x2(pick, probs), "factors_for": pro, "factors_against": con,
            "trends": trends, "stats_used": stats_used, "confidence_label": confidence_label(conf),
        }, quality))

        probs_ou = {"over": round(p_over, 4), "under": round(1 - p_over, 4)}
        pick_ou = max(probs_ou, key=probs_ou.get)
        conf_ou = confidence_score(min(sh["matches"], sa["matches"]), 30, days_since, list(probs_ou.values()))
        xg_total = lh + la
        ou_signals = [
            {"text": f"Goles esperados en el partido: {xg_total:.2f}", "value": xg_total - 2.5},
            {"text": f"Media de goles en partidos recientes del local: "
                     f"{(sh['avg_for'] or 0) + (sh['avg_against'] or 0):.2f}",
             "value": (sh["avg_for"] or 0) + (sh["avg_against"] or 0) - 2.5},
            {"text": f"Media de goles en partidos recientes del visitante: "
                     f"{(sa['avg_for'] or 0) + (sa['avg_against'] or 0):.2f}",
             "value": (sa["avg_for"] or 0) + (sa["avg_against"] or 0) - 2.5},
        ]
        pro_ou, con_ou = split_factors(ou_signals, 1 if pick_ou == "over" else -1)
        out.append(PredictionOutput("over_under_2.5", probs_ou, pick_ou, conf_ou, {
            "summary": f"{'Más' if pick_ou == 'over' else 'Menos'} de 2,5 goles "
                       f"({probs_ou[pick_ou] * 100:.0f} %). Goles esperados: {xg_total:.2f}",
            "factors_for": pro_ou, "factors_against": con_ou, "trends": trends,
            "stats_used": {k: stats_used[k] for k in ("expected_goals", "avg_goals_last10", "most_likely_scores")},
            "confidence_label": confidence_label(conf_ou),
        }, quality))

        probs_b = {"yes": round(p_btts, 4), "no": round(1 - p_btts, 4)}
        pick_b = max(probs_b, key=probs_b.get)
        conf_b = confidence_score(min(sh["matches"], sa["matches"]), 30, days_since, list(probs_b.values()))
        p_h_scores, p_a_scores = 1 - math.exp(-lh), 1 - math.exp(-la)
        b_signals = [
            {"text": f"Probabilidad de que marque el local: {p_h_scores * 100:.0f} %", "value": p_h_scores - 0.6},
            {"text": f"Probabilidad de que marque el visitante: {p_a_scores * 100:.0f} %", "value": p_a_scores - 0.6},
        ]
        pro_b, con_b = split_factors(b_signals, 1 if pick_b == "yes" else -1)
        out.append(PredictionOutput("btts", probs_b, pick_b, conf_b, {
            "summary": f"Ambos marcan: {'sí' if pick_b == 'yes' else 'no'} ({probs_b[pick_b] * 100:.0f} %)",
            "factors_for": pro_b, "factors_against": con_b, "trends": trends,
            "stats_used": {k: stats_used[k] for k in ("expected_goals", "avg_goals_last10")},
            "confidence_label": confidence_label(conf_b),
        }, quality))
        return out

    # ------------------------------------------------------------------ explicaciones
    @staticmethod
    def _summary_1x2(pick: str, probs: dict) -> str:
        label = {"home": "Victoria local", "draw": "Empate", "away": "Victoria visitante"}[pick]
        return f"{label} como resultado más probable ({probs[pick] * 100:.0f} %)"

    @staticmethod
    def _signals(sh, sa, lh, la, att_h, att_a, def_h, def_a, h2h_list) -> list[dict]:
        sig = [
            {"text": f"Goles esperados: local {lh:.2f} vs visitante {la:.2f}", "value": lh - la},
            {"text": f"Índice de ataque: local {att_h:.2f} vs visitante {att_a:.2f} (1 = media)",
             "value": (att_h - att_a) / 2},
            {"text": f"Goles encajados (índice): local {def_h:.2f} vs visitante {def_a:.2f} (menos es mejor)",
             "value": (def_a - def_h) / 2},
            {"text": f"Forma (últimos 5): local {sh['form_points']} pts vs visitante {sa['form_points']} pts",
             "value": (sh["form_points"] - sa["form_points"]) / 15},
        ]
        if sh["venue_win_rate"] is not None and sa["venue_win_rate"] is not None:
            sig.append({"text": f"Victorias del local en casa {sh['venue_win_rate'] * 100:.0f} % vs del "
                                f"visitante fuera {sa['venue_win_rate'] * 100:.0f} %",
                        "value": sh["venue_win_rate"] - sa["venue_win_rate"]})
        if h2h_list:
            a = sum(1 for x in h2h_list if x["winner"] == "team_a")
            b = sum(1 for x in h2h_list if x["winner"] == "team_b")
            if a != b:
                sig.append({"text": f"Enfrentamientos directos recientes: {a} victorias local, {b} visitante",
                            "value": (a - b) / max(1, len(h2h_list)) / 2})
        return [{**s, "value": round(float(s["value"]), 3)} for s in sig]

    @staticmethod
    def _trends(sh, sa) -> list[str]:
        out = []
        for label, s in (("Local", sh), ("Visitante", sa)):
            r, n = streak(s["form"])
            if n >= 3:
                word = {"W": "victorias", "D": "empates", "L": "derrotas"}[r]
                out.append(f"{label}: {n} {word} consecutivas")
            elif s["form"]:
                out.append(f"{label}: forma reciente {'-'.join(s['form'])}")
        return out

    def _quality(self, sh, sa, days_since, kickoff) -> dict:
        warnings = []
        if min(sh["matches"], sa["matches"]) < 15:
            warnings.append("Muestra reducida para al menos un equipo")
        if days_since is not None and days_since > 60:
            warnings.append(f"El último dato tiene {days_since:.0f} días")
        return {
            "matches_home_team": sh["matches"],
            "matches_away_team": sa["matches"],
            "matches_in_model": self.n_matches,
            "data_until": self.as_of.isoformat(),
            "days_since_last_match": round(days_since, 1) if days_since is not None else None,
            "window_days": self.window_days,
            "time_decay_xi": self.xi,
            "level": "alta" if not warnings else "media" if len(warnings) == 1 else "baja",
            "warnings": warnings,
        }
