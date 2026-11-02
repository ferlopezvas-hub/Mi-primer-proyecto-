"""Textos de las notificaciones (español)."""
from __future__ import annotations

from app.models import Match

_SIDE = {"home": "local", "away": "visitante"}
_PERIOD = {"Q1": "1.er cuarto", "Q2": "2.º cuarto", "Q3": "3.er cuarto", "Q4": "4.º cuarto", "OT": "la prórroga"}


def _sc(m: Match) -> str:
    return f"{m.home.name} {m.home_score if m.home_score is not None else 0}-" \
           f"{m.away_score if m.away_score is not None else 0} {m.away.name}"


def _team(m: Match, side: str | None) -> str:
    return m.home.name if side == "home" else m.away.name if side == "away" else ""


def build(m: Match, etype: str, p: dict) -> tuple[str, str]:
    vs = f"{m.home.name} vs {m.away.name}"
    minute = f" ({p['minute']}')" if p.get("minute") else ""
    player = p.get("player") or ""
    if etype == "upcoming":
        return f"⏰ Empieza en {p.get('minutes', '')} min", vs
    if etype in ("kickoff", "tipoff", "match_start"):
        return "▶️ ¡Comienza el partido!", vs
    if etype == "halftime_start":
        return "⏸️ Descanso", _sc(m)
    if etype == "halftime_end":
        return "▶️ Comienza la segunda parte", _sc(m)
    if etype == "goal":
        who = f"{player} ({_team(m, p.get('side'))})" if player else _team(m, p.get("side"))
        return f"⚽ ¡Gol!{minute}", f"{who}. {_sc(m)}"
    if etype == "goal_cancelled":
        return "❌ Gol anulado", _sc(m)
    if etype == "yellow_card":
        return f"🟨 Tarjeta amarilla{minute}", f"{player} ({_team(m, p.get('side'))}). {vs}"
    if etype == "red_card":
        return f"🟥 ¡Tarjeta roja!{minute}", f"{player} ({_team(m, p.get('side'))}). {_sc(m)}"
    if etype == "penalty_missed":
        return f"🚫 Penalti fallado{minute}", f"{player} ({_team(m, p.get('side'))}). {_sc(m)}"
    if etype == "substitution":
        return f"🔁 Cambio{minute}", f"{_team(m, p.get('side'))}: {player} ({p.get('detail', '')})"
    if etype == "period_end":
        return f"🏀 Final del {_PERIOD.get(p.get('period'), p.get('period', 'periodo'))}", _sc(m)
    if etype == "lead_change":
        return "🔄 Cambio de líder", f"{_team(m, p.get('leader'))} manda. {_sc(m)}"
    if etype == "big_run":
        return f"🔥 Parcial de {p.get('swing')} puntos", f"A favor de {_team(m, p.get('side'))}. {_sc(m)}"
    if etype == "set_end":
        ss = p.get("set_score") or {}
        sets = p.get("sets") or {}
        return f"🎾 Fin del set {p.get('set')}", (f"{ss.get('home', '?')}-{ss.get('away', '?')}. Sets: "
                                                 f"{m.home.name} {sets.get('home')}-{sets.get('away')} {m.away.name}")
    if etype == "game_score":
        g = p.get("games") or {}
        return f"🎾 Set {p.get('set')}: {g.get('home')}-{g.get('away')}", vs
    if etype == "full_time":
        if m.sport.value == "tennis":
            w = _team(m, p.get("winner")) or "—"
            return "🏁 Final del partido", f"Gana {w}. Sets {m.home_score}-{m.away_score}"
        return "🏁 Final del partido", _sc(m)
    return "Actualización del partido", vs
