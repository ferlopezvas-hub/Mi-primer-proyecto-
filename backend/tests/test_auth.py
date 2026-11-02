from app.notifications.email import OUTBOX
from tests.conftest import PASSWORD, login


def test_register_login_me(client):
    r = client.post("/api/v1/auth/register", json={"email": "Nuevo@Example.com", "password": "Abcdefgh123",
                                                   "full_name": "Nuevo", "accept_terms": True})
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email"] == "nuevo@example.com"
    assert r.json()["user"]["plan"]["code"] == "free"
    tok = r.json()["tokens"]["access_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200 and me.json()["full_name"] == "Nuevo"


def test_register_rejects_weak_password_and_terms(client):
    base = {"email": "x@example.com", "full_name": "", "accept_terms": True}
    assert client.post("/api/v1/auth/register", json={**base, "password": "short"}).status_code == 400
    assert client.post("/api/v1/auth/register", json={**base, "password": "alllowercase123"}).status_code == 400
    r = client.post("/api/v1/auth/register", json={**base, "password": "Abcdefgh123", "accept_terms": False})
    assert r.status_code == 400


def test_duplicate_email(client, user):
    r = client.post("/api/v1/auth/register", json={"email": "ana@example.com", "password": "Abcdefgh123",
                                                   "accept_terms": True})
    assert r.status_code == 409


def test_login_wrong_password_generic_error(client, user):
    r1 = client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "bad"})
    r2 = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "bad"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_protected_requires_token(client):
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_refresh_rotation_and_reuse_detection(client, user):
    r = client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": PASSWORD}).json()
    first = r["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert r2.status_code == 200
    second = r2.json()["refresh_token"]
    # reutilizar el token ya rotado revoca toda la familia
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_password_reset_flow(client, user):
    OUTBOX.clear()
    r = client.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"})
    assert r.status_code == 202
    r_unknown = client.post("/api/v1/auth/forgot-password", json={"email": "zz@example.com"})
    assert r_unknown.json() == r.json()  # no revela si existe
    assert len(OUTBOX) == 1
    body = OUTBOX[0].get_content()
    token = body.split("token=")[1].split()[0]
    old_headers = login(client)
    ok = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "NuevaClave2025"})
    assert ok.status_code == 200
    # token de un solo uso
    assert client.post("/api/v1/auth/reset-password",
                       json={"token": token, "new_password": "OtraClave2025x"}).status_code == 400
    # las sesiones previas quedan invalidadas
    assert client.get("/api/v1/me", headers=old_headers).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "ana@example.com",
                                                   "password": "NuevaClave2025"}).status_code == 200


def test_logout_all_invalidates_access_tokens(client, auth):
    assert client.post("/api/v1/auth/logout-all", headers=auth).status_code == 204
    assert client.get("/api/v1/me", headers=auth).status_code == 401


def test_rate_limit_auth(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_auth_per_min", 3)
    codes = [client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "x"}).status_code
             for _ in range(5)]
    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429


def test_admin_requires_role(client, auth, admin_auth):
    assert client.get("/api/v1/admin/users", headers=auth).status_code == 403
    r = client.get("/api/v1/admin/users", headers=admin_auth)
    assert r.status_code == 200 and r.json()["total"] == 2


def test_admin_change_plan_and_audit(client, auth, admin_auth, user):
    r = client.patch(f"/api/v1/admin/users/{user.id}", json={"plan_code": "pro"}, headers=admin_auth)
    assert r.status_code == 200 and r.json()["plan"]["code"] == "pro"
    assert client.patch(f"/api/v1/admin/users/{user.id}", json={"plan_code": "nope"},
                        headers=admin_auth).status_code == 400
    audit = client.get("/api/v1/admin/audit", headers=admin_auth).json()
    assert audit[0]["action"] == "user.update"


def test_delete_account(client, auth):
    assert client.request("DELETE", "/api/v1/me", json={"password": "wrong"}, headers=auth).status_code == 400
    assert client.request("DELETE", "/api/v1/me", json={"password": PASSWORD}, headers=auth).status_code == 204
    assert client.get("/api/v1/me", headers=auth).status_code == 401


def test_security_headers_and_health(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Request-ID" in r.headers
    ready = client.get("/health/ready").json()
    assert ready["checks"]["database"]["ok"] is True
