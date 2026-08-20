"""Outbound email — optional, multi-provider.

Installs work without mail (invite links only). Admins pick one provider in
settings: none | smtp | resend. App code only calls `try_send` / templates.
"""

from __future__ import annotations

from joel.mail.factory import (
    PROVIDERS,
    from_settings,
    is_configured,
    provider_name,
    try_send,
)
from joel.mail.templates import invite_email, test_email
from joel.mail.types import MailError, MailMessage, SendResult

__all__ = [
    "PROVIDERS",
    "MailError",
    "MailMessage",
    "SendResult",
    "from_settings",
    "invite_email",
    "is_configured",
    "provider_name",
    "test_email",
    "try_send",
]
