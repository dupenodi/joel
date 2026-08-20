"""Cloud vs self-host seam, Slack install kinds, OAuth bind, team_id routing."""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from joel.deployment import (  # noqa: E402
    deployment,
    host_is_hosted,
    slack_install,
)
from joel.slack_bot import authenticate_slack_request, verify_signature  # noqa: E402
from joel.slack_oauth import (  # noqa: E402
    BOT_SCOPES,
    SlackOAuthAccess,
    SlackOAuthError,
    authorize_url,
    parse_oauth_access,
    safe_return_path,
)


def _env(**kwargs: str) -> dict[str, str]:
    base = {
        "JOEL_WEB_ORIGIN": "http://localhost:3000",
        "JOEL_DEPLOYMENT": "",
        "SLACK_CLIENT_ID": "",
        "SLACK_CLIENT_SECRET": "",
        "SLACK_SIGNING_SECRET": "",
    }
    base.update(kwargs)
    return base


def check_host_is_hosted() -> None:
    assert host_is_hosted("meetjoel.xyz")
    assert host_is_hosted("app.meetjoel.xyz")
    assert host_is_hosted("www.meetjoel.xyz")
    assert host_is_hosted("staging.meetjoel.xyz")
    assert not host_is_hosted("localhost")
    assert not host_is_hosted("joel.example.com")
    assert not host_is_hosted("notmeetjoel.xyz")
    print("ok  deploy.1: meetjoel.xyz and subdomains are hosted; nothing else is")


def check_deployment_from_origin_and_override() -> None:
    with patch.dict(os.environ, _env(JOEL_WEB_ORIGIN="http://localhost:3000"), clear=False):
        assert deployment().mode == "selfhost"
        assert deployment().is_cloud is False
    with patch.dict(
        os.environ, _env(JOEL_WEB_ORIGIN="https://meetjoel.xyz"), clear=False
    ):
        assert deployment().mode == "cloud"
        assert deployment().is_cloud is True
    with patch.dict(
        os.environ,
        _env(JOEL_WEB_ORIGIN="https://app.meetjoel.xyz", JOEL_DEPLOYMENT="selfhost"),
        clear=False,
    ):
        assert deployment().mode == "selfhost", "explicit JOEL_DEPLOYMENT wins over origin"
    with patch.dict(
        os.environ,
        _env(JOEL_WEB_ORIGIN="http://localhost:3000", JOEL_DEPLOYMENT="cloud"),
        clear=False,
    ):
        assert deployment().mode == "cloud", "explicit cloud for local testing"
    print("ok  deploy.2: origin detects cloud; JOEL_DEPLOYMENT overrides")


def check_slack_install_kinds() -> None:
    with patch.dict(os.environ, _env(), clear=False):
        assert slack_install() == "manifest"
    with patch.dict(
        os.environ,
        _env(
            JOEL_DEPLOYMENT="cloud",
            SLACK_CLIENT_ID="",
            SLACK_CLIENT_SECRET="",
            SLACK_SIGNING_SECRET="",
        ),
        clear=False,
    ):
        assert slack_install() == "unavailable"
    creds = _env(
        JOEL_DEPLOYMENT="selfhost",
        SLACK_CLIENT_ID="cid",
        SLACK_CLIENT_SECRET="csecret",
        SLACK_SIGNING_SECRET="sign",
    )
    with patch.dict(os.environ, creds, clear=False):
        assert slack_install() == "oauth"
    print("ok  deploy.3: slack_install is manifest / unavailable / oauth")


def check_authorize_url_and_return_path() -> None:
    url = authorize_url(
        client_id="CID",
        redirect_uri="https://meetjoel.xyz/api/slack/oauth/callback",
        state="st",
    )
    assert url.startswith("https://slack.com/oauth/v2/authorize?")
    assert "client_id=CID" in url
    assert "scope=" in url and "app_mentions%3Aread" in url or "app_mentions:read" in url
    assert BOT_SCOPES.split(",")[0] == "app_mentions:read"
    assert safe_return_path("/settings/slack") == "/settings/slack"
    assert safe_return_path("/onboarding/slack") == "/onboarding/slack"
    assert safe_return_path("https://evil.test/phish") == "/settings/slack"
    assert safe_return_path("//evil.test") == "/settings/slack"
    assert safe_return_path("/chat") == "/settings/slack"
    print("ok  deploy.4: authorize URL and return_to allowlist")


def check_parse_oauth_access() -> None:
    parsed = parse_oauth_access(
        {
            "ok": True,
            "access_token": "xoxb-real-token",
            "bot_user_id": "UBOT",
            "team": {"id": "T9TEAM", "name": "Acme"},
        }
    )
    assert parsed.bot_token == "xoxb-real-token"
    assert parsed.team_id == "T9TEAM"
    assert parsed.team_name == "Acme"
    try:
        parse_oauth_access({"ok": False, "error": "invalid_code"})
        raise AssertionError("expected SlackOAuthError")
    except SlackOAuthError as exc:
        assert exc.code == "invalid_code"
    try:
        parse_oauth_access({"ok": True, "access_token": "not-a-bot", "team": {"id": "T1"}})
        raise AssertionError("expected SlackOAuthError")
    except SlackOAuthError as exc:
        assert exc.code == "malformed_access"
    print("ok  deploy.5: oauth.v2.access parse keeps bot token + team id, rejects junk")


