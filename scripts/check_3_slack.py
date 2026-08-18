"""Slack connector contract checks without live OAuth or network access."""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from joel.connectors.oauth import (  # noqa: E402
    decrypt_credentials,
    encrypt_credentials,
)
from joel.connectors.slack import fetch_slack_docs  # noqa: E402
from joel.adapters import SLACK, adapt  # noqa: E402


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any],
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        del timeout
        assert headers["Authorization"] == "Bearer xoxb-test"
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, dict(params)))
        cursor = params.get("cursor")
        if method == "auth.test":
            return FakeResponse(
                {
                    "ok": True,
                    "team_id": "T1",
                    "team": "Acme",
                    "url": "https://acme.slack.com/",
                }
            )
        if method == "users.list":
            if not cursor:
                return FakeResponse(
                    {
                        "ok": True,
                        "members": [{"id": "U1", "name": "soham"}],
                        "response_metadata": {"next_cursor": "users-2"},
                    }
                )
            return FakeResponse(
                {
                    "ok": True,
                    "members": [{"id": "U2", "name": "alice"}],
                    "response_metadata": {"next_cursor": ""},
                }
            )
        if method == "conversations.list":
            return FakeResponse(
                {
                    "ok": True,
                    "channels": [
                        {"id": "C1", "name": "infra", "is_member": True},
                        {"id": "C9", "name": "random", "is_member": False},
                    ],
                    "response_metadata": {"next_cursor": ""},
                }
            )
        if method == "conversations.history":
            return FakeResponse(
                {
                    "ok": True,
                    "messages": [
                        {
                            "ts": "1700000000.000001",
                            "user": "U1",
                            "text": "Why does restore hang after loading the manifest?",
                            "reply_count": 2,
                        },
                        {
                            "ts": "1700000200.000001",
                            "user": "U2",
                            "text": "Standalone deployment update with enough useful detail to retain.",
                        },
                    ],
                    "response_metadata": {"next_cursor": ""},
                }
            )
        if method == "conversations.replies":
            root = "1700000000.000001"
            return FakeResponse(
                {
                    "ok": True,
                    "messages": [
                        {
                            "ts": root,
                            "user": "U1",
                            "text": "Why does restore hang after loading the manifest?",
                        },
                        {
                            "ts": "1700000001.000001",
                            "thread_ts": root,
                            "user": "U2",
                            "text": "Set CKPT_PREFETCH=4 and retry it <@U1>.",
                        },
                        {
                            "ts": "1700000002.000001",
                            "thread_ts": root,
                            "user": "U1",
                            "text": "Confirmed, that fixes the restore on the NFS mount.",
                        },
                    ],
                    "response_metadata": {"next_cursor": ""},
                }
            )
        raise AssertionError(f"unexpected Slack method {method}")


def check_fetch() -> None:
    session = FakeSession()
    result = fetch_slack_docs(
        "xoxb-test", oldest="1699990000", session=session  # type: ignore[arg-type]
    )
    assert result.team_domain == "acme"
    assert result.channel_count == 1
    assert not any(
        method == "conversations.history" and params.get("channel") == "C9"
        for method, params in session.calls
    )
    assert len(result.docs) == 4
    assert len({doc.doc_id for doc in result.docs}) == 4
    assert all(doc.url and "/archives/C1/" in doc.url for doc in result.docs)
    assert any(doc.author_raw == "@soham" for doc in result.docs)
    mention = next(doc for doc in result.docs if doc.participants_raw)
    assert mention.participants_raw == ["@soham"]
    thread = [
        doc for doc in result.docs if doc.thread_id == "C1:1700000000.000001"
    ]
    assert len(thread) == 3
    assert sum(doc.parent_id is not None for doc in thread) == 2
    assert sum(method == "users.list" for method, _ in session.calls) == 2
    same_ts_other_channel = adapt(
        SLACK,
        {
            "channel_id": "C2",
            "channel": "support",
            "ts": "1700000000.000001",
            "text": "Different channel message with the same Slack timestamp value.",
            "user": "U1",
        },
    )
    assert same_ts_other_channel is not None
    assert same_ts_other_channel.doc_id not in {doc.doc_id for doc in result.docs}
    print("ok  Slack pagination, enrichment, threads, and normalization")


def check_encryption() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        credentials = {
            "access_token": "xoxb-never-plaintext",
            "refresh_token": "xoxe-refresh",
        }
        encrypted = encrypt_credentials(credentials, data_dir)
        assert "xoxb-never-plaintext" not in encrypted
        assert decrypt_credentials(encrypted, data_dir) == credentials
        assert (data_dir / ".joel-secret").exists()
    print("ok  encrypted credential round-trip")


