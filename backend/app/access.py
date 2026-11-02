"""Acceso por tiempo limitado: el administrador concede periodos (p. ej. 30 días) tras recibir el pago."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AccessGrant, Role, User, UserNotification


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def has_access(user: User, now: datetime | None = None) -> bool:
    if user.role == Role.admin or not get_settings().require_access_grant:
        return True
    exp = _aware(user.access_expires_at)
    return exp is not None and exp > (now or datetime.now(UTC))


def grant(db: Session, user: User, days: int, admin: User | None, amount: float | None = None,
          currency: str = "USD", note: str = "") -> AccessGrant:
    """Suma `days` al acceso. Si el acceso sigue vigente, se encadena a partir de su vencimiento."""
    now = datetime.now(UTC)
    current = _aware(user.access_expires_at)
    start = current if current and current > now else now
    end = start + timedelta(days=days)
    g = AccessGrant(user_id=user.id, granted_by=admin.id if admin else None, days=days, starts_at=start, ends_at=end,
                    amount=amount, currency=currency, note=note)
    user.access_expires_at = end
    if user.plan_code == "free":
        user.plan_code = "pro"  # quien alquila el acceso tiene el análisis completo
    db.add(g)
    return g


def revoke(db: Session, user: User) -> None:
    user.access_expires_at = datetime.now(UTC)
    for g in db.scalars(select(AccessGrant).where(AccessGrant.user_id == user.id,
                                                  AccessGrant.ends_at > datetime.now(UTC))).all():
        g.revoked = True
    user.token_version += 1


def send_expiry_reminders(db: Session, now: datetime | None = None) -> int:
    """Aviso en el centro de notificaciones N días antes de vencer (una vez por periodo)."""
    now = now or datetime.now(UTC)
    days = get_settings().access_reminder_days
    users = db.scalars(select(User).where(User.access_expires_at.is_not(None), User.is_active.is_(True),
                                          User.role != Role.admin)).all()
    n = 0
    contact = get_settings().admin_contact
    for u in users:
        exp = _aware(u.access_expires_at)
        if not (now < exp <= now + timedelta(days=days)):
            continue
        key = f"access_expiring:{exp.date().isoformat()}"
        if db.scalar(select(UserNotification.id).where(UserNotification.user_id == u.id,
                                                       UserNotification.dedup_key == key)):
            continue
        left = max(1, round((exp - now).total_seconds() / 86400))
        body = f"Tu acceso vence el {exp.strftime('%d/%m/%Y')}."
        if contact:
            body += f" Para renovarlo: {contact}"
        db.add(UserNotification(user_id=u.id, kind="access_expiring", title=f"⏳ Tu acceso vence en {left} días",
                                body=body, data={"url": "/profile"}, dedup_key=key))
        n += 1
    db.commit()
    return n
