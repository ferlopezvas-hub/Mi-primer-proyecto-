"""Interfaz común de los motores de análisis."""
from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

_STOP = {"fc", "cf", "afc", "sc", "ac", "cd", "ud", "sd", "rc", "rcd", "club", "de", "the", "bc", "bk", "kk"}
_ALIASES = {
    # football-data.co.uk -> nombre estándar (ampliable)
    "ath madrid": "atletico madrid", "atl madrid": "atletico madrid", "ath bilbao": "athletic", "athletic bilbao":
    "athletic", "sociedad": "real sociedad", "betis": "real betis", "vallecano": "rayo vallecano",
    "espanol": "espanyol", "celta": "celta vigo", "man united": "manchester united", "man utd": "manchester united",
    "man city": "manchester city", "nott m forest": "nottingham forest", "nottm forest": "nottingham forest",
    "spurs": "tottenham", "tottenham hotspur": "tottenham", "wolves": "wolverhampton", "wolverhampton wanderers":
    "wolverhampton", "newcastle united": "newcastle", "west ham united": "west ham", "brighton hove albion":
    "brighton", "sheffield united": "sheffield utd", "sheffield united fc": "sheffield utd",
    "leicester city": "leicester", "leeds united": "leeds", "ipswich town": "ipswich", "luton town": "luton",
    # API-Football -> football-data.co.uk (para unir históricos de ambas fuentes)
    "bayern munchen": "bayern munich", "paris saint germain": "paris sg", "borussia dortmund": "dortmund",
    "borussia monchengladbach": "m gladbach", "eintracht frankfurt": "ein frankfurt", "olympique marseille":
    "marseille", "olympique lyonnais": "lyon", "as roma": "roma", "ss lazio": "lazio", "ssc napoli": "napoli",
    "deportivo alaves": "alaves", "athletic bilbao club": "athletic", "atletico de madrid": "atletico madrid",
    "rb leipzig": "rb leipzig", "1899 hoffenheim": "hoffenheim", "vfb stuttgart": "stuttgart",
    "bayer leverkusen": "leverkusen", "vfl wolfsburg": "wolfsburg", "1 koln": "koln", "1 fc koln": "koln",
    "fc koln": "koln", "stade rennais": "rennes", "as monaco": "monaco", "stade brestois 29": "brest",
    "hellas verona": "verona", "racing santander": "santander", "real racing club": "santander",
}


def canonical(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = " ".join(w for w in s.split() if w not in _STOP)
    return _ALIASES.get(s, s)


@dataclass
class HistMatch:
    date: datetime
    home: str
    away: str
    home_score: int
    away_score: int
    surface: str = ""
    neutral: bool = False


@dataclass
class PredictionOutput:
    market: str
    probabilities: dict[str, float]
    predicted_outcome: str
    confidence: float
    explanation: dict = field(default_factory=dict)
    data_quality: dict = field(default_factory=dict)


class InsufficientData(Exception):
    """No hay datos suficientes para una predicción honesta."""


def confidence_score(n_min: int, n_target: int, days_since_last: float | None, probs: list[float]) -> float:
    """Confianza heurística 0-1 (NO es una probabilidad de acierto).

    Combina: claridad de la predicción, es decir, distancia al reparto uniforme
    (60 %), suficiencia de datos (25 %) y actualidad de los datos (15 %).
    Los pesos se eligieron para que la confianza separe mejor los aciertos en el
    backtest histórico (ver docs/MODELS.md); se revisan con cada versión.
    """
    sufficiency = min(1.0, n_min / n_target)
    if days_since_last is None:
        recency = 0.0
    else:
        recency = max(0.0, 1.0 - max(0.0, days_since_last - 14) / 180)
    k = len(probs)
    decisiveness = min(1.0, (max(probs) - 1 / k) / (1 - 1 / k) / 0.6)
    return round(0.6 * decisiveness + 0.25 * sufficiency + 0.15 * recency, 3)


def confidence_label(c: float) -> str:
    return "alta" if c >= 0.7 else "media" if c >= 0.45 else "baja"


def split_factors(signals: list[dict], favoured_sign: int) -> tuple[list[dict], list[dict]]:
    """signals: [{'text', 'value' (>0 favorece al local)}]. Devuelve (a favor, en contra)."""
    pro = [s for s in signals if s["value"] * favoured_sign > 0]
    con = [s for s in signals if s["value"] * favoured_sign < 0]
    pro.sort(key=lambda s: -abs(s["value"]))
    con.sort(key=lambda s: -abs(s["value"]))
    return pro[:5], con[:5]


class Engine(ABC):
    name: str
    version: str
    sport: str

    @abstractmethod
    def fit(self, history: list[HistMatch], as_of: datetime) -> None: ...

    @abstractmethod
    def predict(self, home: str, away: str, kickoff: datetime, surface: str = "") -> list[PredictionOutput]: ...
