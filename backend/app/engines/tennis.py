"""Tennis AI: Elo global + Elo por superficie.

- K dinámico K = 250 / (n + 5)^0.4 (n = partidos previos del jugador),
  formulación popularizada por FiveThirtyEight para el tenis.
- La probabilidad combina a partes iguales el Elo global y el de la superficie
  del partido (si la superficie es conocida).
"""
from __future__ import annotations

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
from app.engines.stats import days_between, h2h, summary

BASE = 1500.0


def _p(diff: float) -> float:
    return 1 / (1 + 10 ** (-diff / 400))


class TennisEngine(Engine):
    name = "tennis-ai"
    version = "elo-surface-1.0"
    sport = "tennis"

    def __init__(self, window_days: int = 1100, min_matches: int = 5, surface_weight: float = 0.5):
        self.window_days = window_days
        self.min_matches = min_matches
        self.surface_weight = surface_weight
        self.fitted = False

    def fit(self, history: list[HistMatch], as_of: datetime) -> None:
        start = as_of - timedelta(days=self.window_days)
        hist = sorted([m for m in history if start <= m.date < as_of and m.home_score != m.away_score],
                      key=lambda m: m.date)
        self.history, self.as_of = hist, as_of
        if len(hist) < 30:
            self.fitted = False
            return
        elo: dict[str, float] = {}
        n: dict[str, int] = {}
        selo: dict[tuple[str, str], float] = {}
        sn: dict[tuple[str, str], int] = {}
        for m in hist:
            win, lose = (m.home, m.away) if m.home_score > m.away_score else (m.away, m.home)
            ew, el = elo.get(win, BASE), elo.get(lose, BASE)
            p = _p(ew - el)
            kw, kl = 250 / (n.get(win, 0) + 5) ** 0.4, 250 / (n.get(lose, 0) + 5) ** 0.4
            elo[win], elo[lose] = ew + kw * (1 - p), el - kl * (1 - p)
            n[win], n[lose] = n.get(win, 0) + 1, n.get(lose, 0) + 1
            if m.surface:
                sw, sl = (win, m.surface), (lose, m.surface)
                esw, esl = selo.get(sw, BASE), selo.get(sl, BASE)
                ps = _p(esw - esl)
                kws, kls = 250 / (sn.get(sw, 0) + 5) ** 0.4, 250 / (sn.get(sl, 0) + 5) ** 0.4
                selo[sw], selo[sl] = esw + kws * (1 - ps), esl - kls * (1 - ps)
                sn[sw], sn[sl] = sn.get(sw, 0) + 1, sn.get(sl, 0) + 1
        self.elo, self.n, self.selo, self.sn = elo, n, selo, sn
        self.n_matches = len(hist)
        self.fitted = True

    def predict(self, home: str, away: str, kickoff: datetime, surface: str = "") -> list[PredictionOutput]:
        if not self.fitted:
            raise InsufficientData("Histórico insuficiente (mínimo 30 partidos)")
        sa_, sb_ = summary(self.history, home), summary(self.history, away)
        if sa_["matches"] < self.min_matches or sb_["matches"] < self.min_matches:
            raise InsufficientData(f"Datos insuficientes: {sa_['matches']} y {sb_['matches']} partidos")
        ea, eb = self.elo.get(home, BASE), self.elo.get(away, BASE)
        p_overall = _p(ea - eb)
        surface = (surface or "").lower()
        if surface:
            sa, sb = self.selo.get((home, surface), BASE), self.selo.get((away, surface), BASE)
            p_surface = _p(sa - sb)
            p = (1 - self.surface_weight) * p_overall + self.surface_weight * p_surface
        else:
            sa = sb = None
            p_surface = None
            p = p_overall
        probs = {"home": round(p, 4), "away": round(1 - p, 4)}
        pick = max(probs, key=probs.get)
        last = [d for d in (sa_["last_date"], sb_["last_date"]) if d]
        days_since = days_between(min(last), kickoff) if last else None
        conf = confidence_score(min(sa_["matches"], sb_["matches"]), 30, days_since, list(probs.values()))
        signals = [{"text": f"Elo global: {ea:.0f} vs {eb:.0f}", "value": (ea - eb) / 100}]
        if sa is not None:
            n_a, n_b = self.sn.get((home, surface), 0), self.sn.get((away, surface), 0)
            signals.append({"text": f"Elo en {surface}: {sa:.0f} ({n_a} partidos) vs {sb:.0f} ({n_b} partidos)",
                            "value": (sa - sb) / 100})
        signals.append({"text": f"Forma (últimos 5): {sa_['form'].count('W')}V vs {sb_['form'].count('W')}V",
                        "value": (sa_["form"].count("W") - sb_["form"].count("W")) / 5})
        hh = h2h(self.history, home, away)
        if hh:
            a = sum(1 for x in hh if x["winner"] == "team_a")
            if a * 2 != len(hh):
                signals.append({"text": f"Cara a cara reciente: {a}-{len(hh) - a}", "value": (2 * a - len(hh)) / 10})
        pro, con = split_factors([{**s, "value": round(s["value"], 3)} for s in signals], 1 if pick == "home" else -1)
        warnings = []
        if not surface:
            warnings.append("Superficie desconocida: solo se usa el Elo global")
        if min(sa_["matches"], sb_["matches"]) < 15:
            warnings.append("Muestra reducida para al menos un jugador")
        if days_since is not None and days_since > 60:
            warnings.append(f"El último partido registrado tiene {days_since:.0f} días")
        quality = {
            "matches_player_1": sa_["matches"], "matches_player_2": sb_["matches"],
            "matches_in_model": self.n_matches, "data_until": self.as_of.isoformat(),
            "days_since_last_match": round(days_since, 1) if days_since is not None else None,
            "level": "alta" if not warnings else "media" if len(warnings) == 1 else "baja", "warnings": warnings,
        }
        return [PredictionOutput("match_winner", probs, pick, conf, {
            "summary": f"Gana {'el jugador 1' if pick == 'home' else 'el jugador 2'} ({probs[pick] * 100:.0f} %)",
            "factors_for": pro, "factors_against": con,
            "trends": [f"Forma: {'-'.join(sa_['form'])} vs {'-'.join(sb_['form'])}"],
            "stats_used": {"elo": {"home": round(ea), "away": round(eb)},
                           "surface_elo": None if sa is None else {"home": round(sa), "away": round(sb)},
                           "p_overall": round(p_overall, 4),
                           "p_surface": None if p_surface is None else round(p_surface, 4),
                           "form_last5": {"home": sa_["form"], "away": sb_["form"]}, "head_to_head": hh},
            "confidence_label": confidence_label(conf),
        }, quality)]
