"""§13.2 — live lookup: read-only, then remembered. Fires on exactly two
conditions (the caller decides which): the planner's intent is `"live"`, or
the abstention gate fired and at least one whitelisted connector is
authorized. Never an open-ended tool loop.

Each live provider exposes two shapes of read:

- **point** — a named object in the question (`owner/repo#118`, `#eng`)
- **catalog** — current open set on a named or connected container, when
  the question implicates that provider but has no point id

A question that matches neither yields zero targets, not a guess.
Jira/Linear/Gmail catalogs are the same shape but not wired yet.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable

from joel.connectors.github import fetch_github_item, fetch_github_open_items
from joel.connectors.http import RequestFn
from joel.connectors.slack import fetch_slack_channel_latest
from joel.models import CanonicalDoc
from joel.retrieve.planner import QueryPlan

MAX_LOOKUPS = 2
TIMEOUT_SECONDS = 10

# Credentials still work while ingest is in flight. Live is a point/catalog
# API read, not a wait-for-index. Dead/unauthed states stay out.
LIVE_CONNECTION_STATUSES = frozenset(
    {"ready", "syncing", "backfilling", "distilling", "linking"}
)


def connection_can_live(status: str) -> bool:
    return status in LIVE_CONNECTION_STATUSES

_GITHUB_ITEM_RE = re.compile(r"(?:([\w.-]+/[\w.-]+))?#(\d+)")
_GITHUB_REPO_RE = re.compile(r"(?:github\.com/)?\b([\w.-]+/[\w.-]+)\b", re.I)
_SLACK_CHANNEL_RE = re.compile(r"#([a-z0-9][a-z0-9_-]{0,79})", re.I)
_NOT_A_REPO = re.compile(
    r"\.(py|js|jsx|ts|tsx|json|md|css|html|lock|yml|yaml)$", re.I
)


@dataclass(frozen=True)
class GitHubItemTarget:
    owner: str
    repo: str
    number: int

    @property
    def provider(self) -> str:
        return "github"

    @property
    def description(self) -> str:
        return f"GitHub {self.owner}/{self.repo}#{self.number}"


@dataclass(frozen=True)
class GitHubCatalogTarget:
    """Current open issues/PRs on one connected (or named) repo."""

    owner: str
    repo: str

    @property
    def provider(self) -> str:
        return "github"

    @property
    def description(self) -> str:
        return f"GitHub {self.owner}/{self.repo} open items"


@dataclass(frozen=True)
class SlackChannelTarget:
    channel_name: str

    @property
    def provider(self) -> str:
        return "slack"

    @property
    def description(self) -> str:
        return f"Slack #{self.channel_name}"


LiveTarget = GitHubItemTarget | GitHubCatalogTarget | SlackChannelTarget


@dataclass(frozen=True)
class LiveCapability:
    """How a provider is recognized when the question has no point id.

    `cues` are the tool's own names and the nouns of its catalog — not
    question templates. Slack has no catalog without a channel, so it
    is omitted here; `#channel` is enough.
    """

    provider: str
    cues: frozenset[str]


# Providers that can fill a catalog when cued but no point id was found.
_CATALOG_CAPABILITIES: tuple[LiveCapability, ...] = (
    LiveCapability(
        provider="github",
        cues=frozenset(
            {
                "github",
                "gh",
                "pull request",
                "pull requests",
                "pull-request",
                "prs",
                "pr",
            }
        ),
    ),
)


def _connected_github_repos(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """SELECT container FROM docs
           WHERE source_type='github' AND container LIKE '%/%'
           GROUP BY container
           ORDER BY MAX(timestamp) DESC"""
    ).fetchall()
    return [r["container"] for r in rows if r["container"]]


def _looks_like_repo(full_name: str) -> bool:
    if full_name.count("/") != 1:
        return False
    owner, repo = full_name.split("/", 1)
    if not owner or not repo or owner.lower() == "github.com":
        return False
    return _NOT_A_REPO.search(repo) is None


def _haystack(question: str, plan: QueryPlan) -> str:
    return " ".join([question, *plan.entities, *plan.exact_tokens])


def _cued_providers(haystack: str) -> list[str]:
    text = haystack.lower()
    found: list[str] = []
    for cap in _CATALOG_CAPABILITIES:
        for cue in cap.cues:
            if " " in cue or "-" in cue:
                hit = cue in text
            else:
                hit = re.search(rf"\b{re.escape(cue)}\b", text) is not None
            if hit:
                found.append(cap.provider)
                break
    return found


def detect_live_targets(
    conn: sqlite3.Connection, question: str, plan: QueryPlan
) -> list[LiveTarget]:
    """Point ids first, then a catalog for a cued/named provider.

    Deliberately not another LLM call — the whitelist is literal shapes.
    """
    targets: list[LiveTarget] = []
    seen: set[LiveTarget] = set()

    def _add(target: LiveTarget) -> None:
        if len(targets) >= MAX_LOOKUPS or target in seen:
            return
        seen.add(target)
        targets.append(target)

    haystack = _haystack(question, plan)

    for match in _GITHUB_ITEM_RE.finditer(haystack):
        full_name, number = match.group(1), match.group(2)
        if full_name and "/" in full_name:
            owner, repo = full_name.split("/", 1)
        else:
            repos = _connected_github_repos(conn)
            if len(repos) != 1:
                continue
            owner, repo = repos[0].split("/", 1)
        _add(GitHubItemTarget(owner=owner, repo=repo, number=int(number)))

    for match in _SLACK_CHANNEL_RE.finditer(haystack):
        name = match.group(1)
        if name.isdigit():
            continue
        _add(SlackChannelTarget(channel_name=name))

    if len(targets) >= MAX_LOOKUPS:
        return targets[:MAX_LOOKUPS]

    pointed_repos = {
        (t.owner, t.repo)
        for t in targets
        if isinstance(t, (GitHubItemTarget, GitHubCatalogTarget))
    }

    for match in _GITHUB_REPO_RE.finditer(haystack):
        full_name = match.group(1)
        if not _looks_like_repo(full_name):
            continue
        owner, repo = full_name.split("/", 1)
        if (owner, repo) in pointed_repos:
            continue
        _add(GitHubCatalogTarget(owner=owner, repo=repo))
        pointed_repos.add((owner, repo))

    if "github" in _cued_providers(haystack) and not pointed_repos:
        for full_name in _connected_github_repos(conn):
            if not _looks_like_repo(full_name):
                continue
            owner, repo = full_name.split("/", 1)
            _add(GitHubCatalogTarget(owner=owner, repo=repo))
            if len(targets) >= MAX_LOOKUPS:
                break

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
    """One whitelisted read. Callers enforce the 10s cap around this call."""
    if isinstance(target, GitHubItemTarget):
        if github_request is None:
            return LiveFetch(target, [])
        doc = fetch_github_item(
            request=github_request, owner=target.owner, repo=target.repo, number=target.number
        )
        return LiveFetch(target, [doc] if doc else [])
    if isinstance(target, GitHubCatalogTarget):
        if github_request is None:
            return LiveFetch(target, [])
        docs = fetch_github_open_items(
            request=github_request, owner=target.owner, repo=target.repo
        )
        return LiveFetch(target, docs)
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
    "LIVE_CONNECTION_STATUSES",
    "connection_can_live",
    "GitHubItemTarget",
    "GitHubCatalogTarget",
    "SlackChannelTarget",
    "LiveTarget",
    "LiveFetch",
    "detect_live_targets",
    "fetch_live_target",
]
