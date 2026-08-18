"""Slack Web API fetcher.

Fetch and pagination stay separate from normalization: this module enriches
Slack payloads with channel/user/permalink context, then the shared SLACK
manifest turns them into CanonicalDoc objects.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator

import requests

from joel.adapters import SLACK, adapt_many
from joel.models import CanonicalDoc

SLACK_API = "https://slack.com/api"


class SlackAPIError(RuntimeError):
    def __init__(self, error: str, *, retryable: bool = False) -> None:
        super().__init__(f"Slack API error: {error}")
        self.error = error
        self.retryable = retryable


@dataclass
class SlackFetchResult:
    docs: list[CanonicalDoc]
    team_id: str | None
    team_name: str | None
    team_domain: str | None
    channel_count: int


class SlackClient:
    def __init__(
        self,
        token: str = "",
        *,
        session: requests.Session | None = None,
        timeout: float = 20,
        max_rate_limit_retries: int = 3,
        caller: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.token = token
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_rate_limit_retries = max_rate_limit_retries
        self.caller = caller

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        if self.caller is None and not self.token:
            raise SlackAPIError("invalid_auth")
        for attempt in range(self.max_rate_limit_retries + 1):
            if self.caller is not None:
                try:
                    data = self.caller(method, params)
                except Exception as exc:
                    error = str(exc)
                    retryable = "429" in error or "rate_limited" in error
                    if retryable and attempt < self.max_rate_limit_retries:
                        time.sleep(1 + attempt)
                        continue
                    raise SlackAPIError(error, retryable=retryable) from exc
            else:
                response = self.session.get(
                    f"{SLACK_API}/{method}",
                    params=params,
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    if attempt >= self.max_rate_limit_retries:
                        raise SlackAPIError("rate_limited", retryable=True)
                    retry_after = max(1, int(response.headers.get("Retry-After", "1")))
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict):
                raise SlackAPIError("malformed_response")
            if data.get("ok") is False:
                error = str(data.get("error", "unknown_error"))
                raise SlackAPIError(
                    error,
                    retryable=error
                    in {"ratelimited", "internal_error", "fatal_error", "request_timeout"},
                )
            return data
        raise SlackAPIError("rate_limited", retryable=True)

    def pages(
        self,
        method: str,
        item_key: str,
        *,
        limit: int = 200,
        **params: Any,
    ) -> Iterator[list[dict[str, Any]]]:
        cursor: str | None = None
        while True:
            page_params = dict(params)
            page_params["limit"] = limit
            if cursor:
                page_params["cursor"] = cursor
            data = self.call(method, **page_params)
            items = data.get(item_key) or []
            yield [item for item in items if isinstance(item, dict)]
            cursor = str(
                (data.get("response_metadata") or {}).get("next_cursor") or ""
            ).strip()
            if not cursor:
                return

    def user_handles(self) -> dict[str, str]:
        handles: dict[str, str] = {}
        for page in self.pages("users.list", "members"):
            for user in page:
                user_id = user.get("id")
                profile = user.get("profile") or {}
                handle = (
                    user.get("name")
                    or profile.get("display_name")
                    or profile.get("real_name")
                )
                if user_id and handle:
                    handles[str(user_id)] = f"@{str(handle).lstrip('@')}"
        return handles

    def channels(self, *, channel_ids: list[str] | None = None) -> list[dict[str, Any]]:
        listed: list[dict[str, Any]] = []
        for page in self.pages(
            "conversations.list",
            "channels",
            types="public_channel,private_channel",
            exclude_archived="true",
        ):
            listed.extend(page)
        # User tokens (Composio’s `slack` toolkit) can read public channels
        # without joining. Bot tokens can only read channels they’re in.
        if self.token.startswith("xoxb-"):
            listed = [c for c in listed if c.get("is_member") is True]
        if channel_ids:
            wanted = {cid for cid in channel_ids if cid}
            by_id = {str(c.get("id") or ""): c for c in listed}
            selected: list[dict[str, Any]] = []
            for cid in wanted:
                selected.append(by_id.get(cid) or {"id": cid, "name": cid})
            return selected
        return listed

    def messages(
        self,
        channel_id: str,
        *,
        oldest: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"channel": channel_id}
        if oldest:
            params["oldest"] = oldest
        messages: list[dict[str, Any]] = []
        for page in self.pages("conversations.history", "messages", **params):
            messages.extend(page)
        return messages

    def replies(self, channel_id: str, thread_ts: str) -> list[dict[str, Any]]:
        replies: list[dict[str, Any]] = []
        for page in self.pages(
            "conversations.replies",
            "messages",
            channel=channel_id,
            ts=thread_ts,
        ):
            replies.extend(page)
        return replies


def _mention_handles(text: str, users: dict[str, str]) -> list[str]:
    import re

    return [
        users.get(user_id, f"@{user_id}")
        for user_id in re.findall(r"<@(U[A-Z0-9]+)>", text)
    ]


def fetch_slack_docs(
    token: str = "",
    *,
    oldest: str | None = None,
    channel_ids: list[str] | None = None,
    session: requests.Session | None = None,
    caller: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> SlackFetchResult:
    client = SlackClient(token, session=session, caller=caller)
    auth = client.call("auth.test")
    users = client.user_handles()
    channels = client.channels(channel_ids=channel_ids)
    team_url = str(auth.get("url") or "").rstrip("/")
    team_domain = team_url.removeprefix("https://").removeprefix("http://").split(
        ".slack.com", 1
    )[0]

    raw_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    if not channels:
        raise SlackAPIError(
            "Pick at least one channel to ingest, then Sync now"
        )
    for channel in channels:
        channel_id = str(channel.get("id") or "")
        if not channel_id:
            continue
        channel_name = str(channel.get("name") or channel_id)
        try:
            roots = client.messages(channel_id, oldest=oldest)
        except SlackAPIError as exc:
            if exc.error in {"not_in_channel", "channel_not_found", "is_archived"}:
                continue
            raise
        for message in roots:
            ts = str(message.get("ts") or "")
            if not ts or message.get("subtype") in {
                "channel_join",
                "channel_leave",
                "channel_name",
                "channel_purpose",
                "channel_topic",
            }:
                continue
            candidates = [message]
            if int(message.get("reply_count") or 0) > 0:
                try:
                    candidates = client.replies(channel_id, ts)
                except SlackAPIError as exc:
                    if exc.error in {"not_in_channel", "thread_not_found"}:
                        continue
                    raise
            for item in candidates:
                item_ts = str(item.get("ts") or "")
                if not item_ts:
                    continue
                enriched = dict(item)
                enriched["channel"] = channel_name
                enriched["channel_id"] = channel_id
                enriched["team_domain"] = team_domain
                user_id = str(item.get("user") or "")
                enriched["author_handle"] = users.get(
                    user_id, f"@{user_id}" if user_id else None
                )
                enriched["mentions"] = _mention_handles(
                    str(item.get("text") or ""), users
                )
                enriched["permalink"] = (
                    f"{team_url}/archives/{channel_id}/p{item_ts.replace('.', '')}"
                    if team_url
                    else None
                )
                raw_by_key[(channel_id, item_ts)] = enriched

    docs = adapt_many(SLACK, raw_by_key.values())
    return SlackFetchResult(
        docs=docs,
        team_id=str(auth.get("team_id") or "") or None,
        team_name=str(auth.get("team") or "") or None,
        team_domain=team_domain or None,
        channel_count=len(channels),
    )


__all__ = [
    "SlackAPIError",
    "SlackClient",
    "SlackFetchResult",
    "fetch_slack_docs",
]
