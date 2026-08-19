"""Declarative manifests for each shipping provider (§6.0).

A new connector should almost always mean a new entry here plus fetch/auth —
not a new adapter module. Provider-specific code stays in `pre` hooks.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Mapping

from joel.adapters.base import SourceManifest

_SLACK_USER = re.compile(r"<@(U[A-Z0-9]+)>")
_SLACK_CHANNEL = re.compile(r"<#(C[A-Z0-9]+)(?:\|[^>]*)?>")
_SLACK_LINK = re.compile(r"<(https?://[^|>]+)(?:\|([^>]*))?>")
_SLACK_BOLD = re.compile(r"\*([^*]+)\*")
_SLACK_ITALIC = re.compile(r"(?<!\w)_([^_]+)_(?!\w)")
_SLACK_STRIKE = re.compile(r"~([^~]+)~")
_SLACK_CODE = re.compile(r"`([^`]+)`")
_GMAIL_QUOTE_MARKERS = (
    re.compile(r"^On .{10,80} wrote:\s*$", re.M),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.M | re.I),
    re.compile(r"^From: .+\nSent: .+\n", re.M),
)


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
    if not out.get("author_handle") and out.get("user"):
        out["author_handle"] = f"@{str(out['user']).lstrip('@')}"
    # Surface mention handles for participants_raw without normalizing names.
    if "mentions" not in out:
        out["mentions"] = [f"@{m}" for m in _SLACK_USER.findall(text)]
    return out


def qualify_slack_identity(raw: dict[str, Any]) -> dict[str, Any]:
    """Slack timestamps are channel-local; qualify every identity by channel."""
    channel = raw.get("channel_id") or raw.get("channel")
    ts = raw.get("ts")
    if not channel or not ts:
        return raw
    out = dict(raw)
    out["channel_id"] = str(channel)
    thread_ts = raw.get("thread_ts") or ts
    out["_external_id"] = f"{channel}:{ts}"
    out["_thread_id"] = f"{channel}:{thread_ts}"
    out["_parent_id"] = (
        f"{channel}:{thread_ts}" if str(thread_ts) != str(ts) else None
    )
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
    external_id="_external_id",
    body="text",
    author="author_handle",
    container="channel",
    timestamp=("ts", "epoch"),
    thread=("_thread_id", "_external_id"),
    parent="_parent_id",
    url=slack_permalink,
    extra=("reactions", "files", "channel_id", "channel_kind"),
    participants="mentions",
    pre=(strip_slack_markup, qualify_slack_identity),
)


def _github_repo(raw: Mapping[str, Any]) -> str:
    repository = raw.get("repository")
    if isinstance(repository, dict):
        return str(repository.get("full_name") or "")
    return str(raw.get("full_name") or "")


def qualify_github_item(kind: str):
    """Qualify issue/PR identity by repo so #1 in two repos cannot collide.

    Empty/short bodies fall back to the title so a PR still becomes a doc.

    Also prepends a one-line status ("Status: merged"/"draft"/"open"/
    "closed") to the body. Without this, "is PR 118 merged?" has no way to
    be answered from the doc's own text — a PR description essentially
    never restates its own merge state, and `merged`/`draft`/`state` lived
    only in `extra`, which retrieval and the answer LLM never read (§13.2's
    live PR-state lookup surfaced this — the fetch worked, but the fetched
    doc still couldn't answer the question it was fetched for).
    """

    def hook(raw: dict[str, Any]) -> dict[str, Any]:
        out = dict(raw)
        body = out.get("body")
        title = str(out.get("title") or "").strip()
        if (not isinstance(body, str) or len(body.strip()) < 20) and title:
            out["body"] = title
        if kind == "pr":
            state = str(out.get("state") or "open")
            if out.get("merged"):
                status = "merged"
            elif out.get("draft"):
                status = "draft"
            elif state == "closed":
                status = "closed (not merged)"  # explicit -- "closed" alone leaves merged-or-not ambiguous
            else:
                status = state
        else:
            status = str(out.get("state") or "open")
        out["body"] = f"Status: {status}\n\n{out.get('body') or ''}".rstrip()
        repo = _github_repo(out)
        number = out.get("number")
        if repo and number is not None:
            qualified = f"{repo}#{number}"
            out["_qualified_id"] = qualified
            out["_thread_key"] = f"{kind}_{qualified}"
        return out

    return hook


GITHUB_ISSUE = SourceManifest(
    provider="github",
    archetype="tracker",
    external_id="_qualified_id",
    body="body",
    title="title",
    author="user.login",
    container="repository.full_name",
    timestamp=("created_at", "iso"),
    thread=("_thread_key", "_qualified_id"),
    url="html_url",
    extra=("state", "labels", "assignees"),
    id_prefix="issue_",
    pre=(qualify_github_item("issue"),),
)

GITHUB_PR = SourceManifest(
    provider="github",
    archetype="tracker",
    external_id="_qualified_id",
    body="body",
    title="title",
    author="user.login",
    container="repository.full_name",
    timestamp=("created_at", "iso"),
    thread=("_thread_key", "_qualified_id"),
    url="html_url",
    extra=("state", "labels", "draft", "merged"),
    id_prefix="pr_",
    pre=(qualify_github_item("pr"),),
)

GITHUB_ISSUE_COMMENT = SourceManifest(
    provider="github",
    archetype="tracker",
    external_id="id",
    body="body",
    author="user.login",
    container="repository.full_name",
    timestamp=("created_at", "iso"),
    thread=("thread_key", "thread_key"),
    parent="thread_key",
    url="html_url",
    id_prefix="comment_",
)

GITHUB_PR_REVIEW = SourceManifest(
    provider="github",
    archetype="tracker",
    external_id="id",
    body="body",
    author="user.login",
    container="repository.full_name",
    timestamp=("submitted_at", "iso"),
    thread=("thread_key", "thread_key"),
    parent="thread_key",
    url="html_url",
    extra=("state",),
    id_prefix="review_",
)

GITHUB_CODE = SourceManifest(
    provider="github",
    archetype="code",
    external_id="_qualified_id",
    body="body",
    title="title",
    container="repository.full_name",
    url="html_url",
    granularity="code",
    id_prefix="code_",
    min_body_chars=1,
)

def strip_gmail_quotes(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop quoted reply tails; keep signatures (entity-resolution fuel)."""
    body = raw.get("body")
    if not isinstance(body, str) or not body:
        return raw
    cut = len(body)
    for marker in _GMAIL_QUOTE_MARKERS:
        match = marker.search(body)
        if match:
            cut = min(cut, match.start())
    cleaned = "\n".join(
        line for line in body[:cut].splitlines() if not line.lstrip().startswith(">")
    ).strip()
    out = dict(raw)
    out["body"] = cleaned
    return out


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
    pre=(strip_gmail_quotes,),
)


