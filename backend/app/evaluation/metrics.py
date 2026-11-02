"""Métricas de evaluación de predicciones probabilísticas."""
from __future__ import annotations

import math
from collections.abc import Iterable

EPS = 1e-15


def brier(probs: dict[str, float], actual: str) -> float:
    """Brier multiclase: suma de (p_k - o_k)^2. Rango 0 (perfecto) a 2."""
    return float(sum((p - (1.0 if k == actual else 0.0)) ** 2 for k, p in probs.items()))


def log_loss(probs: dict[str, float], actual: str) -> float:
    p = min(1 - EPS, max(EPS, probs.get(actual, 0.0)))
    return float(-math.log(p))


def calibration(pairs: Iterable[tuple[float, bool]], bins: int = 10) -> dict:
    """pairs = (probabilidad asignada a un resultado, ¿ocurrió?).

    Se usan TODAS las clases de cada predicción (estilo 'reliability diagram').
    Devuelve cubetas y el Expected Calibration Error (ECE).
    """
    buckets = [{"lo": i / bins, "hi": (i + 1) / bins, "n": 0, "sum_p": 0.0, "hits": 0} for i in range(bins)]
    total = 0
    for p, hit in pairs:
        i = min(bins - 1, int(p * bins))
        b = buckets[i]
        b["n"] += 1
        b["sum_p"] += p
        b["hits"] += int(hit)
        total += 1
    out, ece = [], 0.0
    for b in buckets:
        if b["n"]:
            mean_p, freq = b["sum_p"] / b["n"], b["hits"] / b["n"]
            ece += b["n"] / total * abs(mean_p - freq)
            out.append({"range": [round(b["lo"], 2), round(b["hi"], 2)], "n": b["n"],
                        "mean_predicted": round(mean_p, 4), "observed_frequency": round(freq, 4)})
    return {"bins": out, "ece": round(ece, 4) if total else None, "n_points": total}


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Intervalo de confianza del 95 % para un porcentaje de aciertos."""
    if n == 0:
        return None
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(centre - half, 4), round(centre + half, 4)


def baseline_brier_uniform(k: int) -> float:
    """Brier de una predicción que reparte 1/k a cada clase (referencia mínima)."""
    return (1 - 1 / k) ** 2 + (k - 1) * (1 / k) ** 2
