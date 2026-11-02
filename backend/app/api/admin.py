from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import user_out
from app.config import get_settings
from app.db import get_db
from app.deps import require_admin
from app.models import (
    AuditLog,
    JobRun,
    Match,
    MatchStatus,
    Prediction,
    PushSubscription,
    Role,
    UsageEvent,
    User,
    UserNotification,
)
from app.plans import PLANS
from app.providers.http import circuit_state, quota_used
from app.providers.registry import all_providers

router = APIRouter(prefix="/admin", tags=["admin"])

ALLOWED_TASKS = {"sync_fixtures", "sync_live", "sync_results", "generate_predictions", "resolve_predictions",
                 "fanout_events", "check_upcoming"}


class UserPatch(BaseModel):
    role: Role | None = None
    plan_code: str | None = None
    is_active: bool | None = None


@router.get("/users")
def users(q: str | None = None, limit: int = Query(50, le=200), offset: int = 0,
          _: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(User)
    if q:
        stmt = stmt.where(func.lower(User.email).like(f"%{q.lower()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(User.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [{**user_out(u), "is_active": u.is_active, "last_login_at": u.last_login_at}
                                      for u in rows]}


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "No encontrado")
    if u.id == admin.id and (body.role == Role.user or body.is_active is False):
        raise HTTPException(400, "No puedes quitarte permisos ni desactivarte a ti mismo")
    changes = body.model_dump(exclude_none=True)
    if "plan_code" in changes and changes["plan_code"] not in PLANS:
        raise HTTPException(400, "Plan desconocido")
    for k, v in changes.items():
        setattr(u, k, v)
    if body.is_active is False or body.role is not None:
        u.token_version += 1  # fuerza a renovar sesión con los nuevos permisos
    db.add(AuditLog(actor_id=admin.id, action="user.update",
                    detail={"user_id": u.id, **{k: str(v) for k, v in changes.items()}}))
    db.commit()
    return {**user_out(u), "is_active": u.is_active}


@router.get("/metrics")
def metrics(days: int = Query(30, ge=1, le=365), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    since = datetime.now(UTC) - timedelta(days=days)
    day = func.date(UsageEvent.created_at)
    usage = db.execute(select(day, UsageEvent.kind, func.count(), func.count(func.distinct(UsageEvent.user_id)))
                       .where(UsageEvent.created_at >= since).group_by(day, UsageEvent.kind).order_by(day)).all()
    series: dict[str, dict] = {}
    for d, kind, n, users_ in usage:
        series.setdefault(str(d), {})[kind] = {"events": n, "users": users_}
    by_plan = dict(db.execute(select(User.plan_code, func.count()).group_by(User.plan_code)).all())
    return {
        "users_total": db.scalar(select(func.count()).select_from(User)),
        "users_active_period": db.scalar(select(func.count(func.distinct(UsageEvent.user_id)))
                                         .where(UsageEvent.created_at >= since)),
        "users_by_plan": by_plan,
        "push_subscriptions": db.scalar(select(func.count()).select_from(PushSubscription)),
        "notifications_period": db.scalar(select(func.count()).select_from(UserNotification)
                                          .where(UserNotification.created_at >= since)),
        "matches": dict((k.value, v) for k, v in db.execute(select(Match.status, func.count())
                                                             .group_by(Match.status)).all()),
        "predictions_live": db.scalar(select(func.count()).select_from(Prediction)
                                      .where(Prediction.is_backtest.is_(False))),
        "predictions_backtest": db.scalar(select(func.count()).select_from(Prediction)
                                          .where(Prediction.is_backtest.is_(True))),
        "daily": series,
    }


@router.get("/providers")
def providers(_: User = Depends(require_admin)):
    s = get_settings()
    quotas = {"api-football": s.api_football_daily_quota, "api-basketball": s.api_basketball_daily_quota,
              "api-tennis": s.api_tennis_daily_quota}
    return [{"name": p.name, "sport": p.sport.value, "configured": p.is_configured(), "supports_live": p.supports_live,
             "quota_used_today": quota_used(p.name), "daily_quota": quotas.get(p.name),
             "circuit": circuit_state(p.name)} for p in all_providers()]


@router.get("/jobs")
def jobs(limit: int = Query(50, le=200), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(JobRun).order_by(JobRun.id.desc()).limit(limit)).all()
    live = db.scalar(select(func.count()).select_from(Match).where(Match.status == MatchStatus.live))
    return {"live_matches": live, "runs": [{"id": r.id, "name": r.name, "status": r.status, "started_at": r.started_at,
                                            "finished_at": r.finished_at, "detail": r.detail} for r in rows]}


@router.post("/jobs/{name}/run", status_code=202)
def run_job(name: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if name not in ALLOWED_TASKS:
        raise HTTPException(404, "Tarea desconocida")
    from app.worker import tasks

    getattr(tasks, name).delay()
    db.add(AuditLog(actor_id=admin.id, action="job.run", detail={"task": name}))
    db.commit()
    return {"queued": name}


@router.get("/audit")
def audit(limit: int = Query(100, le=500), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
    return [{"id": a.id, "actor_id": a.actor_id, "action": a.action, "detail": a.detail, "created_at": a.created_at}
            for a in rows]
