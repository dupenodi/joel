"""MCP OAuth 2.1 (authorization code + PKCE) for this install.

joel is the authorization server. Cursor/Claude dynamically register, the
person signs in on this origin, and the access token maps to the same
Actor an API key would. Works on hosted and self-host — unlike Slack,
nothing here is a third-party app with one Events URL.

API keys (`joel_sk_…`) stay valid; this is the sign-in path.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.routes import build_resource_metadata_url, create_auth_routes, create_protected_resource_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl, AnyUrl

from joel.identity import Actor, actor_for_user, hash_token

MCP_SCOPE = "mcp"
ACCESS_TTL_SECONDS = 60 * 60
REFRESH_TTL_SECONDS = 30 * 86400
PENDING_TTL_SECONDS = 10 * 60
CODE_TTL_SECONDS = 10 * 60
ACCESS_PREFIX = "joel_at_"
REFRESH_PREFIX = "joel_rt_"

Connect = Callable[[], sqlite3.Connection]


class JoelAuthorizationCode(AuthorizationCode):
    user_id: str
    org_id: int


def resource_metadata_url(origin: str) -> str:
    resource = AnyHttpUrl(origin.rstrip("/") + "/mcp")
    return str(build_resource_metadata_url(resource))


def actor_from_oauth_access(conn: sqlite3.Connection, raw: str | None) -> Actor | None:
    if not raw or not raw.startswith(ACCESS_PREFIX):
        return None
    row = conn.execute(
        """SELECT user_id, org_id, expires_at FROM mcp_oauth_tokens
           WHERE token_hash=? AND kind='access'""",
        (hash_token(raw),),
    ).fetchone()
    if row is None:
        return None
    expires = row["expires_at"]
    if expires is not None and float(expires) < time.time():
        return None
    return actor_for_user(conn, row["user_id"], int(row["org_id"]))


class JoelAuthProvider:
    """SQLite-backed OAuthAuthorizationServerProvider."""

    def __init__(self, connect: Connect, origin: Callable[[], str]) -> None:
        self._connect = connect
        self._origin = origin

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self._db() as conn:
            row = conn.execute(
                "SELECT metadata_json FROM mcp_oauth_clients WHERE client_id=?",
                (client_id,),
            ).fetchone()
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate_json(row["metadata_json"])

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        payload = client_info.model_dump_json()
        now = datetime.now(timezone.utc).isoformat()
        with self._db() as conn:
            conn.execute(
                """INSERT INTO mcp_oauth_clients(client_id, metadata_json, created_at)
                   VALUES (?,?,?)""",
                (client_info.client_id, payload, now),
            )

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        rid = secrets.token_urlsafe(18)
        blob = json.dumps(
            {
                "state": params.state,
                "scopes": params.scopes or [MCP_SCOPE],
                "code_challenge": params.code_challenge,
                "redirect_uri": str(params.redirect_uri),
                "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                "resource": params.resource,
                "client_name": client.client_name or "MCP client",
            }
        )
        with self._db() as conn:
            conn.execute(
                """INSERT INTO mcp_oauth_pending(id, client_id, params_json, expires_at)
                   VALUES (?,?,?,?)""",
                (rid, client.client_id, blob, time.time() + PENDING_TTL_SECONDS),
            )
        return f"{self._origin().rstrip('/')}/oauth/consent?rid={rid}"

    def pending_public(self, rid: str) -> dict[str, str] | None:
        with self._db() as conn:
            row = conn.execute(
                """SELECT client_id, params_json, expires_at FROM mcp_oauth_pending
                   WHERE id=?""",
                (rid,),
            ).fetchone()
        if row is None or float(row["expires_at"]) < time.time():
            return None
        params = json.loads(row["params_json"])
        return {
            "rid": rid,
            "client_name": str(params.get("client_name") or "MCP client"),
        }

    def complete_consent(self, rid: str, actor: Actor, *, allow: bool) -> str:
        with self._db() as conn:
            row = conn.execute(
                """SELECT client_id, params_json, expires_at FROM mcp_oauth_pending
                   WHERE id=?""",
                (rid,),
            ).fetchone()
            if row is None or float(row["expires_at"]) < time.time():
                raise ValueError("This sign-in request expired. Start again from Cursor.")
            params = json.loads(row["params_json"])
            client_id = str(row["client_id"])
            redirect_uri = str(params["redirect_uri"])
            state = params.get("state")
            conn.execute("DELETE FROM mcp_oauth_pending WHERE id=?", (rid,))
            if not allow:
                return construct_redirect_uri(
                    redirect_uri,
                    error="access_denied",
                    state=state if isinstance(state, str) else None,
                )
            code = secrets.token_urlsafe(32)
            payload = json.dumps(
                {
                    "code_challenge": params["code_challenge"],
                    "redirect_uri": redirect_uri,
                    "redirect_uri_provided_explicitly": bool(
                        params.get("redirect_uri_provided_explicitly")
                    ),
                    "scopes": params.get("scopes") or [MCP_SCOPE],
                    "resource": params.get("resource"),
                    "user_id": actor.user_id,
                    "org_id": actor.org_id,
                }
            )
            conn.execute(
                """INSERT INTO mcp_oauth_codes(
                       code, client_id, user_id, org_id, payload_json, expires_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    code,
                    client_id,
                    actor.user_id,
                    actor.org_id,
                    payload,
                    time.time() + CODE_TTL_SECONDS,
                ),
            )
        extra: dict[str, str | None] = {"code": code}
        if isinstance(state, str):
            extra["state"] = state
        return construct_redirect_uri(redirect_uri, **extra)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> JoelAuthorizationCode | None:
        with self._db() as conn:
            row = conn.execute(
                """SELECT client_id, payload_json, expires_at FROM mcp_oauth_codes
                   WHERE code=?""",
                (authorization_code,),
            ).fetchone()
        if row is None or row["client_id"] != client.client_id:
            return None
        payload = json.loads(row["payload_json"])
        return JoelAuthorizationCode(
            code=authorization_code,
            scopes=list(payload.get("scopes") or [MCP_SCOPE]),
            expires_at=float(row["expires_at"]),
            client_id=client.client_id,
            code_challenge=str(payload["code_challenge"]),
            redirect_uri=AnyUrl(payload["redirect_uri"]),
            redirect_uri_provided_explicitly=bool(
                payload.get("redirect_uri_provided_explicitly")
            ),
            resource=payload.get("resource"),
            subject=f"{payload['user_id']}:{payload['org_id']}",
            user_id=str(payload["user_id"]),
            org_id=int(payload["org_id"]),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: JoelAuthorizationCode
    ) -> OAuthToken:
        with self._db() as conn:
            conn.execute(
                "DELETE FROM mcp_oauth_codes WHERE code=?", (authorization_code.code,)
            )
            return self._mint_tokens(
                conn,
                client_id=client.client_id,
                user_id=authorization_code.user_id,
                org_id=authorization_code.org_id,
                scopes=authorization_code.scopes,
            )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        with self._db() as conn:
            row = conn.execute(
                """SELECT client_id, user_id, org_id, scopes_json, expires_at
                   FROM mcp_oauth_tokens WHERE token_hash=? AND kind='refresh'""",
                (hash_token(refresh_token),),
            ).fetchone()
        if row is None or row["client_id"] != client.client_id:
            return None
        scopes = json.loads(row["scopes_json"])
        expires = row["expires_at"]
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=list(scopes),
            expires_at=int(expires) if expires is not None else None,
            subject=f"{row['user_id']}:{row['org_id']}",
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        user_id, _, org_raw = (refresh_token.subject or "").partition(":")
        org_id = int(org_raw or "0")
        with self._db() as conn:
            conn.execute(
                "DELETE FROM mcp_oauth_tokens WHERE token_hash=?",
                (hash_token(refresh_token.token),),
            )
            return self._mint_tokens(
                conn,
                client_id=client.client_id,
                user_id=user_id,
                org_id=org_id,
                scopes=scopes,
            )

    async def load_access_token(self, token: str) -> AccessToken | None:
        if not token.startswith(ACCESS_PREFIX):
            return None
        with self._db() as conn:
            row = conn.execute(
                """SELECT client_id, user_id, org_id, scopes_json, expires_at
                   FROM mcp_oauth_tokens WHERE token_hash=? AND kind='access'""",
                (hash_token(token),),
            ).fetchone()
        if row is None:
            return None
        expires = row["expires_at"]
        if expires is not None and float(expires) < time.time():
            return None
        scopes = list(json.loads(row["scopes_json"]))
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=scopes,
            expires_at=int(expires) if expires is not None else None,
            subject=f"{row['user_id']}:{row['org_id']}",
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        with self._db() as conn:
            conn.execute(
                "DELETE FROM mcp_oauth_tokens WHERE token_hash=?",
                (hash_token(token.token),),
            )

    def _mint_tokens(
        self,
        conn: sqlite3.Connection,
        *,
        client_id: str,
        user_id: str,
        org_id: int,
        scopes: list[str],
    ) -> OAuthToken:
        now = datetime.now(timezone.utc).isoformat()
        access = ACCESS_PREFIX + secrets.token_urlsafe(32)
        refresh = REFRESH_PREFIX + secrets.token_urlsafe(32)
        scopes_json = json.dumps(scopes)
        t = time.time()
        conn.execute(
            """INSERT INTO mcp_oauth_tokens(
                   token_hash, kind, client_id, user_id, org_id, scopes_json,
                   expires_at, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                hash_token(access),
                "access",
                client_id,
                user_id,
                org_id,
                scopes_json,
                t + ACCESS_TTL_SECONDS,
                now,
            ),
        )
        conn.execute(
            """INSERT INTO mcp_oauth_tokens(
                   token_hash, kind, client_id, user_id, org_id, scopes_json,
                   expires_at, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                hash_token(refresh),
                "refresh",
                client_id,
                user_id,
                org_id,
                scopes_json,
                t + REFRESH_TTL_SECONDS,
                now,
            ),
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TTL_SECONDS,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )


def oauth_starlette_routes(provider: JoelAuthProvider, origin: str) -> list[Any]:
    issuer = AnyHttpUrl(origin)
    resource = AnyHttpUrl(origin.rstrip("/") + "/mcp")
    routes = create_auth_routes(
        provider,
        issuer_url=issuer,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=[MCP_SCOPE],
            default_scopes=[MCP_SCOPE],
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    routes.extend(
        create_protected_resource_routes(
            resource_url=resource,
            authorization_servers=[issuer],
            scopes_supported=[MCP_SCOPE],
            resource_name="joel",
        )
    )
    return routes


def is_oauth_http_path(path: str) -> bool:
    if path.startswith("/.well-known/oauth-"):
        return True
    return path in {"/authorize", "/token", "/register", "/revoke"}


__all__ = [
    "ACCESS_PREFIX",
    "JoelAuthProvider",
    "JoelAuthorizationCode",
    "MCP_SCOPE",
    "actor_from_oauth_access",
    "is_oauth_http_path",
    "oauth_starlette_routes",
    "resource_metadata_url",
]
