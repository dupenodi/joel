"""Resend HTTP adapter — https://resend.com/docs/api-reference/emails/send-email."""

from __future__ import annotations

import requests

from joel.mail.types import MailError, MailMessage, SendResult


class ResendMailer:
    def __init__(self, *, api_key: str, from_addr: str, from_name: str) -> None:
        self.api_key = api_key
        self.from_addr = from_addr
        self.from_name = from_name

    def send(self, message: MailMessage) -> SendResult:
        sender = (
            f"{self.from_name} <{self.from_addr}>"
            if self.from_name
            else self.from_addr
        )
        payload: dict[str, object] = {
            "from": sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
        }
        if message.html:
            payload["html"] = message.html
        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise MailError(str(exc) or "Resend request failed") from exc

        if response.status_code >= 400:
            detail = _resend_error(response)
            raise MailError(detail, status=response.status_code)

        data = response.json() if response.content else {}
        message_id = data.get("id") if isinstance(data, dict) else None
        return SendResult(
            provider="resend",
            message_id=str(message_id) if message_id else None,
        )


def _resend_error(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text.strip() or f"Resend HTTP {response.status_code}"
    if isinstance(data, dict):
        message = data.get("message") or data.get("error")
        if isinstance(message, dict):
            message = message.get("message") or message.get("name")
        if message:
            return str(message)
    return f"Resend HTTP {response.status_code}"
