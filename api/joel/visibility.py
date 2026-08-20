"""The room a document lives in, and the rooms an ask is allowed to read.

A document is written to exactly one room at ingest. Retrieval never infers
this later — it filters the stamp. An ask carries who is asking and where
they are asking from; the readable set is derived here, not in each lane.

This module does not know about FastAPI, Slack payloads, or SQLite schemas.
Callers pass source facts in, and get a stamp or an allowed-stamp set back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from joel.models import CanonicalDoc

ORG = "org"
KINDS = frozenset({"org", "channel", "user"})
SURFACES = frozenset({"web", "slack", "mcp"})
_ROOM_KINDS = frozenset({"org", "channel", "user"})


class VisibilityError(ValueError):
    pass


@dataclass(frozen=True)
class Visibility:
    """One room. `org` has no provider/scope; channel and user always do."""

    kind: str
    provider: str = ""
    scope: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise VisibilityError(f"unknown visibility kind {self.kind!r}")
        if self.kind == ORG:
            if self.provider or self.scope:
                raise VisibilityError("org visibility cannot carry a provider or scope")
            return
        if not self.provider or not self.scope:
            raise VisibilityError(f"{self.kind} visibility needs provider and scope")

    @property
    def stamp(self) -> str:
        if self.kind == ORG:
            return ORG
        return f"{self.kind}:{self.provider}:{self.scope}"

    @staticmethod
    def org() -> Visibility:
        return Visibility(ORG)

    @staticmethod
    def channel(provider: str, scope: str) -> Visibility:
        return Visibility("channel", provider=provider, scope=scope)

    @staticmethod
    def user(provider: str, scope: str) -> Visibility:
        return Visibility("user", provider=provider, scope=scope)


def parse(stamp: str) -> Visibility:
    text = (stamp or "").strip()
    if text == ORG:
        return Visibility.org()
    kind, sep, rest = text.partition(":")
    if not sep or kind not in {"channel", "user"}:
        raise VisibilityError(f"invalid visibility stamp {stamp!r}")
    provider, sep, scope = rest.partition(":")
    if not sep or not provider or not scope:
        raise VisibilityError(f"invalid visibility stamp {stamp!r}")
    return Visibility(kind, provider=provider, scope=scope)


def derive(
    source_type: str,
    *,
    extra: Mapping[str, Any] | None = None,
    container: str | None = None,
) -> Visibility:
    """Map provider facts onto a room. Unknown facts fail closed for private
    sources (gmail, private/im slack) and open for company-data sources."""
    extra = extra or {}
    source = (source_type or "").strip().lower()
    if source == "gmail":
        mailbox = str(container or extra.get("mailbox") or "unknown").strip().lower()
        return Visibility.user("gmail", mailbox or "unknown")
    if source == "slack":
        kind = str(extra.get("channel_kind") or "public").strip().lower()
        scope = str(extra.get("channel_id") or container or "unknown").strip() or "unknown"
        if kind in {"im", "mpim"}:
            return Visibility.user("slack", scope)
        if kind == "private":
            return Visibility.channel("slack", scope)
        return Visibility.org()
    return Visibility.org()


def apply(doc: CanonicalDoc) -> CanonicalDoc:
    """Stamp a doc from its source facts. Idempotent. Does not touch content_hash."""
    vis = derive(doc.source_type, extra=doc.extra, container=doc.container)
    if doc.visibility == vis.stamp:
        return doc
    return doc.model_copy(update={"visibility": vis.stamp})


@dataclass(frozen=True)
class Room:
    """Where the question is being asked. Built by the server for that surface,
    never taken as a client-chosen ACL."""

    surface: str
    kind: str
    provider: str = ""
    scope: str = ""

    def __post_init__(self) -> None:
        if self.surface not in SURFACES:
            raise VisibilityError(f"unknown ask surface {self.surface!r}")
        if self.kind not in _ROOM_KINDS:
            raise VisibilityError(f"unknown room kind {self.kind!r}")
        if self.kind == "channel" and (not self.provider or not self.scope):
            raise VisibilityError("channel room needs provider and scope")

    @staticmethod
    def web() -> Room:
        return Room(surface="web", kind="user", provider="web")

    @staticmethod
    def public(surface: str) -> Room:
        return Room(surface=surface, kind="org")

    @staticmethod
    def channel(surface: str, provider: str, scope: str) -> Room:
        return Room(surface=surface, kind="channel", provider=provider, scope=scope)

    @staticmethod
    def dm(surface: str, provider: str, scope: str) -> Room:
        return Room(surface=surface, kind="user", provider=provider, scope=scope)


@dataclass(frozen=True)
class AskContext:
    """Who is asking, and from where. `aliases` and `channels` are already
    complete stamps (`user:gmail:ada@x.com`, `channel:slack:C123`).

    `org_id` is the tenant boundary for FTS/SQL lanes (Mode B); LiveIndex and
    Hydra are scoped separately by the caller using the same id."""

    actor_id: str
    room: Room
    aliases: frozenset[str] = frozenset()
    channels: frozenset[str] = frozenset()
    org_id: int = 1

    @staticmethod
    def web(
        actor_id: str,
        *,
        aliases: Iterable[str] = (),
        channels: Iterable[str] = (),
        org_id: int = 1,
    ) -> AskContext:
        return AskContext(
            actor_id=actor_id,
            room=Room.web(),
            aliases=frozenset(aliases),
            channels=frozenset(channels),
            org_id=org_id,
        )


def allowed_stamps(ask: AskContext) -> frozenset[str]:
    """Stamps retrieval may return. Asking in public reads only org; asking
    in a channel reads org plus that channel; asking from a desk/DM reads
    org plus the asker's own user stamps plus channels they belong to."""
    if ask.room.kind == "org":
        return frozenset({ORG})
    if ask.room.kind == "channel":
        return frozenset({ORG, Visibility.channel(ask.room.provider, ask.room.scope).stamp})
    return frozenset({ORG, *ask.aliases, *ask.channels})


def sql_in(stamps: Iterable[str], column: str = "d.visibility") -> tuple[str, tuple[str, ...]]:
    """`column IN (?,?,…)` plus bind values. Empty set matches nothing."""
    values = tuple(stamps)
    if not values:
        return "1=0", ()
    placeholders = ",".join("?" for _ in values)
    return f"{column} IN ({placeholders})", values


__all__ = [
    "ORG",
    "VisibilityError",
    "Visibility",
    "Room",
    "AskContext",
    "parse",
    "derive",
    "apply",
    "allowed_stamps",
    "sql_in",
]