class _HTMLMarkdown(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n" + "#" * int(tag[1]) + " ")
        elif tag in {"p", "div", "tr"}:
            self.parts.append("\n")
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in {"code", "pre"}:
            self.parts.append("`")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "table"}:
            self.parts.append("\n")
        elif tag in {"code", "pre"}:
            self.parts.append("`")

    def handle_data(self, data: str) -> None:
        if not self._skip and data:
            self.parts.append(data)


def html_to_markdown(raw_html: str) -> str:
    parser = _HTMLMarkdown()
    parser.feed(raw_html or "")
    text = "".join(parser.parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def adf_to_text(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(item) for item in node)
    if not isinstance(node, dict):
        return ""
    ntype = str(node.get("type") or "")
    text = str(node.get("text") or "")
    kids = adf_to_text(node.get("content"))
    if ntype in {"paragraph", "heading", "blockquote", "listItem"}:
        return f"{text}{kids}\n"
    if ntype == "hardBreak":
        return "\n"
    return f"{text}{kids}"


def flatten_jira_body(raw: dict[str, Any]) -> dict[str, Any]:
    body = raw.get("body")
    if isinstance(body, dict):
        out = dict(raw)
        out["body"] = adf_to_text(body).strip()
        return out
    description = raw.get("description")
    if isinstance(description, dict) and not raw.get("body"):
        out = dict(raw)
        out["body"] = adf_to_text(description).strip()
        return out
    return raw


def flatten_confluence_body(raw: dict[str, Any]) -> dict[str, Any]:
    body = raw.get("body")
    html = ""
    if isinstance(body, str):
        html = body
    elif isinstance(body, dict):
        storage = body.get("storage")
        if isinstance(storage, dict):
            html = str(storage.get("value") or "")
        else:
            html = str(body.get("value") or "")
    if not html:
        return raw
    out = dict(raw)
    out["body"] = html_to_markdown(html)
    title = str(raw.get("title") or "").lower()
    if "runbook" in title or "playbook" in title:
        out["doc_type"] = "runbook"
    elif "spec" in title or "rfc" in title:
        out["doc_type"] = "spec"
    elif "policy" in title:
        out["doc_type"] = "policy"
    else:
        out["doc_type"] = "notes"
    return out


H2_SPLIT_CHARS = 12_000  # ~3k tokens


def split_document_on_h2(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Split long Confluence-style pages on H2 so each section is its own doc."""
    flattened = flatten_confluence_body(raw)
    body = str(flattened.get("body") or "")
    page_id = str(flattened.get("id") or "")
    if not page_id or len(body) < H2_SPLIT_CHARS:
        return [flattened]
    chunks = re.split(r"(?m)^(## .+)$", body)
    if len(chunks) <= 1:
        return [flattened]
    sections: list[tuple[str, str]] = []
    preamble = chunks[0].strip()
    if preamble:
        sections.append(("", preamble))
    for index in range(1, len(chunks), 2):
        heading = chunks[index].lstrip("#").strip()
        text = chunks[index + 1].strip() if index + 1 < len(chunks) else ""
        block = f"## {heading}\n\n{text}".strip() if heading else text
        if block:
            sections.append((heading, block))
    if len(sections) <= 1:
        return [flattened]
    parts: list[dict[str, Any]] = []
    for index, (heading, text) in enumerate(sections):
        row = dict(flattened)
        row["id"] = f"{page_id}_s{index}"
        row["body"] = text
        row["linked_to"] = page_id
        if heading:
            row["title"] = f"{flattened.get('title')} — {heading}"
        if index > 0:
            row["parent_id"] = page_id
        parts.append(row)
    return parts


def render_hubspot_deal(raw: dict[str, Any]) -> dict[str, Any]:
    props = raw.get("properties") if isinstance(raw.get("properties"), dict) else raw
    name = str(props.get("dealname") or "Untitled deal")
    stage = str(props.get("dealstage") or "unknown")
    amount = props.get("amount")
    owner = str(props.get("owner") or props.get("hubspot_owner_id") or "unassigned")
    notes = str(props.get("description") or "").strip()
    amount_s = str(amount) if amount not in {None, ""} else "n/a"
    body = f"Deal '{name}' — stage {stage}, amount {amount_s}, owner {owner}."
    if notes:
        body += f" Notes: {notes}"
    out = dict(raw)
    out["title"] = name
    out["body"] = body
    out["pipeline"] = str(props.get("pipeline") or "default")
    out["data"] = {
        key: str(props[key])
        for key in (
            "dealname",
            "dealstage",
            "amount",
            "pipeline",
            "closedate",
            "hubspot_owner_id",
        )
        if props.get(key) not in {None, ""}
    }
    return out


def parse_fireflies_date(raw: dict[str, Any]) -> dict[str, Any]:
    value = raw.get("date")
    if value is None:
        return raw
    out = dict(raw)
    if isinstance(value, (int, float)):
        ms = float(value)
        if ms > 10_000_000_000:
            ms = ms / 1000.0
        from datetime import datetime, timezone

        out["timestamp"] = datetime.fromtimestamp(ms, tz=timezone.utc).isoformat()
        return out
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    out["timestamp"] = text
    return out


LINEAR_ISSUE = SourceManifest(
    provider="linear",
    archetype="tracker",
    external_id="identifier",
    body="description",
    title="title",
    author="creator.name",
    container="team.key",
    timestamp=("createdAt", "iso"),
    thread=("identifier", "identifier"),
    url="url",
    extra=("state", "priority"),
)

LINEAR_COMMENT = SourceManifest(
    provider="linear",
    archetype="tracker",
    external_id="id",
    body="body",
    author="user.name",
    container="team_key",
    timestamp=("createdAt", "iso"),
    thread=("identifier", "identifier"),
    parent="identifier",
    url="url",
    id_prefix="comment_",
)

JIRA_ISSUE = SourceManifest(
    provider="jira",
    archetype="tracker",
    external_id="key",
    body="body",
    title="summary",
    author="assignee",
    container="project",
    timestamp=("created", "iso"),
    thread=("key", "key"),
    url="url",
    extra=("status", "priority"),
    pre=(flatten_jira_body,),
)

JIRA_COMMENT = SourceManifest(
    provider="jira",
    archetype="tracker",
    external_id="id",
    body="body",
    author="author",
    container="project",
    timestamp=("created", "iso"),
    thread=("key", "key"),
    parent="key",
    url="url",
    id_prefix="comment_",
    pre=(flatten_jira_body,),
)

NOTION_PAGE = SourceManifest(
    provider="notion",
    archetype="document",
    external_id="id",
    body="body",
    title="title",
    author="author",
    container="parent",
    timestamp=("last_edited_time", "iso"),
    url="url",
    extra=("doc_type",),
)

CONFLUENCE_PAGE = SourceManifest(
    provider="confluence",
    archetype="document",
    external_id="id",
    body="body",
    title="title",
    author="author",
    container="space",
    timestamp=("when", "iso"),
    parent="parent_id",
    url="url",
    extra=("doc_type", "linked_to"),
    pre=(flatten_confluence_body,),
)

GDRIVE_FILE = SourceManifest(
    provider="googledrive",
    archetype="document",
    external_id="id",
    body="body",
    title="name",
    author="author",
    container="folder",
    timestamp=("modifiedTime", "iso"),
    url="url",
)

HUBSPOT_DEAL = SourceManifest(
    provider="hubspot",
    archetype="record",
    external_id="id",
    body="body",
    title="title",
    author="owner",
    container="pipeline",
    timestamp=("updatedAt", "iso"),
    url="url",
    extra=("data",),
    pre=(render_hubspot_deal,),
)

FIREFLIES_CHUNK = SourceManifest(
    provider="fireflies",
    archetype="transcript",
    external_id="id",
    body="body",
    title="title",
    author="host",
    container="title",
    timestamp=("timestamp", "iso"),
    thread=("thread_id", "thread_id"),
    url="url",
    extra=("summary", "action_items"),
    granularity="document",
    pre=(parse_fireflies_date,),
)


__all__ = [
    "SLACK",
    "GITHUB_ISSUE",
    "GITHUB_PR",
    "GITHUB_ISSUE_COMMENT",
    "GITHUB_PR_REVIEW",
    "GITHUB_CODE",
    "GMAIL",
    "LINEAR_ISSUE",
    "LINEAR_COMMENT",
    "JIRA_ISSUE",
    "JIRA_COMMENT",
    "NOTION_PAGE",
    "CONFLUENCE_PAGE",
    "GDRIVE_FILE",
    "HUBSPOT_DEAL",
    "FIREFLIES_CHUNK",
    "qualify_slack_identity",
    "strip_slack_markup",
    "slack_permalink",
    "strip_gmail_quotes",
    "html_to_markdown",
    "adf_to_text",
    "flatten_jira_body",
    "flatten_confluence_body",
    "split_document_on_h2",
    "render_hubspot_deal",
    "parse_fireflies_date",
    "qualify_github_item",
]
