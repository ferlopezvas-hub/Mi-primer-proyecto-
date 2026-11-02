import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123")
os.environ.setdefault("RATE_LIMIT_AUTH_PER_MIN", "1000")
for k in ("API_FOOTBALL_KEY", "API_BASKETBALL_KEY", "API_TENNIS_KEY", "FOOTBALL_DATA_ORG_KEY"):
    os.environ[k] = ""

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db as dbmod  # noqa: E402
from app.db import Base  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.providers.registry import set_providers  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.store import get_store  # noqa: E402

PASSWORD = "Sup3rSecretPass"


@pytest.fixture(autouse=True)
def _fresh_db():
    engine = dbmod.get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    get_store().flushall()
    set_providers([])
    yield
    set_providers(None)


@pytest.fixture
def db():
    s = dbmod.SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def make_user(db, email="ana@example.com", role=Role.user, plan="free") -> User:
    u = User(email=email, password_hash=hash_password(PASSWORD), full_name="Ana", role=role, plan_code=plan)
    db.add(u)
    db.commit()
    return u


def login(client, email="ana@example.com") -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def auth(client, user):
    return login(client)


@pytest.fixture
def admin_auth(client, db):
    make_user(db, "admin@example.com", Role.admin, "elite")
    return login(client, "admin@example.com")


def utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


def now_plus(**kw) -> datetime:
    return datetime.now(UTC) + timedelta(**kw)
