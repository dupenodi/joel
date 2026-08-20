"""§13's Slack bot surface (the last cuttable item on §17's list -- "web
desk must keep working" is the only hard requirement, and it does). An
`app_mention` in a channel gets answered in-thread, using the exact same
`answer_question` pipeline every other surface uses. `AskContext` is
built server-side from the mentioning Slack user's own identity, matched
to a workspace Actor by email -- the identical signal channel membership
and Gmail visibility already use -- never from anything in the event
payload itself. An unrecognized Slack user gets silence, never an
org-wide answer.

Slack's Events API needs a response within 3 seconds or it retries the
same delivery; `app.py`'s route handler returns immediately and does the
real work (which involves real LLM calls, seconds not milliseconds) on a
background thread, deduping repeat deliveries by `event_id` so a slow
first response can't produce two replies.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any, Callable

import requests

SIGNATURE_MAX_AGE_SECONDS = 60 * 5  # Slack's own documented replay window
SLACK_API = "https://slack.com/api"
_MENTION_RE = re.compile(r"^\s*<@([A-Z0-9]+)>\s*")


def verify_signature(
    *, signing_secret: str, timestamp: str, body: bytes, signature: str, now: float | None = None
) -> bool:
    """Slack's documented v0 scheme: HMAC-SHA256(secret, "v0:{ts}:{body}"),
    compared with constant-time equality. A timestamp more than 5 minutes
    from now is rejected even with a valid signature -- replay protection,
    exactly as Slack's own docs specify."""
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        ts = float(timestamp)
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - ts) > SIGNATURE_MAX_AGE_SECONDS:
        return False
    base = f"v0:{timestamp}:".encode() + body
    computed = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


def authenticate_slack_request(
    *,
    timestamp: str,
    body: bytes,
    signature: str,
    env_signing_secret: str = "",
    org_signing_secrets: Sequence[tuple[int, str]] = (),
) -> tuple[bool, int | None]:
    """HMAC check for an Events API delivery.

    If the install-wide env secret verifies, `org_id` is None — the caller
    maps Slack `team_id` to an org. If an org's pasted secret verifies,
    that org_id is returned (self-host manifest install).
    """
    env = (env_signing_secret or "").strip()
    if env and verify_signature(
        signing_secret=env, timestamp=timestamp, body=body, signature=signature
    ):
        return True, None
    for org_id, secret in org_signing_secrets:
        if verify_signature(
            signing_secret=secret, timestamp=timestamp, body=body, signature=signature
        ):
            return True, org_id
    return False, None


@dataclass(frozen=True)
class MentionEvent:
    event_id: str
    channel: str
    user: str
    text: str
    ts: str
    thread_ts: str | None


def strip_mention(text: str, bot_user_id: str) -> str:
    """`<@BOTID> what's the refund policy?` -> `what's the refund policy?`.
    Only strips a LEADING mention of the bot itself -- a mention of
    someone else earlier in the text is real question content, not
    boilerplate to discard."""
    match = _MENTION_RE.match(text)
    if match and match.group(1) == bot_user_id:
        return text[match.end():].strip()
    return text.strip()


def parse_app_mention(payload: dict[str, Any]) -> MentionEvent | None:
    """Returns None for anything that isn't a real, well-formed
    `app_mention` -- callers treat that as "nothing to do," never a
    crash. Bot-authored events (edits, deletes, and joel's own replies)
    are filtered by the absence of a real `user` field, same signal
    Slack's own docs recommend."""
    if payload.get("type") != "event_callback":
        return None
    event = payload.get("event")
    if not isinstance(event, dict) or event.get("type") != "app_mention":
        return None
    user = event.get("user")
    channel = event.get("channel")
    ts = event.get("ts")
    event_id = payload.get("event_id")
    if not (isinstance(user, str) and isinstance(channel, str) and isinstance(ts, str) and isinstance(event_id, str)):
        return None
    text = str(event.get("text") or "")
    thread_ts = event.get("thread_ts")
    return MentionEvent(
        event_id=event_id,
        channel=channel,
        user=user,
        text=text,
        ts=ts,
        thread_ts=thread_ts if isinstance(thread_ts, str) else None,
    )


class SeenEvents:
    """§13.2's live-lookup dedupe pattern, reapplied here: Slack retries
    an Events API delivery that didn't get a fast-enough 200, so the same
    event_id can arrive more than once. A small bounded in-memory set is
    enough for one self-hosted process -- no cross-restart durability
    needed, since a restart also means any in-flight retry starts fresh."""

    def __init__(self, max_size: int = 2000) -> None:
        self._seen: dict[str, float] = {}
        self._max_size = max_size

    def already_seen(self, event_id: str) -> bool:
        if event_id in self._seen:
            return True
        if len(self._seen) >= self._max_size:
            oldest = min(self._seen, key=lambda k: self._seen[k])
            del self._seen[oldest]
        self._seen[event_id] = time.time()
        return False


SlackCaller = Callable[[str, dict[str, Any]], dict[str, Any]]


def web_api_caller(
    token: str,
    *,
    http_post: Callable[..., Any] | None = None,
) -> SlackCaller:
    """Direct Slack Web API caller for the *bot* token in Settings.

    Ingest still goes through Composio. Mentions need `chat.postMessage`,
    which the token Web API accepts as JSON POST. `http_post` is a test
    seam (same shape as `requests.post`).
    """
    post = http_post or requests.post

    def call(method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = post(
            f"{SLACK_API}/{method}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=params,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return {"ok": False, "error": "malformed_response"}
        return data

    return call


def email_for_slack_user(caller: SlackCaller, slack_user_id: str) -> str | None:
    """Look up one Slack member's email via `users.info` (needs
    `users:read.email`). Missing/ok=false/no email → None, never a guess."""
    data = caller("users.info", {"user": slack_user_id})
    if not isinstance(data, dict) or data.get("ok") is False:
        return None
    user = data.get("user")
    if not isinstance(user, dict):
        return None
    profile = user.get("profile")
    if not isinstance(profile, dict):
        return None
    email = str(profile.get("email") or "").strip().lower()
    return email or None


def post_reply(caller: SlackCaller, *, channel: str, thread_ts: str, text: str) -> None:
    caller("chat.postMessage", {"channel": channel, "thread_ts": thread_ts, "text": text})


__all__ = [
    "SIGNATURE_MAX_AGE_SECONDS",
    "SLACK_API",
    "MentionEvent",
    "SeenEvents",
    "authenticate_slack_request",
    "email_for_slack_user",
    "parse_app_mention",
    "post_reply",
    "strip_mention",
    "verify_signature",
    "web_api_caller",
]
