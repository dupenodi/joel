"""Invite (and later transactional) email bodies — plain text + simple HTML."""

from __future__ import annotations

from joel.mail.types import MailMessage


def invite_email(
    *,
    to: str,
    workspace_name: str,
    role: str,
    join_url: str,
    expires_days: int,
) -> MailMessage:
    name = workspace_name.strip() or "joel"
    subject = f"You're invited to {name}"
    text = (
        f"You've been invited to join {name} on joel as {role}.\n\n"
        f"Open this link to create your account:\n{join_url}\n\n"
        f"This invite expires in {expires_days} days. "
        "If you weren't expecting this, you can ignore it.\n"
    )
    html = (
        f"<p>You've been invited to join <strong>{_escape(name)}</strong> "
        f"on joel as <strong>{_escape(role)}</strong>.</p>"
        f'<p><a href="{_escape(join_url)}">Accept invite</a></p>'
        f"<p style=\"color:#666;font-size:13px\">"
        f"Or paste this link: {_escape(join_url)}<br>"
        f"Expires in {expires_days} days.</p>"
    )
    return MailMessage(to=to, subject=subject, text=text, html=html)


def test_email(*, to: str) -> MailMessage:
    return MailMessage(
        to=to,
        subject="joel test email",
        text=(
            "This is a test from joel.\n\n"
            "If you received it, outbound email is configured correctly.\n"
        ),
        html=(
            "<p>This is a test from joel.</p>"
            "<p>If you received it, outbound email is configured correctly.</p>"
        ),
    )


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
