from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import Follow, Match, MatchEvent, MatchStatus, PushSubscription, Sport, UserNotification
from app.notifications.service import PushSender, fanout_pending, in_quiet_hours, notify_upcoming
from app.providers.base import EventDTO
from app.providers.registry import set_providers
from app.sync import jobs
from app.sync.service import process
from tests.factories import FakeProvider, dto


def _now():
    return datetime.now(UTC)


def _follow_team(db, user, match_pid="m1"):
    m = db.scalar(select(Match).where(Match.provider_id == match_pid))
    db.add(Follow(user_id=user.id, kind="team", target_id=m.home_id))
    db.commit()
    return m


def _events(db):
    return [e.type for e in db.scalars(select(MatchEvent).order_by(MatchEvent.id)).all()]


def test_upsert_is_idempotent(db):
    start = _now() + timedelta(hours=3)
    for _ in range(3):
        process(db, "fake", [dto(start=start)])
    assert db.scalar(select(func.count()).select_from(Match)) == 1


def test_football_live_flow_generates_deduplicated_notifications(db, user):
    start = _now() - timedelta(minutes=1)
    process(db, "fake", [dto(start=start)])
    _follow_team(db, user)
    live = dict(start=start, status=MatchStatus.live)
    steps = [
        dto(**live, detail="1H", hs=0, as_=0),
        dto(**live, detail="1H", hs=1, as_=0, events=[EventDTO("goal", 12, "home", "Pérez")]),
        dto(**live, detail="1H", hs=1, as_=0, events=[EventDTO("goal", 12, "home", "Pérez")]),  # repetido
        dto(**live, detail="HT", hs=1, as_=0, events=[EventDTO("goal", 12, "home", "Pérez"),
                                                      EventDTO("yellow_card", 40, "away", "Jones")]),
        dto(**live, detail="2H", hs=1, as_=1, events=[EventDTO("goal", 12, "home", "Pérez"),
                                                      EventDTO("yellow_card", 40, "away", "Jones"),
                                                      EventDTO("goal", 55, "away", "Smith"),
                                                      EventDTO("red_card", 70, "home", "Ruiz")]),
        dto(start=start, status=MatchStatus.finished, detail="FT", hs=1, as_=1),
        dto(start=start, status=MatchStatus.finished, detail="FT", hs=1, as_=1),  # repetido
    ]
    for s in steps:
        process(db, "fake", [s])
    assert _events(db) == ["kickoff", "goal", "halftime_start", "yellow_card", "halftime_end", "goal",
                           "red_card", "full_time"]
    fanout_pending(db)
    notes = db.scalars(select(UserNotification).order_by(UserNotification.id)).all()
    kinds = [n.kind for n in notes]
    # Por defecto: amarillas y fin del descanso desactivadas
    assert kinds == ["kickoff", "goal", "halftime_start", "goal", "red_card", "full_time"]
    assert "Pérez" in notes[1].body and "Equipo A" in notes[1].body
    fanout_pending(db)  # segunda pasada: nada nuevo
    assert db.scalar(select(func.count()).select_from(UserNotification)) == 6


def test_goal_detection_without_detailed_events_and_var(db, user):
    start = _now()
    live = dict(start=start, status=MatchStatus.live, detail="1H")
    process(db, "fake", [dto(**live, hs=0, as_=0)])
    process(db, "fake", [dto(**live, hs=2, as_=0)])  # dos goles entre consultas
    process(db, "fake", [dto(**live, hs=1, as_=0)])  # VAR anula uno
    process(db, "fake", [dto(**live, hs=2, as_=0)])  # vuelve a marcar
    assert _events(db) == ["goal", "goal", "goal_cancelled", "goal"]


def test_user_preferences_filter_events(client, db, user, auth):
    r = client.put("/api/v1/me/notification-preferences", headers=auth,
                   json={"events": {"football": {"goal": False, "yellow_card": True}}})
    assert r.status_code == 200
    assert client.put("/api/v1/me/notification-preferences", headers=auth,
                      json={"events": {"football": {"nope": True}}}).status_code == 400
    db.expire_all()  # el usuario se modificó en otra sesión (la de la API)
    start = _now()
    process(db, "fake", [dto(start=start)])
    _follow_team(db, user)
    process(db, "fake", [dto(start=start, status=MatchStatus.live, detail="1H", hs=1, as_=0,
                             events=[EventDTO("goal", 5, "home", "A"), EventDTO("yellow_card", 6, "away", "B")])])
    fanout_pending(db)
    db.expire_all()
    kinds = {n.kind for n in db.scalars(select(UserNotification)).all()}
    assert kinds == {"kickoff", "yellow_card"}


