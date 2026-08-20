"""Add to Slack — oauth.v2 for the install-wide Slack app.

Used when `slack_install() == "oauth"` (hosted meetjoel, or a self-host
that put Slack app credentials in env). Token storage and org binding
stay in the app layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

import requests

from joel.slack_bot import SLACK_API

BOT_SCOPES = "app_mentions:read,chat:write,users:read,users:read.email"
OAUTH_PROVIDER = "slack_bot"
STATE_TTL_SECONDS = 10 * 60


class SlackOAuthError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SlackOAuthAccess:
    bot_token: str
    team_id: str
    team_name: str
    bot_user_id: str


def safe_return_path(value: str | None) -> str:
    """Only Settings or onboarding Slack steps. No open redirects."""
    raw = (value or "").strip() or "/settings/slack"
    if not raw.startswith("/") or raw.startswith("//") or "://" in raw:
        return "/settings/slack"
    path = raw.split("?", 1)[0]
    if path == "/settings/slack":
        return path
    if path == "/onboarding/slack":
        return path
    return "/settings/slack"


def authorize_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "scope": BOT_SCOPES,
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"https://slack.com/oauth/v2/authorize?{query}"


def parse_oauth_access(data: dict[str, Any]) -> SlackOAuthAccess:
    if data.get("ok") is not True:
        raise SlackOAuthError(str(data.get("error") or "oauth_failed"))
    token = str(data.get("access_token") or "").strip()
    team = data.get("team") if isinstance(data.get("team"), dict) else {}
    team_id = str(team.get("id") or "").strip()
    if not token.startswith("xoxb-") or not team_id:
        raise SlackOAuthError("malformed_access")
    return SlackOAuthAccess(
        bot_token=token,
        team_id=team_id,
        team_name=str(team.get("name") or ""),
        bot_user_id=str(data.get("bot_user_id") or ""),
    )


def exchange_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    http_post: Callable[..., Any] | None = None,
) -> SlackOAuthAccess:
    post = http_post or requests.post
    response = post(
        f"{SLACK_API}/oauth.v2.access",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise SlackOAuthError("malformed_access")
    return parse_oauth_access(payload)


__all__ = [
    "BOT_SCOPES",
    "OAUTH_PROVIDER",
    "STATE_TTL_SECONDS",
    "SlackOAuthAccess",
    "SlackOAuthError",
    "authorize_url",
    "exchange_code",
    "parse_oauth_access",
    "safe_return_path",
]
