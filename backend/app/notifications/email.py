"""Envío de correo (SMTP). Sin SMTP configurado se registra en el log (solo desarrollo)."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger(__name__)
OUTBOX: list[EmailMessage] = []  # usado por los tests


def send_email(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if s.environment == "test":
        OUTBOX.append(msg)
        return True
    if not s.smtp_host:
        log.warning("SMTP no configurado; correo a %s no enviado (asunto: %s)", to, subject)
        return False
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        log.error("Fallo enviando correo: %s", exc)
        return False