def test_no_notifications_for_first_sight_or_old_matches(db, user):
    old = _now() - timedelta(days=2)
    process(db, "fake", [dto(start=old)])
    _follow_team(db, user)
    process(db, "fake", [dto(start=old, status=MatchStatus.finished, detail="FT", hs=1, as_=0)])
    assert fanout_pending(db) == []
    assert db.scalar(select(func.count()).select_from(UserNotification)) == 0
    # primera vez que se ve un partido ya en juego: no se notifica retroactivamente
    process(db, "fake", [dto(pid="m2", start=_now(), status=MatchStatus.live, detail="2H", hs=3, as_=0)])
    m2 = db.scalar(select(Match).where(Match.provider_id == "m2"))
    assert db.scalar(select(func.count()).select_from(MatchEvent).where(MatchEvent.match_id == m2.id)) == 0
    # los eventos del partido antiguo se registran, pero marcados como ya repartidos (silenciosos)
    assert all(e.fanned_out for e in db.scalars(select(MatchEvent)).all())


def test_basketball_events(db):
    start = _now()
    b = dict(sport=Sport.basketball, start=start, status=MatchStatus.live)
    process(db, "fake", [dto(sport=Sport.basketball, start=start)])
    seq = [("Q1", 0, 0), ("Q1", 10, 2), ("Q2", 20, 20), ("Q4", 80, 78), ("Q4", 80, 82), ("Q4", 80, 92)]
    for d, h, a in seq:
        process(db, "fake", [dto(**b, detail=d, hs=h, as_=a)])
    process(db, "fake", [dto(sport=Sport.basketball, start=start, status=MatchStatus.finished, detail="FT",
                             hs=85, as_=95)])
    ev = _events(db)
    assert ev[0] == "tipoff"
    assert "period_end" in ev and "lead_change" in ev and "big_run" in ev and ev[-1] == "full_time"


def test_tennis_events(db):
    start = _now()
    t = dict(sport=Sport.tennis, start=start, status=MatchStatus.live, detail="Set 1")
    process(db, "fake", [dto(sport=Sport.tennis, start=start)])
    process(db, "fake", [dto(**t, hs=0, as_=0, periods={"sets": [{"set": 1, "home": 1, "away": 0}]})])
    process(db, "fake", [dto(**t, hs=1, as_=0, periods={"sets": [{"set": 1, "home": 6, "away": 4},
                                                                  {"set": 2, "home": 0, "away": 0}]})])
    process(db, "fake", [dto(sport=Sport.tennis, start=start, status=MatchStatus.finished, detail="Finished", hs=2,
                             as_=0, periods={"winner": "home", "sets": [{"set": 1, "home": 6, "away": 4},
                                                                         {"set": 2, "home": 6, "away": 3}]})])
    ev = _events(db)
    assert ev.count("set_end") == 2 and ev[0] == "match_start" and ev[-1] == "full_time"


def test_upcoming_notification_respects_lead_time(db, user):
    process(db, "fake", [dto(start=_now() + timedelta(minutes=50))])
    _follow_team(db, user)
    notify_upcoming(db)
    assert db.scalar(select(func.count()).select_from(UserNotification)) == 0  # 50 > 30 min por defecto
    later = _now() + timedelta(minutes=25)
    notify_upcoming(db, now=later)
    notify_upcoming(db, now=later + timedelta(minutes=1))  # no duplica
    assert db.scalar(select(func.count()).select_from(UserNotification)) == 1


def test_quiet_hours():
    prefs = {"quiet_hours": {"start": "23:00", "end": "08:00"}}
    night = datetime(2026, 11, 2, 23, 30, tzinfo=UTC)
    day = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    assert in_quiet_hours(prefs, "UTC", night) and not in_quiet_hours(prefs, "UTC", day)


