"""HTTP access layers: public / session / actor."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from joel.auth import Access, classify, unauthorized, RequestIdentity  # noqa: E402


def main() -> None:
    assert classify("OPTIONS", "/api/ask") is Access.PUBLIC
    assert classify("GET", "/api/healthz") is Access.PUBLIC
    assert classify("POST", "/api/auth/login") is Access.PUBLIC
    assert classify("GET", "/api/auth/invite/abc") is Access.PUBLIC
    assert classify("POST", "/api/auth/invite/abc/accept") is Access.PUBLIC
    assert classify("GET", "/mcp/foo") is Access.PUBLIC

    assert classify("GET", "/api/workspaces") is Access.SESSION
    assert classify("POST", "/api/workspaces") is Access.SESSION
    assert classify("POST", "/api/auth/workspace") is Access.SESSION

    assert classify("GET", "/api/ask") is Access.ACTOR
    assert classify("GET", "/api/org") is Access.ACTOR
    assert classify("PATCH", "/api/workspace") is Access.ACTOR

    empty = RequestIdentity(session_id=None, user_id=None, actor=None)
    assert unauthorized(empty, Access.PUBLIC) is False
    assert unauthorized(empty, Access.SESSION) is True
    assert unauthorized(empty, Access.ACTOR) is True

    session_only = RequestIdentity(session_id="s", user_id="u", actor=None)
    assert unauthorized(session_only, Access.SESSION) is False
    assert unauthorized(session_only, Access.ACTOR) is True

    print("ok  auth: public / session / actor layers")


if __name__ == "__main__":
    main()
