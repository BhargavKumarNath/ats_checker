"""Report-link delivery. SMTP when configured, a log line otherwise."""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from atsc.config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Outgoing:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    def send(self, message: Outgoing) -> None: ...


class LogSender:
    """Development default: never sends, logs the link instead."""

    def send(self, message: Outgoing) -> None:
        log.info("email to %s: %s\n%s", message.to, message.subject, message.body)


class RecordingSender:
    """Keeps every message in memory; used by tests and local dry runs."""

    def __init__(self) -> None:
        self.sent: list[Outgoing] = []

    def send(self, message: Outgoing) -> None:
        self.sent.append(message)


class SmtpSender:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def send(self, message: Outgoing) -> None:
        msg = EmailMessage()
        msg["From"] = self._s.email_from
        msg["To"] = message.to
        msg["Subject"] = message.subject
        msg.set_content(message.body)
        with smtplib.SMTP(self._s.smtp_host, self._s.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if self._s.smtp_user:
                smtp.login(self._s.smtp_user, self._s.smtp_password)
            smtp.send_message(msg)


def sender_from_settings(settings: Settings) -> EmailSender:
    return SmtpSender(settings) if settings.smtp_host else LogSender()


def report_ready_message(to: str, url: str) -> Outgoing:
    return Outgoing(
        to=to,
        subject="Your detailed resume report is ready",
        body=(
            "Your detailed report is ready.\n\n"
            f"{url}\n\n"
            "The link is private to you; anyone with it can read the report. "
            "Nothing else was sent or stored beyond what the report shows.\n"
        ),
    )
