"""SMTP adapter — universal fallback for corporate relays and API-provider SMTP."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from joel.mail.types import MailError, MailMessage, SendResult


class SmtpMailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        from_addr: str,
        from_name: str,
        use_tls: bool,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_addr = from_addr
        self.from_name = from_name
        self.use_tls = use_tls

    def send(self, message: MailMessage) -> SendResult:
        mail = EmailMessage()
        mail["From"] = (
            formataddr((self.from_name, self.from_addr))
            if self.from_name
            else self.from_addr
        )
        mail["To"] = message.to
        mail["Subject"] = message.subject
        mail.set_content(message.text)
        if message.html:
            mail.add_alternative(message.html, subtype="html")

        try:
            if self.port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    self.host, self.port, timeout=30, context=context
                ) as smtp:
                    if self.user:
                        smtp.login(self.user, self.password)
                    smtp.send_message(mail)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
                    if self.use_tls:
                        context = ssl.create_default_context()
                        smtp.starttls(context=context)
                    if self.user:
                        smtp.login(self.user, self.password)
                    smtp.send_message(mail)
        except smtplib.SMTPException as exc:
            raise MailError(str(exc) or "SMTP send failed") from exc
        except OSError as exc:
            raise MailError(str(exc) or "SMTP connection failed") from exc
        return SendResult(provider="smtp")
