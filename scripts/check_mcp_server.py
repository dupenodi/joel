"""§13's MCP surface (§0.3's "API keys — not built", now built): identity
via API key, `AskContext` built server-side from the key's owner, the
`ask` tool reusing the exact same `answer_question` pipeline `/api/ask`
uses.

`identity.py`'s create/list/revoke/resolve functions are tested directly
against a real disposable SQLite database (through the actual
migrations). `_BearerAuthASGI` (the auth wrapper around the MCP
Streamable HTTP transport) is tested directly against a fake ASGI
scope/send, no real server needed. `check_live_mcp_round_trip` is the one
real check: a genuine MCP client (the actual `mcp` SDK) against the
already-running dev server, with a real API key, calling the real `ask`
tool against the real corpus -- skipped honestly if no dev server is
reachable.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import joel.app as app  # noqa: E402
import joel.identity as identity  # noqa: E402
from joel.mcp_server import _BearerAuthASGI  # noqa: E402


def check_api_key_lifecycle(tmp_dir: Path) -> None:
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()
    with app.db() as conn:
        conn.execute(
            "INSERT INTO orgs(id,domain,name,logo_url,created_at) VALUES (1,'x.co','X','','2026-08-20T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO users(id,email,display_name,password_hash,created_at) "
            "VALUES ('u_a','a@x.co','A','h','2026-08-20T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO memberships(user_id,org_id,role,created_at) VALUES ('u_a',1,'admin','2026-08-20T00:00:00+00:00')"
        )

        actor = identity.actor_for_user(conn, "u_a", 1)
        assert actor is not None
        key_id, raw = identity.create_api_key(conn, actor, "my laptop")
        assert raw.startswith(identity.API_KEY_PREFIX)

        actor = identity.actor_from_api_key(conn, raw)
        assert actor is not None and actor.user_id == "u_a"
        print("ok  mcp.1: a freshly created key resolves to its owner's normal Actor")

        assert identity.actor_from_api_key(conn, "joel_sk_not_a_real_key") is None
        assert identity.actor_from_api_key(conn, None) is None
        assert identity.actor_from_api_key(conn, "not even the right prefix") is None
        print("ok  mcp.2: an unknown or malformed key resolves to nothing, never a crash")

        keys = identity.list_api_keys(conn, actor)
        assert len(keys) == 1 and keys[0]["label"] == "my laptop"
        assert keys[0]["last_used_at"] is not None, "resolving the key above must stamp last_used_at"
        print("ok  mcp.3: list_api_keys shows the key with real metadata, never the raw secret")

        removed = identity.revoke_api_key(conn, actor, key_id)
        assert removed
        assert identity.actor_from_api_key(conn, raw) is None, "a revoked key must stop resolving immediately"
        assert not identity.revoke_api_key(conn, actor, key_id), "revoking twice must not raise, just report nothing removed"
        print("ok  mcp.4: revoking a key stops it from resolving; revoking again is a clean no-op")


def check_revoke_is_scoped_to_owner(tmp_dir: Path) -> None:
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()
    with app.db() as conn:
        conn.execute(
            "INSERT INTO orgs(id,domain,name,logo_url,created_at) VALUES (1,'x.co','X','','2026-08-20T00:00:00+00:00')"
        )
        for uid in ("u_a", "u_b"):
            conn.execute(
                "INSERT INTO users(id,email,display_name,password_hash,created_at) VALUES (?,?,?,?,?)",
                (uid, f"{uid}@x.co", uid, "h", "2026-08-20T00:00:00+00:00"),
            )
            conn.execute(
                "INSERT INTO memberships(user_id,org_id,role,created_at) VALUES (?,1,'member',?)",
                (uid, "2026-08-20T00:00:00+00:00"),
            )
        actor_a = identity.actor_for_user(conn, "u_a", 1)
        actor_b = identity.actor_for_user(conn, "u_b", 1)
        assert actor_a is not None and actor_b is not None
        key_id, raw = identity.create_api_key(conn, actor_a, "a's key")
        stolen = identity.revoke_api_key(conn, actor_b, key_id)
        assert not stolen, "one person must never be able to revoke another person's key"
        assert identity.actor_from_api_key(conn, raw) is not None, "the key must survive the failed cross-user revoke"
        print("ok  mcp.5: revoking a key is scoped to its owner -- another user's revoke attempt is a no-op")


def check_bearer_auth_asgi_wrapper() -> None:
    """Direct test of the ASGI middleware, no real server needed."""

    async def inner_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    calls: list[str] = []

    def resolver(token: str):
        calls.append(token)
        return "fake-actor" if token == "goodtoken" else None

    wrapped = _BearerAuthASGI(inner_app, resolver)

    async def run(auth_header: bytes | None):
        sent = []

        async def send(message):
            sent.append(message)

        headers = [(b"authorization", auth_header)] if auth_header else []
        await wrapped({"type": "http", "headers": headers}, None, send)
        return sent

    sent_good = asyncio.run(run(b"Bearer goodtoken"))
    assert sent_good[0]["status"] == 200, "a valid bearer token must reach the inner app"

    sent_bad = asyncio.run(run(b"Bearer wrongtoken"))
    assert sent_bad[0]["status"] == 401

    sent_missing = asyncio.run(run(None))
    assert sent_missing[0]["status"] == 401
    print("ok  mcp.6: _BearerAuthASGI passes a valid key through, rejects a wrong or missing one with 401")


def check_live_mcp_round_trip() -> None:
    """The one real check: a genuine MCP client against the already-
    running dev server, a real API key, a real question against the real
    corpus."""
    import urllib.request

    try:
        urllib.request.urlopen("http://127.0.0.1:8000/api/healthz", timeout=2)
    except Exception:
        print("skip live: no dev server reachable at 127.0.0.1:8000 -- real MCP round trip skipped")
        return

    try:
        import httpx2
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError:
        print("skip live: mcp/httpx2 not importable")
        return

    data_dir = ROOT / "data"
    db_path = data_dir / "index" / "joel.db"
    if not db_path.exists():
        print("skip live: no real data/index/joel.db")
        return
    app.DATA_DIR = data_dir
    app.DB_PATH = db_path

    with app.db() as conn:
        row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
        if row is None:
            print("skip live: no real user to mint a test API key for")
            return
        membership = conn.execute(
            "SELECT org_id FROM memberships WHERE user_id=? LIMIT 1", (row["id"],)
        ).fetchone()
        if membership is None:
            print("skip live: user has no workspace membership")
            return
        actor = identity.actor_for_user(conn, row["id"], int(membership["org_id"]))
        if actor is None:
            print("skip live: could not resolve Actor for smoke-test key")
            return
        key_id, raw = identity.create_api_key(conn, actor, "check_mcp_server.py smoke test")

    async def round_trip() -> str:
        client = httpx2.AsyncClient(headers={"Authorization": f"Bearer {raw}"}, timeout=90.0)
        async with streamable_http_client("http://127.0.0.1:8000/mcp/", http_client=client) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.server_info.name == "joel"
                tools = await session.list_tools()
                assert "ask" in [t.name for t in tools.tools]
                result = await session.call_tool("ask", {"question": "what is joel"})
                return result.content[0].text

    async def unauthenticated_rejected() -> bool:
        bad_client = httpx2.AsyncClient(timeout=10.0)
        try:
            async with streamable_http_client("http://127.0.0.1:8000/mcp/", http_client=bad_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
            return False
        except Exception:
            return True

    try:
        answer = asyncio.run(round_trip())
        assert answer.strip(), "a real tool call must return real text, not an empty string"
        rejected = asyncio.run(unauthenticated_rejected())
        assert rejected, "a request with no bearer token must be rejected, never reach the tool"
        print(f"ok  live: real MCP round trip -- init, list_tools, and a real 'ask' call all succeeded ({answer[:70]!r}...)")
    finally:
        with app.db() as conn:
            identity.revoke_api_key(conn, actor, key_id)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        check_api_key_lifecycle(Path(td))
    with tempfile.TemporaryDirectory() as td:
        check_revoke_is_scoped_to_owner(Path(td))
    check_bearer_auth_asgi_wrapper()
    check_live_mcp_round_trip()
    print("\nMCP server (§13): all automated checks passed.")


if __name__ == "__main__":
    main()