def check_authenticate_prefers_env_then_org() -> None:
    body = b'{"type":"event_callback","team_id":"T1"}'
    ts = str(int(time.time()))

    def sig(secret: str) -> str:
        base = f"v0:{ts}:".encode() + body
        return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()

    ok, org_id = authenticate_slack_request(
        timestamp=ts,
        body=body,
        signature=sig("env-secret"),
        env_signing_secret="env-secret",
        org_signing_secrets=[(2, "org-secret")],
    )
    assert ok is True and org_id is None

    ok, org_id = authenticate_slack_request(
        timestamp=ts,
        body=body,
        signature=sig("org-secret"),
        env_signing_secret="env-secret",
        org_signing_secrets=[(7, "org-secret")],
    )
    assert ok is True and org_id == 7

    ok, org_id = authenticate_slack_request(
        timestamp=ts,
        body=body,
        signature=sig("wrong"),
        env_signing_secret="env-secret",
        org_signing_secrets=[(7, "org-secret")],
    )
    assert ok is False and org_id is None
    assert verify_signature(
        signing_secret="env-secret", timestamp=ts, body=body, signature=sig("env-secret")
    )
    print("ok  deploy.6: env signing secret wins; else org pasted secret")


def check_bind_slack_workspace_and_team_lookup() -> None:
    import joel.app as app
    from joel import identity

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app.DATA_DIR = tmp
        app.DB_PATH = tmp / "index" / "joel.db"
        app.init_db()
        with app.db() as conn:
            actor, _ = identity.setup(
                conn,
                email="ada@acme.dev",
                password="secretsecret",
                display_name="Ada",
                domain="acme.dev",
            )
            app.seed_org_defaults(conn, actor.org_id)
            other_id, _ = identity.create_workspace(
                conn, actor.user_id, name="Other", domain="other.dev"
            )
            access = SlackOAuthAccess(
                bot_token="xoxb-from-oauth",
                team_id="TTEAM1",
                team_name="Acme Slack",
                bot_user_id="UBOT",
            )
            app._bind_slack_workspace(conn, actor.org_id, access)
            assert app._org_id_for_slack_team(conn, "TTEAM1") == actor.org_id
            token = conn.execute(
                "SELECT value FROM settings WHERE org_id=? AND key='slack_bot_token'",
                (actor.org_id,),
            ).fetchone()["value"]
            assert token == "xoxb-from-oauth"
            try:
                app._bind_slack_workspace(conn, other_id, access)
                raise AssertionError("same Slack team must not bind to a second org")
            except SlackOAuthError as exc:
                assert exc.code == "already_linked"
            app._clear_slack_install(conn, actor.org_id)
            assert app._org_id_for_slack_team(conn, "TTEAM1") is None
            cleared = conn.execute(
                "SELECT value FROM settings WHERE org_id=? AND key='slack_bot_token'",
                (actor.org_id,),
            ).fetchone()["value"]
            assert cleared == ""
    print("ok  deploy.7: team_id binds one org; disconnect clears it")


def check_slack_connected_and_put_skips_oauth_secrets() -> None:
    import joel.app as app
    from joel import identity
    from types import SimpleNamespace

    assert app._slack_connected(
        install="oauth", token_set=True, secret_set=False, team_id="T1"
    )
    assert not app._slack_connected(
        install="oauth", token_set=True, secret_set=True, team_id=""
    )
    assert app._slack_connected(
        install="manifest", token_set=True, secret_set=True, team_id=""
    )
    assert not app._slack_connected(
        install="unavailable", token_set=True, secret_set=True, team_id="T1"
    )

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app.DATA_DIR = tmp
        app.DB_PATH = tmp / "index" / "joel.db"
        app.init_db()
        with app.db() as conn:
            actor, _ = identity.setup(
                conn,
                email="ada@acme.dev",
                password="secretsecret",
                display_name="Ada",
                domain="acme.dev",
            )
            app.seed_org_defaults(conn, actor.org_id)

        request = SimpleNamespace(state=SimpleNamespace(actor=actor))
        creds = _env(
            JOEL_DEPLOYMENT="cloud",
            SLACK_CLIENT_ID="cid",
            SLACK_CLIENT_SECRET="csecret",
            SLACK_SIGNING_SECRET="sign",
        )
        with patch.dict(os.environ, creds, clear=False):
            app.put_settings(
                app.SettingsIn(
                    values={
                        "slack_bot_token": "xoxb-forged",
                        "slack_signing_secret": "forged-secret",
                        "voice": "Direct",
                    }
                ),
                request,  # type: ignore[arg-type]
            )
        with app.db() as conn:
            settings = app._settings_map(conn, actor.org_id)
            assert settings.get("slack_bot_token") == ""
            assert settings.get("slack_signing_secret") == ""
            assert settings.get("voice") == "Direct"
    print("ok  deploy.8: oauth install ignores pasted Slack secrets; voice still saves")


def main() -> None:
    check_host_is_hosted()
    check_deployment_from_origin_and_override()
    check_slack_install_kinds()
    check_authorize_url_and_return_path()
    check_parse_oauth_access()
    check_authenticate_prefers_env_then_org()
    check_bind_slack_workspace_and_team_lookup()
    check_slack_connected_and_put_skips_oauth_secrets()
    print("\nDeployment / Slack install: all automated checks passed.")


if __name__ == "__main__":
    main()