def check_bot_token_shape() -> None:
    import os

    os.environ["JOEL_DATA"] = tempfile.mkdtemp(prefix="joel-token-")
    import joel.app as appmod
    from fastapi import HTTPException
    from joel.connectors.gate import require_connectable

    appmod.init_db()
    appmod.create_org(appmod.OrgIn(domain="acme.dev"))
    try:
        appmod.create_connector(appmod.ConnectorIn(provider="github"))
        raise AssertionError("direct connector create must be rejected")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Composio" in str(exc.detail)
    try:
        require_connectable("salesforce")
        raise AssertionError("unknown tools must not be connectable")
    except ValueError as exc:
        assert "list" in str(exc).lower() or "Connectable" in str(exc)
    print("ok  composio-only connect gate")


def check_gmail_connect_skips_create() -> None:
    from joel.connectors.composio_conn import ComposioError, start_toolkit_connect

    class _Authorize:
        def authorize(self, user_id: str, toolkit: str) -> object:
            del user_id
            return type("R", (), {"redirect_url": f"https://accounts.google.com/{toolkit}"})()

    class _AuthConfigs:
        def list(self, limit: int = 100) -> list:
            del limit
            return []

    class Ok:
        created = False

        def __init__(self) -> None:
            self.auth_configs = _AuthConfigs()
            self.connected_accounts = type("C", (), {})()
            self.toolkits = _Authorize()

        def create(self, **kwargs: object) -> object:
            del kwargs
            self.created = True
            raise AssertionError("composio.create must not run for gmail")

    ok = Ok()
    url = start_toolkit_connect(ok, "gmail", "http://localhost:3001/api/composio/callback")
    assert url == "https://accounts.google.com/gmail"
    assert ok.created is False

    class Fail:
        created = False

        def __init__(self) -> None:
            self.auth_configs = _AuthConfigs()
            self.connected_accounts = type("C", (), {})()

            class Boom:
                def authorize(self, user_id: str, toolkit: str) -> object:
                    del user_id, toolkit
                    raise RuntimeError("managed authorize failed")

            self.toolkits = Boom()

        def create(self, **kwargs: object) -> object:
            del kwargs
            self.created = True
            raise AssertionError("composio.create must not run for gmail")

    fail = Fail()
    try:
        start_toolkit_connect(fail, "gmail", "http://localhost:3001/cb")
        raise AssertionError("expected ComposioError")
    except ComposioError as exc:
        assert "Google blocked" in str(exc) or "managed app" in str(exc)
    assert fail.created is False

    class PreferJoel:
        initiated: list[str] = []
        created = False

        def __init__(self) -> None:
            self.initiated = []
            self.auth_configs = self
            self.connected_accounts = self

            class Boom:
                def authorize(self, user_id: str, toolkit: str) -> object:
                    del user_id, toolkit
                    raise RuntimeError("should use joel readonly config")

            self.toolkits = Boom()

        def list(self, limit: int = 100) -> list:
            del limit
            return [
                {
                    "id": "ac_extra",
                    "toolkit": "gmail",
                    "status": "ENABLED",
                    "isComposioManaged": True,
                    "name": "Gmail",
                },
                {
                    "id": "ac_joel",
                    "toolkit": "gmail",
                    "status": "ENABLED",
                    "isComposioManaged": True,
                    "name": "Joel gmail readonly",
                },
            ]

        def link(self, user_id: str, auth_config_id: str, callback_url: str | None = None) -> object:
            del user_id, callback_url
            self.initiated.append(auth_config_id)
            return type("R", (), {"redirect_url": f"https://accounts.google.com/{auth_config_id}"})()

        def create(self, **kwargs: object) -> object:
            del kwargs
            self.created = True
            raise AssertionError("composio.create must not run for gmail")

    prefer = PreferJoel()
    url = start_toolkit_connect(prefer, "gmail", "http://localhost:3001/cb")
    assert url.endswith("ac_joel")
    assert prefer.initiated == ["ac_joel"]
    assert prefer.created is False

    class DriveOk:
        created = False

        def __init__(self) -> None:
            self.auth_configs = _AuthConfigs()
            self.connected_accounts = type("C", (), {})()
            self.toolkits = _Authorize()

        def create(self, **kwargs: object) -> object:
            del kwargs
            self.created = True
            raise AssertionError("composio.create must not run for googledrive")

    drive = DriveOk()
    drive_url = start_toolkit_connect(
        drive, "googledrive", "http://localhost:3001/cb"
    )
    assert drive_url == "https://accounts.google.com/googledrive"
    assert drive.created is False
    print("ok  gmail connect skips composio.create")


if __name__ == "__main__":
    check_fetch()
    check_encryption()
    check_bot_token_shape()
    check_gmail_connect_skips_create()
    print("\nSlack connector checks passed.")
