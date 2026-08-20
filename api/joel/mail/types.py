"""Shared mail types — one message shape for every provider adapter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None


@dataclass(frozen=True)
class SendResult:
    provider: str
    message_id: str | None = None


class MailError(Exception):
    """Provider refused or could not deliver the message."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status
