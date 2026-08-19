"""§13.2 — live lookup: read-only, then remembered. Fires on exactly two
conditions (the caller decides which): the planner's intent is `"live"`, or
the abstention gate fired and at least one whitelisted connector is
authorized. Never an open-ended tool loop — `detect_live_targets` only ever
recognizes the fixed whitelist below, and a question that doesn't match one
of them yields zero targets, not a guess.

**Implemented today: 2 of the 4 whitelisted operations** — current state of
a GitHub PR/issue by number, and the latest N messages in a Slack channel.
Jira/Linear "an issue by key" and Gmail "a mail thread by id" are the same
shape (a `LiveTarget` variant + a narrow point-lookup fetcher in that
provider's `connectors/*.py`, mirroring `fetch_github_item`/
`fetch_slack_channel_latest`) but aren't wired up yet — a question that
would need them degrades to "not found live either", same as any other
unimplemented target, never a crash.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable

from joel.connectors.github import fetch_github_item
from joel.connectors.http import RequestFn
from joel.connectors.slack import fetch_slack_channel_latest
from joel.models import CanonicalDoc
from joel.retrieve.planner import QueryPlan

MAX_LOOKUPS = 2
TIMEOUT_SECONDS = 10

_GITHUB_ITEM_RE = re.compile(r"(?:([\w.-]+/[\w.-]+))?#(\d+)")
_SLACK_CHANNEL_RE = re.compile(r"#([a-z0-9][a-z0-9_-]{0,79})", re.I)


@dataclass(frozen=True)
class GitHubItemTarget:
    owner: str
    repo: str
    number: int

    @property
    def description(self) -> str:
        return f"GitHub {self.owner}/{self.repo}#{self.number}"


@dataclass(frozen=True)
class SlackChannelTarget:
    channel_name: str

    @property
    def description(self) -> str:
        return f"Slack #{self.channel_name}"


LiveTarget = GitHubItemTarget | SlackChannelTarget


def _connected_github_repos(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT container FROM docs WHERE source_type='github' AND container IS NOT NULL"
    ).fetchall()
    return [r["container"] for r in rows if r["container"]]


def detect_live_targets(
    conn: sqlite3.Connection, question: str, plan: QueryPlan
) -> list[LiveTarget]:
    """Pattern-match the fixed whitelist against the question text (plus
    the planner's already-extracted entities/exact_tokens) — deliberately
    NOT another LLM call. The whitelist is four narrow, literal shapes; a
    regex is the right tool, and it keeps live detection free."""
    targets: list[LiveTarget] = []
    seen: set[LiveTarget] = set()
    # The question, its planner-extracted entities, AND its exact_tokens are
    # concatenated so a mention showing up in any of them is caught — but
    # the planner often echoes the same literal substring from the question
    # back into entities/exact_tokens, so the SAME match can otherwise be
    # found more than once; `seen` dedupes purely on the target's identity.
    haystack = " ".join([question, *plan.entities, *plan.exact_tokens])

    for match in _GITHUB_ITEM_RE.finditer(haystack):
        if len(targets) >= MAX_LOOKUPS:
            break
        full_name, number = match.group(1), match.group(2)
        if full_name and "/" in full_name:
            owner, repo = full_name.split("/", 1)
        else:
            repos = _connected_github_repos(conn)
            if len(repos) != 1:
                continue  # ambiguous or no repo connected -- don't guess
            owner, repo = repos[0].split("/", 1)
        target = GitHubItemTarget(owner=owner, repo=repo, number=int(number))
        if target not in seen:
            seen.add(target)
            targets.append(target)

    for match in _SLACK_CHANNEL_RE.finditer(haystack):
        if len(targets) >= MAX_LOOKUPS:
            break
        name = match.group(1)
        if name.isdigit():
            # A bare "#2" is an issue/PR reference (already handled above,
            # or for a repo that isn't connected), never a real Slack
            # channel name -- Slack channels are practically never
            # all-digits, and treating one as a channel here would mean a
            # GitHub reference silently steals a live-lookup slot from an
            # actual channel mention later in the same question.
            continue
        target = SlackChannelTarget(channel_name=name)
        if target not in seen:
            seen.add(target)
            targets.append(target)

    return targets[:MAX_LOOKUPS]


@dataclass(frozen=True)
class LiveFetch:
    target: LiveTarget
    docs: list[CanonicalDoc]


def fetch_live_target(
    target: LiveTarget,
    *,
    github_request: RequestFn | None = None,
    slack_token: str = "",
    slack_caller: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> LiveFetch:
    """One whitelisted point-lookup. Callers run this under their own
    timeout (§13.2's 10s cap) — this function does not enforce it itself,
    since a thread-based timeout has to wrap the call site, not live inside
    the callee."""
    if isinstance(target, GitHubItemTarget):
        if github_request is None:
            return LiveFetch(target, [])
        doc = fetch_github_item(
            request=github_request, owner=target.owner, repo=target.repo, number=target.number
        )
        return LiveFetch(target, [doc] if doc else [])
    if isinstance(target, SlackChannelTarget):
        if not slack_token and slack_caller is None:
            return LiveFetch(target, [])
        docs = fetch_slack_channel_latest(
            slack_token, channel_name=target.channel_name, caller=slack_caller
        )
        return LiveFetch(target, docs)
    return LiveFetch(target, [])


__all__ = [
    "MAX_LOOKUPS",
    "TIMEOUT_SECONDS",
    "GitHubItemTarget",
    "SlackChannelTarget",
    "LiveTarget",
    "LiveFetch",
    "detect_live_targets",
    "fetch_live_target",
]
