"""Build a mailer from the install's settings kv — same pattern as LLM keys."""

from __future__ import annotations

from typing import Protocol

from joel.mail.resend import ResendMailer
from joel.mail.smtp import SmtpMailer
from joel.mail.types import MailError, MailMessage, SendResult

PROVIDERS = frozenset({"none", "smtp", "resend"})


class Mailer(Protocol):
    def send(self, message: MailMessage) -> SendResult: ...


def provider_name(settings: dict[str, str]) -> str:
    raw = (settings.get("mail_provider") or "none").strip().lower()
    return raw if raw in PROVIDERS else "none"


def is_configured(settings: dict[str, str]) -> bool:
    """True only when a provider is selected *and* required fields are present."""
    provider = provider_name(settings)
    if provider == "none":
        return False
    if not (settings.get("mail_from") or "").strip():
        return False
    if provider == "smtp":
        return bool((settings.get("mail_smtp_host") or "").strip())
    if provider == "resend":
        return bool((settings.get("mail_resend_api_key") or "").strip())
    return False


def from_settings(settings: dict[str, str]) -> Mailer:
    """Raise MailError if the chosen provider is missing required fields."""
    provider = provider_name(settings)
    from_addr = (settings.get("mail_from") or "").strip()
    from_name = (settings.get("mail_from_name") or "joel").strip()

    if provider == "none":
        raise MailError("Email is not configured")

    if not from_addr:
        raise MailError("Set a From address in Email settings")

    if provider == "smtp":
        host = (settings.get("mail_smtp_host") or "").strip()
        if not host:
            raise MailError("Set an SMTP host")
        port_raw = (settings.get("mail_smtp_port") or "587").strip() or "587"
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise MailError("SMTP port must be a number") from exc
        tls = (settings.get("mail_smtp_tls") or "true").strip().lower() not in {
            "0",
            "false",
            "no",
        }
        return SmtpMailer(
            host=host,
            port=port,
            user=(settings.get("mail_smtp_user") or "").strip(),
            password=settings.get("mail_smtp_password") or "",
            from_addr=from_addr,
            from_name=from_name,
            use_tls=tls,
        )

    if provider == "resend":
        api_key = (settings.get("mail_resend_api_key") or "").strip()
        if not api_key:
            raise MailError("Set a Resend API key")
        return ResendMailer(
            api_key=api_key, from_addr=from_addr, from_name=from_name
        )

    raise MailError(f"Unknown email provider: {provider}")


def try_send(settings: dict[str, str], message: MailMessage) -> SendResult | None:
    """Send when configured; return None when provider is none.

    Raises MailError on misconfiguration or provider failure.
    """
    if not is_configured(settings):
        return None
    return from_settings(settings).send(message)
