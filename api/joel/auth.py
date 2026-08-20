"""HTTP session gate.

Identity owns people, memberships, and orgs. This module owns how a request
becomes a session / Actor. Three access layers so later work (SSO, API keys on
more routes, guest tokens) slots in without rewriting callers:

  public   — no cookie required (login, setup, invite peek, Slack, MCP)
  session  — valid session cookie; Actor may be None (pick-workspace, create)
  actor    — session bound to an org (the product API)

Callers should depend on `Access`, `RequestIdentity`, and `classify` /
`resolve` — not on the path tables.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum

from joel import identity

SESSION_COOKIE = "joel_session"


class Access(str, Enum):
    PUBLIC = "public"
    SESSION = "session"
    ACTOR = "actor"


@dataclass(frozen=True)
class RequestIdentity:
    session_id: str | None
    user_id: str | None
    actor: identity.Actor | None

    @property
    def signed_in(self) -> bool:
        return self.user_id is not None


_PUBLIC_EXACT = {
    ("GET", "/api/healthz"),
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/setup"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/composio/callback"),
    # Slack authenticates via its own request signature, not joel_session.
    ("POST", "/api/slack/events"),
}

_SESSION_EXACT = {
    ("POST", "/api/auth/workspace"),
    ("GET", "/api/workspaces"),
    ("POST", "/api/workspaces"),
}


def classify(method: str, path: str) -> Access:
    """Which access layer a request needs. OPTIONS is always public (CORS)."""
    if method == "OPTIONS":
        return Access.PUBLIC
    if (method, path) in _PUBLIC_EXACT:
        return Access.PUBLIC
    if (method, path) in _SESSION_EXACT:
        return Access.SESSION
    if path.startswith("/mcp"):
        # MCP authenticates with an API key inside its own ASGI app.
        return Access.PUBLIC
    if path.startswith("/api/auth/invite/"):
        return Access.PUBLIC
    return Access.ACTOR


def resolve(
    conn: sqlite3.Connection, session_id: str | None
) -> RequestIdentity:
    """Load whoever this cookie is, including pick-workspace (no Actor yet)."""
    if not session_id:
        return RequestIdentity(session_id=None, user_id=None, actor=None)
    actor = identity.actor_from_session(conn, session_id)
    if actor is not None:
        return RequestIdentity(
            session_id=session_id, user_id=actor.user_id, actor=actor
        )
    user_id = identity.session_user_id(conn, session_id)
    return RequestIdentity(session_id=session_id, user_id=user_id, actor=None)


def unauthorized(who: RequestIdentity, needed: Access) -> bool:
    """True when this identity cannot satisfy the access layer."""
    if needed is Access.PUBLIC:
        return False
    if needed is Access.SESSION:
        return not who.signed_in
    return who.actor is None


__all__ = [
    "Access",
    "RequestIdentity",
    "SESSION_COOKIE",
    "classify",
    "resolve",
    "unauthorized",
]
