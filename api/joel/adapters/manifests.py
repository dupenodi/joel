"""Declarative manifests for each shipping provider (§6.0).

A new connector should almost always mean a new entry here plus fetch/auth —
not a new adapter module. Provider-specific code stays in `pre` hooks.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from joel.adapters.base import SourceManifest

_SLACK_USER = re.compile(r"<@(U[A-Z0-9]+)>")
_SLACK_CHANNEL = re.compile(r"<#(C[A-Z0-9]+)(?:\|[^>]*)?>")
_SLACK_LINK = re.compile(r"<(https?://[^|>]+)(?:\|([^>]*))?>")
_SLACK_BOLD = re.compile(r"\*([^*]+)\*")
_SLACK_ITALIC = re.compile(r"(?<!\w)_([^_]+)_(?!\w)")
_SLACK_STRIKE = re.compile(r"~([^~]+)~")
_SLACK_CODE = re.compile(r"`([^`]+)`")


def strip_slack_markup(raw: dict[str, Any]) -> dict[str, Any]:
    """Decode Slack mrkdwn enough for hashing/search; keep @U… mention ids."""
    text = raw.get("text")
    if not isinstance(text, str) or not text:
        return raw
    cleaned = text
    cleaned = _SLACK_USER.sub(r"@\1", cleaned)
    cleaned = _SLACK_CHANNEL.sub(r"#\1", cleaned)
    cleaned = _SLACK_LINK.sub(
        lambda m: m.group(2) or m.group(1), cleaned
    )
    cleaned = _SLACK_BOLD.sub(r"\1", cleaned)
    cleaned = _SLACK_ITALIC.sub(r"\1", cleaned)
    cleaned = _SLACK_STRIKE.sub(r"\1", cleaned)
    cleaned = _SLACK_CODE.sub(r"\1", cleaned)
    out = dict(raw)
    out["text"] = cleaned
    # Surface mention handles for participants_raw without normalizing names.
    if "mentions" not in out:
        out["mentions"] = [f"@{m}" for m in _SLACK_USER.findall(text)]
    return out


def slack_permalink(raw: Mapping[str, Any]) -> str | None:
    permalink = raw.get("permalink")
    if isinstance(permalink, str) and permalink:
        return permalink
    team = raw.get("team_domain") or raw.get("team")
    channel = raw.get("channel")
    ts = raw.get("ts")
    if team and channel and ts:
        return f"https://{team}.slack.com/archives/{channel}/p{str(ts).replace('.', '')}"
    return None


SLACK = SourceManifest(
    provider="slack",
    archetype="conversation",
    external_id="ts",
    body="text",
    author="user",
    container="channel",
    timestamp=("ts", "epoch"),
    thread=("thread_ts", "ts"),
    parent_if_differs=("thread_ts", "ts"),
    url=slack_permalink,
    extra=("reactions", "files"),
    participants="mentions",
    pre=(strip_slack_markup,),
)

GITHUB_ISSUE = SourceManifest(
    provider="github",
    archetype="tracker",
    external_id="number",
    body="body",
    title="title",
    author="user.login",
    container="repository.full_name",
    timestamp=("created_at", "iso"),
    thread=("number", "number"),
    url="html_url",
    extra=("state", "labels", "assignees"),
    id_prefix="issue_",
    thread_prefix="issue_",
)

GITHUB_PR = SourceManifest(
    provider="github",
    archetype="tracker",
    external_id="number",
    body="body",
    title="title",
    author="user.login",
    container="repository.full_name",
    timestamp=("created_at", "iso"),
    thread=("number", "number"),
    url="html_url",
    extra=("state", "labels", "draft", "merged"),
    id_prefix="pr_",
    thread_prefix="pr_",
)

GITHUB_ISSUE_COMMENT = SourceManifest(
    provider="github",
    archetype="tracker",
    external_id="id",
    body="body",
    author="user.login",
    container="repository.full_name",
    timestamp=("created_at", "iso"),
    thread=("issue_number", "issue_number"),
    parent="issue_number",
    url="html_url",
    id_prefix="comment_",
    thread_prefix="issue_",
)

GMAIL = SourceManifest(
    provider="gmail",
    archetype="conversation",
    external_id="id",
    body="body",
    title="subject",
    author="from",
    container="mailbox",
    timestamp=("internalDate", "epoch_ms"),
    thread=("threadId", "id"),
    url="url",
    participants="to",
    extra=("cc", "labels"),
)


__all__ = [
    "SLACK",
    "GITHUB_ISSUE",
    "GITHUB_PR",
    "GITHUB_ISSUE_COMMENT",
    "GMAIL",
    "strip_slack_markup",
    "slack_permalink",
]
