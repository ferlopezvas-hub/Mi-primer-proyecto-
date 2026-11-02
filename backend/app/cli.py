"""Utilidades de operación.

  python -m app.cli create-admin --email admin@tu-dominio.com
  python -m app.cli import-history --divisions SP1,E0 --seasons 2223,2324,2425,2526
  python -m app.cli import-fixtures            (próximos partidos de football-data.co.uk)
  python -m app.cli backtest --sport football --from 2025-08-01 --to 2026-06-30
  python -m app.cli evaluation [--mode backtest]
  python -m app.cli vapid-keys
  python -m app.cli sync fixtures|live|results|predictions|resolve
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import UTC, datetime

from app.db import session_scope
from app.logging_config import setup_logging


def _create_admin(a):
    from sqlalchemy import select

    from app.models import Role, User
    from app.security import hash_password, validate_password_strength

    pwd = a.password or getpass.getpass("Contraseña: ")
    if err := validate_password_strength(pwd):
        sys.exit(err)
    with session_scope() as db:
        u = db.scalar(select(User).where(User.email == a.email.lower()))
        if u is None:
            u = User(email=a.email.lower(), password_hash=hash_password(pwd), full_name="Administrador")
            db.add(u)
        u.role, u.plan_code, u.is_active = Role.admin, "elite", True
    print(f"Administrador listo: {a.email}")


def _import_history(a):
    import httpx

    from app.providers.football_data_uk import PROVIDER, download, parse_csv
    from app.sync.service import process

    client = httpx.Client(timeout=30, follow_redirects=True)
    for div in a.divisions.split(","):
        for season in a.seasons.split(","):
            try:
                text = download(div, season, client)
            except httpx.HTTPError as exc:
                print(f"{div} {season}: no disponible ({exc})")
                continue
            dtos = parse_csv(text, div, f"20{season[:2]}")
            with session_scope() as db:
                r = process(db, PROVIDER, dtos, notify=False)
            print(f"{div} {season}: {len(dtos)} partidos (nuevos {r.created}, actualizados {r.updated})")


def _import_fixtures(a):
    from app.providers.football_data_uk import PROVIDER, download_fixtures, parse_fixtures
    from app.sync.service import process

    dtos = parse_fixtures(download_fixtures(), a.season)
    with session_scope() as db:
        r = process(db, PROVIDER, dtos, notify=False)
    print(f"Próximos partidos: {len(dtos)} (nuevos {r.created}, actualizados {r.updated})")


def _backtest(a):
    from app.evaluation.backtest import walk_forward
    from app.models import Sport

    start = datetime.fromisoformat(a.date_from).replace(tzinfo=UTC)
    end = datetime.fromisoformat(a.date_to).replace(tzinfo=UTC)
    with session_scope() as db:
        print(json.dumps(walk_forward(db, Sport(a.sport), start, end, a.competition, a.refit_days), indent=2))


def _evaluation(a):
    from app.evaluation.service import report

    with session_scope() as db:
        r = report(db, sport=a.sport, mode=a.mode)
    r.pop("calibration") if not a.full else None
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


def _vapid(_a):
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    print(f"VAPID_PUBLIC_KEY={b64(pub)}\nVAPID_PRIVATE_KEY={b64(priv)}")


def _sync(a):
    from app.engines.service import generate_upcoming
    from app.evaluation.resolve import resolve_pending
    from app.sync import jobs

    fn = {"fixtures": jobs.run_sync_fixtures, "live": jobs.run_sync_live, "results": jobs.run_sync_results,
          "predictions": generate_upcoming, "resolve": lambda db: {"resolved": resolve_pending(db)}}[a.what]
    with session_scope() as db:
        print(json.dumps(fn(db), indent=2, default=str))


def main(argv=None):
    setup_logging()
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(required=True)
    s = sub.add_parser("create-admin")
    s.add_argument("--email", required=True)
    s.add_argument("--password")
    s.set_defaults(fn=_create_admin)
    s = sub.add_parser("import-history")
    s.add_argument("--divisions", default="SP1,E0")
    s.add_argument("--seasons", default="2223,2324,2425,2526")
    s.set_defaults(fn=_import_history)
    s = sub.add_parser("import-fixtures")
    s.add_argument("--season", default=str(datetime.now(UTC).year if datetime.now(UTC).month >= 7
                                           else datetime.now(UTC).year - 1))
    s.set_defaults(fn=_import_fixtures)
    s = sub.add_parser("backtest")
    s.add_argument("--sport", default="football", choices=["football", "basketball", "tennis"])
    s.add_argument("--from", dest="date_from", required=True)
    s.add_argument("--to", dest="date_to", required=True)
    s.add_argument("--competition")
    s.add_argument("--refit-days", type=int, default=7)
    s.set_defaults(fn=_backtest)
    s = sub.add_parser("evaluation")
    s.add_argument("--sport")
    s.add_argument("--mode", choices=["live", "backtest"])
    s.add_argument("--full", action="store_true")
    s.set_defaults(fn=_evaluation)
    s = sub.add_parser("vapid-keys")
    s.set_defaults(fn=_vapid)
    s = sub.add_parser("sync")
    s.add_argument("what", choices=["fixtures", "live", "results", "predictions", "resolve"])
    s.set_defaults(fn=_sync)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
