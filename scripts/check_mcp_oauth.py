"""MCP OAuth 2.1: DCR, consent, PKCE token, bearer accepts joel_at_.

API keys stay; this is the sign-in path. Synthetic checks hit the real
FastAPI routes against a disposable SQLite database (no running server).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import joel.app as app  # noqa: E402
import joel.identity as identity  # noqa: E402
from joel.auth import Access, classify  # noqa: E402
from joel.mcp_oauth import (  # noqa: E402
    ACCESS_PREFIX,
    actor_from_oauth_access,
    is_oauth_http_path,
)
from joel.mcp_server import _BearerAuthASGI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

NOW = "2026-08-21T00:00:00+00:00"


def _seed_actor(conn) -> identity.Actor:
    conn.execute(
        "INSERT INTO orgs(id,domain,name,logo_url,created_at) VALUES (1,'x.co','X','',?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO users(id,email,display_name,password_hash,created_at) "
        "VALUES ('u_a','a@x.co','A','h',?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO memberships(user_id,org_id,role,created_at) VALUES ('u_a',1,'admin',?)",
        (NOW,),
    )
    actor = identity.actor_for_user(conn, "u_a", 1)
    assert actor is not None
    return actor


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def check_classify_and_paths() -> None:
    assert is_oauth_http_path("/authorize")
    assert is_oauth_http_path("/token")
    assert is_oauth_http_path("/register")
    assert is_oauth_http_path("/revoke")
    assert is_oauth_http_path("/.well-known/oauth-authorization-server")
    assert is_oauth_http_path("/.well-known/oauth-protected-resource/mcp")
    assert not is_oauth_http_path("/api/mcp/oauth/consent")
    assert classify("GET", "/authorize") is Access.PUBLIC
    assert classify("POST", "/token") is Access.PUBLIC
    assert classify("POST", "/register") is Access.PUBLIC
    assert classify("GET", "/.well-known/oauth-authorization-server") is Access.PUBLIC
    assert classify("GET", "/api/mcp/oauth/pending") is Access.PUBLIC
    assert classify("POST", "/api/mcp/oauth/consent") is Access.ACTOR
    print("ok  oauth.1: OAuth HTTP paths are public; consent POST still needs an Actor")


def check_pkce_round_trip(tmp_dir: Path) -> None:
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()
    with app.db() as conn:
        actor = _seed_actor(conn)

    verifier, challenge = _pkce()
    redirect_uri = "http://127.0.0.1:9999/callback"
    client = TestClient(app.app, follow_redirects=False)

    meta = client.get("/.well-known/oauth-authorization-server")
    assert meta.status_code == 200, meta.text
    body = meta.json()
    assert body["authorization_endpoint"].endswith("/authorize")
    assert body["token_endpoint"].endswith("/token")
    assert body["registration_endpoint"].endswith("/register")
    print("ok  oauth.2: authorization-server metadata advertises register / authorize / token")

    prm = client.get("/.well-known/oauth-protected-resource/mcp")
    assert prm.status_code == 200, prm.text
    assert "/mcp" in prm.json()["resource"]
    print("ok  oauth.3: protected-resource metadata names /mcp")

    registered = client.post(
        "/register",
        json={
            "client_name": "Cursor",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    assert registered.status_code in {200, 201}, registered.text
    info = registered.json()
    client_id = info["client_id"]
    client_secret = info["client_secret"]
    assert client_id and client_secret
    print("ok  oauth.4: dynamic client registration mints a client_id + secret")

    authorize = client.get(
        "/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "st8",
            "scope": "mcp",
        },
    )
    assert authorize.status_code in {302, 303, 307}, authorize.text
    consent = urlparse(authorize.headers["location"])
    rid = parse_qs(consent.query).get("rid", [""])[0]
    assert rid, authorize.headers.get("location")
    assert consent.path == "/oauth/consent"
    print("ok  oauth.5: /authorize parks the request and redirects to /oauth/consent")

    pending = app._oauth_provider.pending_public(rid)
    assert pending is not None and pending["client_name"] == "Cursor"

    peek = client.get("/api/mcp/oauth/pending", params={"rid": rid})
    assert peek.status_code == 200, peek.text
    assert peek.json()["client_name"] == "Cursor"

    denied = app._oauth_provider.complete_consent(rid, actor, allow=False)
    assert "error=access_denied" in denied
    assert "st8" in denied
    print("ok  oauth.6: Deny returns the client to its redirect_uri with access_denied")

    # Fresh authorize for Allow — previous pending row was deleted on Deny.
    authorize = client.get(
        "/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "st8",
            "scope": "mcp",
        },
    )
    rid = parse_qs(urlparse(authorize.headers["location"]).query)["rid"][0]
    allowed = app._oauth_provider.complete_consent(rid, actor, allow=True)
    code = parse_qs(urlparse(allowed).query)["code"][0]
    assert parse_qs(urlparse(allowed).query)["state"] == ["st8"]
    print("ok  oauth.7: Allow issues a one-time authorization code")

    token = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200, token.text
    minted = token.json()
    access = minted["access_token"]
    refresh = minted["refresh_token"]
    assert access.startswith(ACCESS_PREFIX)
    assert refresh.startswith("joel_rt_")
    print("ok  oauth.8: /token PKCE exchange returns joel_at_ / joel_rt_")

    replay = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": verifier,
        },
    )
    assert replay.status_code == 400
    print("ok  oauth.9: a code cannot be exchanged twice")

    with app.db() as conn:
        oauth_actor = actor_from_oauth_access(conn, access)
        assert oauth_actor is not None
        assert oauth_actor.user_id == "u_a"
        assert oauth_actor.org_id == 1
        assert actor_from_oauth_access(conn, "joel_at_nope") is None
        key_actor = identity.actor_from_api_key(conn, access)
        assert key_actor is None
    print("ok  oauth.10: access token resolves to the consenting Actor; it is not an API key")

    resolved = app._mcp_actor_resolver(access)
    assert resolved is not None and resolved.user_id == "u_a"
    print("ok  oauth.11: MCP bearer resolver accepts the OAuth access token")


def check_bearer_www_authenticate() -> None:
    async def inner_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    wrapped = _BearerAuthASGI(
        inner_app,
        lambda token: "actor" if token == "good" else None,
        resource_metadata_url="http://localhost:3000/.well-known/oauth-protected-resource/mcp",
    )

    async def run(auth_header: bytes | None):
        sent = []

        async def send(message):
            sent.append(message)

        headers = [(b"authorization", auth_header)] if auth_header else []
        await wrapped({"type": "http", "headers": headers}, None, send)
        return sent

    missing = asyncio.run(run(None))
    assert missing[0]["status"] == 401
    headers = dict(missing[0]["headers"])
    www = headers[b"www-authenticate"].decode()
    assert "resource_metadata=" in www
    assert "oauth-protected-resource/mcp" in www
    print("ok  oauth.12: 401 WWW-Authenticate points at protected-resource metadata")


def check_mcp_no_slash_is_401_not_redirect(tmp_dir: Path) -> None:
    """Cursor's snippet is `/mcp` (no trailing slash). A 307 to the API
    host would strip the bearer token on the follow."""
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()
    client = TestClient(app.app, follow_redirects=False)
    res = client.post("/mcp", headers={"accept": "application/json"})
    assert res.status_code == 401, res.status_code
    assert "resource_metadata=" in res.headers.get("www-authenticate", "")
    print("ok  oauth.13: POST /mcp (no slash) is 401 with WWW-Authenticate, not a 307")


def main() -> None:
    check_classify_and_paths()
    check_bearer_www_authenticate()
    with tempfile.TemporaryDirectory() as td:
        check_mcp_no_slash_is_401_not_redirect(Path(td))
    with tempfile.TemporaryDirectory() as td:
        check_pkce_round_trip(Path(td))
    print("\nMCP OAuth: all automated checks passed.")


if __name__ == "__main__":
    main()