def test_push_sender_removes_expired_subscriptions(db, user):
    from pywebpush import WebPushException

    from app.config import get_settings

    s = get_settings()
    s.vapid_private_key, s.vapid_public_key = "priv", "pub"
    try:
        process(db, "fake", [dto(start=_now())])
        m = db.scalar(select(Match))
        db.add_all([PushSubscription(user_id=user.id, endpoint="https://push/ok", p256dh="k", auth="a"),
                    PushSubscription(user_id=user.id, endpoint="https://push/gone", p256dh="k", auth="a")])
        n = UserNotification(user_id=user.id, match_id=m.id, kind="goal", title="t", body="b", dedup_key="x")
        db.add(n)
        db.commit()

        class Resp:
            status_code = 410

        def fake_webpush(subscription_info, **kw):
            if subscription_info["endpoint"].endswith("gone"):
                raise WebPushException("gone", response=Resp())

        res = PushSender(fake_webpush).send(db, n.id)
        assert res == {"sent": 1, "failed": 1, "retry": False}
        assert [p.endpoint for p in db.scalars(select(PushSubscription)).all()] == ["https://push/ok"]
        assert PushSender(fake_webpush).send(db, n.id) == {"skipped": True}  # no se reenvía
    finally:
        s.vapid_private_key, s.vapid_public_key = "", ""


def test_jobs_with_fake_provider(db):
    p = FakeProvider()
    set_providers([p])
    start = _now() + timedelta(minutes=5)
    p.fixtures_data = [dto(start=start)]
    out = jobs.run_sync_fixtures(db)
    assert out["providers"]["fake"]["created"] == 1
    # en ventana de directo -> consulta live; el partido desaparece del feed -> by_ids
    p.live_data = [dto(start=start, status=MatchStatus.live, detail="1H", hs=0, as_=0)]
    jobs.run_sync_live(db)
    p.live_data = []
    p.by_id["m1"] = dto(start=start, status=MatchStatus.finished, detail="FT", hs=0, as_=0)
    jobs.run_sync_live(db)
    assert "by_ids:m1" in p.calls
    assert db.scalar(select(Match)).status == MatchStatus.finished


def test_live_poll_skipped_without_matches(db):
    p = FakeProvider()
    set_providers([p])
    assert "skipped" in jobs.run_sync_live(db)
    assert p.calls == []


def test_sync_results_closes_stale_matches(db):
    p = FakeProvider()
    set_providers([p])
    start = _now() - timedelta(hours=5)
    process(db, "fake", [dto(start=start, status=MatchStatus.live, detail="2H", hs=1, as_=0)])
    p.by_id["m1"] = dto(start=start, status=MatchStatus.finished, detail="FT", hs=1, as_=0)
    jobs.run_sync_results(db)
    assert db.scalar(select(Match)).status == MatchStatus.finished


def test_temporary_provider_error_is_reported(db):
    from app.providers.base import ProviderTemporaryError

    class Broken(FakeProvider):
        def fixtures(self, a, b):
            raise ProviderTemporaryError("timeout")

    set_providers([Broken(), FakeProvider(Sport.tennis, "ok")])
    out = jobs.run_sync_fixtures(db)
    assert jobs.has_temporary_errors(out)
    assert out["providers"]["ok"]["fetched"] == 0  # el otro proveedor sigue funcionando


def test_notification_center_api(client, db, user, auth):
    process(db, "fake", [dto(start=_now())])
    m = db.scalar(select(Match))
    db.add_all([UserNotification(user_id=user.id, match_id=m.id, kind="goal", title=f"t{i}", body="",
                                 dedup_key=f"k{i}") for i in range(3)])
    db.commit()
    r = client.get("/api/v1/notifications", headers=auth).json()
    assert r["unread"] == 3 and len(r["items"]) == 3
    client.post(f"/api/v1/notifications/{r['items'][0]['id']}/read", headers=auth)
    assert client.get("/api/v1/notifications", headers=auth).json()["unread"] == 2
    client.post("/api/v1/notifications/read-all", headers=auth)
    assert client.get("/api/v1/notifications", headers=auth).json()["unread"] == 0


def test_follow_limits_by_plan(client, db, user, auth):
    for i in range(6):
        process(db, "fake", [dto(pid=f"x{i}", home=f"H{i}", away=f"A{i}", start=_now())])
    teams = [m.home_id for m in db.scalars(select(Match)).all()]
    codes = [client.post("/api/v1/me/follows", headers=auth, json={"kind": "team", "target_id": t}).status_code
             for t in teams]
    assert codes == [201] * 5 + [402]
    assert client.post("/api/v1/me/follows", headers=auth, json={"kind": "team", "target_id": 99999}).status_code \
        == 404


def test_push_subscription_api(client, auth):
    body = {"endpoint": "https://fcm.googleapis.com/x", "keys": {"p256dh": "a", "auth": "b"}}
    assert client.post("/api/v1/me/push-subscriptions", headers=auth, json=body).status_code == 201
    assert client.post("/api/v1/me/push-subscriptions", headers=auth,
                       json={**body, "endpoint": "http://insecure"}).status_code == 400
