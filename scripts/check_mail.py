"""Outbound mail adapters — none / smtp / resend, plus invite template."""

from __future__ import annotations

import smtplib
import sys
import tempfile
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import joel.app as app  # noqa: E402
from joel import identity, mail  # noqa: E402
from joel.mail.types import MailError  # noqa: E402


def expect(exc_type, fn):
    try:
        fn()
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__}")


def main() -> None:
    # Factory: none is not configured
    assert mail.provider_name({}) == "none"
    assert not mail.is_configured({})
    assert not mail.is_configured({"mail_provider": "resend"})  # missing from + key
    assert not mail.is_configured(
        {"mail_provider": "resend", "mail_from": "joel@yourco.dev"}
    )
    assert mail.is_configured(
        {
            "mail_provider": "resend",
            "mail_from": "joel@yourco.dev",
            "mail_resend_api_key": "re_test",
        }
    )
    assert mail.try_send({}, mail.test_email(to="a@b.co")) is None
    expect(MailError, lambda: mail.from_settings({"mail_provider": "none"}))

    # Resend missing key
    bad = expect(
        MailError,
        lambda: mail.from_settings(
            {
                "mail_provider": "resend",
                "mail_from": "joel@yourco.dev",
                "mail_resend_api_key": "",
            }
        ),
    )
    assert "key" in str(bad).lower()

    # Resend happy path (mocked HTTP)
    with patch("joel.mail.resend.requests.post") as post:
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"id":"msg_1"}'
        response.json.return_value = {"id": "msg_1"}
        post.return_value = response
        result = mail.try_send(
            {
                "mail_provider": "resend",
                "mail_from": "joel@yourco.dev",
                "mail_from_name": "joel",
                "mail_resend_api_key": "re_test",
            },
            mail.test_email(to="sam@yourco.dev"),
        )
        assert result is not None
        assert result.provider == "resend"
        assert result.message_id == "msg_1"
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer re_test"

    # SMTP happy path (mocked)
    with patch("joel.mail.smtp.smtplib.SMTP") as smtp_cls:
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.__exit__.return_value = False
        smtp_cls.return_value = smtp
        result = mail.try_send(
            {
                "mail_provider": "smtp",
                "mail_from": "joel@yourco.dev",
                "mail_from_name": "joel",
                "mail_smtp_host": "localhost",
                "mail_smtp_port": "587",
                "mail_smtp_user": "u",
                "mail_smtp_password": "p",
                "mail_smtp_tls": "true",
            },
            mail.invite_email(
                to="sam@yourco.dev",
                workspace_name="Yourco",
                role="member",
                join_url="http://localhost:3001/join?token=abc",
                expires_days=14,
            ),
        )
        assert result is not None and result.provider == "smtp"
        smtp.starttls.assert_called()
        smtp.login.assert_called_with("u", "p")
        smtp.send_message.assert_called()
        sent: EmailMessage = smtp.send_message.call_args.args[0]
        assert "Yourco" in sent.as_string()
        assert sent["Subject"] and "Yourco" in sent["Subject"]

    # SMTP failure surfaces as MailError
    with patch("joel.mail.smtp.smtplib.SMTP") as smtp_cls:
        smtp_cls.side_effect = smtplib.SMTPConnectError(421, b"down")
        expect(
            MailError,
            lambda: mail.try_send(
                {
                    "mail_provider": "smtp",
                    "mail_from": "joel@yourco.dev",
                    "mail_smtp_host": "localhost",
                    "mail_smtp_port": "587",
                    "mail_smtp_tls": "false",
                },
                mail.test_email(to="a@b.co"),
            ),
        )

    # Invite creation still works; email_sent false when mail is none
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app.DATA_DIR = tmp
        app.DB_PATH = tmp / "index" / "joel.db"
        app.init_db()
        with app.db() as conn:
            actor, _sid = identity.setup(
                conn,
                email="ada@yourco.dev",
                password="secretsecret",
                display_name="Ada",
                domain="yourco.dev",
            )
            settings = app._settings_map(conn)
            assert settings.get("mail_provider") == "none"
            invite_id, token = identity.create_invite(
                conn, actor, email="sam@yourco.dev"
            )
            sent, err = app._send_invite_email(
                settings,
                email="sam@yourco.dev",
                role="member",
                token=token,
                workspace_name="Yourco",
                app_url="http://localhost:3001",
            )
            assert sent is False and err is None and invite_id

            conn.execute(
                "UPDATE settings SET value=? WHERE key=?",
                ("resend", "mail_provider"),
            )
            conn.execute(
                "UPDATE settings SET value=? WHERE key=?",
                ("joel@yourco.dev", "mail_from"),
            )
            conn.execute(
                "UPDATE settings SET value=? WHERE key=?",
                ("re_test", "mail_resend_api_key"),
            )
            settings = app._settings_map(conn)

        with patch("joel.mail.resend.requests.post") as post:
            response = MagicMock()
            response.status_code = 200
            response.content = b'{"id":"x"}'
            response.json.return_value = {"id": "x"}
            post.return_value = response
            sent, err = app._send_invite_email(
                settings,
                email="sam@yourco.dev",
                role="member",
                token=token,
                workspace_name="Yourco",
                app_url="http://localhost:3001",
            )
            assert sent is True and err is None
            body = post.call_args.kwargs["json"]
            assert "join?token=" in body["text"]

    print("ok  mail: none/smtp/resend adapters, invite send path")


if __name__ == "__main__":
    main()
