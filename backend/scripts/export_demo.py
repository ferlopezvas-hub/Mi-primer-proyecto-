"""Exporta un paquete de datos REALES para la versión demo estática del frontend.

Uso (con la base de datos ya cargada con históricos y backtest):
    python scripts/export_demo.py --since 2026-08-01 --out ../frontend/demo/demo-data.json

Se exportan las respuestas reales de la API (mismo formato que en producción). Las
notificaciones de ejemplo se generan a partir de resultados reales (descanso y final)
de los equipos que sigue el usuario demo, y se marcan como de demostración.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime

os.environ.setdefault("RATE_LIMIT_USER_PER_MIN", "1000000")
os.environ.setdefault("RATE_LIMIT_AUTH_PER_MIN", "1000000")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import joinedload  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Match, MatchStatus, Role, User  # noqa: E402
from app.notifications import messages  # noqa: E402
from app.notifications.prefs import EVENT_CATALOG  # noqa: E402
from app.security import hash_password  # noqa: E402

DEMO_EMAIL = "demo-export@sportai.local"
DEMO_PASSWORD = "DemoExport2026x"
FOLLOW_TEAMS = ["Real Madrid", "Barcelona", "Liverpool", "Inter"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-01")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    since = datetime.fromisoformat(a.since).replace(tzinfo=UTC)

    db = SessionLocal()
    u = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if u is None:
        u = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD), full_name="Usuario demo")
        db.add(u)
    u.role, u.plan_code, u.is_active = Role.admin, "elite", True
    db.commit()

    c = TestClient(app)
    tok = c.post("/api/v1/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    def get(path: str):
        r = c.get("/api/v1" + path, headers=h)
        r.raise_for_status()
        return r.json()

    matches = db.scalars(
        select(Match).options(joinedload(Match.home), joinedload(Match.away), joinedload(Match.competition))
        .where(Match.start_time >= since).order_by(Match.start_time)
    ).unique().all()
    details, predictions = {}, {}
    for m in matches:
        details[m.id] = get(f"/sports/matches/{m.id}")
        predictions[m.id] = get(f"/predictions/match/{m.id}")

    # Notificaciones de ejemplo a partir de resultados reales de los equipos seguidos
    followed = [m for m in matches if m.status == MatchStatus.finished
                and (m.home.name in FOLLOW_TEAMS or m.away.name in FOLLOW_TEAMS)]
    notes, nid = [], 1
    for m in followed[-12:]:
        ht = (m.periods or {}).get("halftime")
        events = []
        if ht:
            events.append(("halftime_start", ht, 50))
        events.append(("full_time", {"home": m.home_score, "away": m.away_score}, 110))
        for kind, score, minutes in events:
            hs, as_ = m.home_score, m.away_score
            m.home_score, m.away_score = score["home"], score["away"]
            title, body = messages.build(m, kind, {"score": score})
            m.home_score, m.away_score = hs, as_
            when = m.start_time.timestamp() + minutes * 60
            notes.append({"id": nid, "kind": kind, "title": title, "body": body, "match_id": m.id,
                          "data": {"sport": "football", "url": f"/matches/{m.id}", "demo": True},
                          "created_at": datetime.fromtimestamp(when, UTC).isoformat(), "read_at": None})
            nid += 1
    db.expire_all()
    notes.sort(key=lambda n: n["created_at"], reverse=True)
    for n in notes[4:]:
        n["read_at"] = n["created_at"]

    team_ids = {}
    for m in matches:
        team_ids.setdefault(m.home.name, m.home.id)
        team_ids.setdefault(m.away.name, m.away.id)
    follows = [{"id": i + 1, "kind": "team", "target_id": team_ids[name], "name": name, "sport": "football"}
               for i, name in enumerate(FOLLOW_TEAMS) if name in team_ids]

    admin_users = get("/admin/users")
    admin_users["items"] = [x for x in admin_users["items"] if x["email"] != DEMO_EMAIL]
    data = {
        "generated_at": datetime.now(UTC).isoformat(),
        "since": a.since,
        "source": "football-data.co.uk (resultados reales) · predicciones del backtest walk-forward",
        "me": {**get("/me"), "email": "demo@sportai", "full_name": "Usuario demo"},
        "plans": get("/me/plans"),
        "prefs": get("/me/notification-preferences"),
        "catalog": EVENT_CATALOG,
        "matches": [d["match"] for d in details.values()],
        "details": details,
        "predictions": predictions,
        "competitions": get("/sports/competitions"),
        "evaluation": {"all": get("/evaluation"), "live": get("/evaluation?mode=live"),
                       "backtest": get("/evaluation?mode=backtest")},
        "notifications": notes,
        "follows": follows,
        "admin": {"metrics": get("/admin/metrics?days=30"), "providers": get("/admin/providers"),
                  "jobs": get("/admin/jobs?limit=40"), "users": admin_users},
    }
    # El usuario de exportación no debe quedar en la base de datos
    db.delete(db.scalar(select(User).where(User.email == DEMO_EMAIL)))
    db.commit()
    db.close()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), default=str)
    print(f"{len(matches)} partidos, {sum(len(p['predictions']) for p in predictions.values())} predicciones, "
          f"{len(notes)} avisos -> {a.out} ({os.path.getsize(a.out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
