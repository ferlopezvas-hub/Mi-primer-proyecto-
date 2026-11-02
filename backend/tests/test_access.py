from datetime import UTC, datetime, timedelta

import pytest

from app.access import send_expiry_reminders
from app.config import get_settings
from app.models import UserNotification


@pytest.fixture
def private_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "require_access_grant", True)
    monkeypatch.setattr(get_settings(), "admin_contact", "WhatsApp +593 99 000 0000")


def test_user_without_access_only_sees_profile(client, auth, private_mode):
    me = client.get("/api/v1/me", headers=auth).json()
    assert me["access_active"] is False and me["admin_contact"].startswith("WhatsApp")
    r = client.get("/api/v1/sports/live", headers=auth)
    assert r.status_code == 403 and r.headers["X-Access"] == "inactive"
    assert client.get("/api/v1/evaluation", headers=auth).status_code == 403


def test_admin_grants_and_renews_30_days(client, db, auth, admin_auth, user, private_mode):
    r = client.post(f"/api/v1/admin/users/{user.id}/access", headers=admin_auth,
                    json={"days": 30, "amount": 20, "currency": "usd", "note": "Transferencia Banco Pichincha"})
    assert r.status_code == 200 and r.json()["access_active"] is True
    end1 = datetime.fromisoformat(r.json()["access_expires_at"])
    assert timedelta(days=29, hours=23) < end1.replace(tzinfo=UTC) - datetime.now(UTC) <= timedelta(days=30)
    assert client.get("/api/v1/sports/live", headers=auth).status_code == 200
    # renovar con el acceso vigente: se encadena (60 días en total, no se pierden días)
    r2 = client.post(f"/api/v1/admin/users/{user.id}/access", headers=admin_auth, json={"days": 30, "amount": 20})
    end2 = datetime.fromisoformat(r2.json()["access_expires_at"])
    assert (end2 - end1).days == 30
    grants = client.get(f"/api/v1/admin/users/{user.id}/grants", headers=admin_auth).json()
    assert len(grants) == 2 and grants[1]["note"] == "Transferencia Banco Pichincha"
    inc = client.get("/api/v1/admin/income", headers=admin_auth).json()
    month = datetime.now(UTC).strftime("%Y-%m")
    assert inc["months"][month] == {"grants": 2, "total": {"USD": 40.0}} and inc["active_users"] == 1
    kinds = [n["kind"] for n in client.get("/api/v1/notifications", headers=auth).json()["items"]]
    assert "access_granted" in kinds
    # revocar
    client.post(f"/api/v1/admin/users/{user.id}/access/revoke", headers=admin_auth)
    assert client.get("/api/v1/sports/live", headers=auth).status_code == 401  # sesión cerrada al revocar


def test_only_admin_can_grant(client, auth, user, private_mode):
    assert client.post(f"/api/v1/admin/users/{user.id}/access", headers=auth, json={"days": 30}).status_code == 403


def test_access_expires(client, db, auth, user, private_mode):
    user.access_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert client.get("/api/v1/sports/live", headers=auth).status_code == 403


def test_expiry_reminder_once(db, user, private_mode):
    user.access_expires_at = datetime.now(UTC) + timedelta(days=2)
    db.commit()
    assert send_expiry_reminders(db) == 1
    assert send_expiry_reminders(db) == 0
    n = db.query(UserNotification).one()
    assert "WhatsApp" in n.body and n.kind == "access_expiring"
