"""Ports the tools depend on, so adapters can be swapped without touching them."""

from __future__ import annotations

from typing import Protocol


class MailSender(Protocol):
    """Anything that can deliver a message."""

    def send(self, to: str, subject: str, body: str) -> None: ...


class RecordingMailSender:
    """Keeps messages in memory instead of sending them. Used by tests."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})
