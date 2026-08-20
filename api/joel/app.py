"""Joel API — bootable app surface over SQLite (§12.2).

Hydra / ingest / retrieval stay stubs for now; the product UI is fully
wired against these endpoints with empty corpus semantics.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

# Every scripts/check_*.py loads .env itself before touching Settings.from_env()
# or Composio; this app is normally started directly via `uvicorn joel.app:app`
# with no such wrapper, so HYDRA_HTTP/HYDRA_BOLT/HYDRA_TOKEN/COMPOSIO_API_KEY
# etc. must be loaded here instead — otherwise _runtime()'s first real call
# (e.g. the first /api/ask) raises a raw KeyError deep in Settings.from_env()
# the moment retrieval actually needs Hydra, no matter how well *that* call
# path degrades LLM/network failures elsewhere.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import anyio
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from joel.adapters import triage_batch
from joel.agent.live import (
    TIMEOUT_SECONDS as LIVE_TIMEOUT_SECONDS,
    GitHubItemTarget,
    detect_live_targets,
    fetch_live_target,
)
from joel.agent.working_memory import Turn, answer_meta, load_recent_turns, rewrite_question
from joel.connectors.composio_conn import (
    ComposioError,
    find_active_account,
    get_composio,
    list_connected_accounts,
    mask_api_key,
    proxy_call,
    resolve_composio_key,
    slack_proxy_call,
    start_toolkit_connect,
)
from joel import mail as joel_mail
from joel.connectors.gate import (
    INGEST_PROVIDERS,
    INTEGRATION_BY_ID,
    INTEGRATION_BY_TOOLKIT,
    INTEGRATIONS,
    LOOKBACK_DAYS,
    IntegrationDef,
    require_connectable,
)
from joel.connectors.oauth import (
    OAuthError,
    decrypt_credentials,
    encrypt_credentials,
    validate_return_to,
)
from joel.syncer import (
    ingest_is_schedulable,
    next_retry_at,
    release_running_jobs,
    start_scheduler,
)
from joel import auth as joel_auth
from joel import identity
from joel.mcp_server import build_mcp_app
from joel.slack_bot import SeenEvents, parse_app_mention, post_reply, strip_mention, verify_signature
from joel.connectors.catalog import (
    ProviderAPIError,
    fetch_gdrive_docs,
    fetch_hubspot_docs,
    fetch_linear_docs,
    fetch_notion_docs,
)
from joel.connectors.confluence import fetch_confluence_docs
from joel.connectors.fireflies import fetch_fireflies_docs
from joel.connectors.jira import fetch_jira_docs
from joel.connectors.gmail import GmailAPIError, fetch_gmail_docs
from joel.connectors.github import GITHUB_ACCEPT, GitHubAPIError, fetch_github_docs
from joel.connectors.slack import (
    SlackAPIError,
    SlackClient,
    fetch_slack_docs,
    slack_channels_floor,
)
from joel.config import Settings, hydra_namespace_for
from joel.hydra import Hydra
from joel.live_index import LiveIndex
from joel.llm import make_openrouter_caller
from joel.membership import member_channel_stamps, sync_slack_channel_memberships
from joel.models import CanonicalDoc
from joel.pipeline import run_store_pipeline
from joel.retrieve import RetrievalTrace, answer_question, log_trace
from joel.retrieve.planner import QueryPlan
from joel.store import HydraStore
from joel.store_sql import remove_docs
from joel.visibility import AskContext, Visibility, apply as apply_visibility

DATA_DIR = Path(os.getenv("JOEL_DATA", "data"))
DB_PATH = DATA_DIR / "index" / "joel.db"

# Store-layer singletons (Hydra driver, HydraStore, LiveIndex, embedding
# model) -- built lazily on first real use, never at import time, so
# anything that only needs SQLite (most of the test scripts, most routes)
# never pays for a Hydra connection or a model load. Long-lived by design:
# Hydra's driver and the embedding model are meant to be constructed once
# and reused, not per-request.
#
# Mode B: LiveIndex and HydraStore are cached per org_id (separate npz
# files and Hydra namespaces). Embed model + base Settings stay shared.
_RUNTIME: dict[str, Any] = {}
_RUNTIME_LOCK = threading.Lock()


def _runtime() -> dict[str, Any]:
    with _RUNTIME_LOCK:
        if "embed_model" not in _RUNTIME:
            from sentence_transformers import SentenceTransformer

            settings = Settings.from_env()
            _RUNTIME["settings"] = settings
            _RUNTIME["embed_model"] = SentenceTransformer(settings.embed_model)
            _RUNTIME["live_indexes"] = {}
            _RUNTIME["hydra_stores"] = {}
        return _RUNTIME


def _live_index_for(org_id: int) -> LiveIndex:
    """Per-org vector index at `index/org-{org_id}.npz`.

    On first use for org 1, copies legacy `joel.npz` if present so existing
    installs keep their vectors without a rebuild.
    """
    rt = _runtime()
    with _RUNTIME_LOCK:
        indexes: dict[int, LiveIndex] = rt["live_indexes"]
        if org_id not in indexes:
            index_dir = DATA_DIR / "index"
            index_dir.mkdir(parents=True, exist_ok=True)
            path = index_dir / f"org-{org_id}.npz"
            legacy = index_dir / "joel.npz"
            if org_id == 1 and not path.exists() and legacy.exists():
                shutil.copy2(legacy, path)
            dim = rt["embed_model"].get_sentence_embedding_dimension()
            indexes[org_id] = LiveIndex(path, dim=dim)
        return indexes[org_id]


def _hydra_store_for(org_id: int) -> HydraStore:
    """Per-org HydraStore with `X-Graph-Namespace: joel-org-{org_id}`."""
    rt = _runtime()
    with _RUNTIME_LOCK:
        stores: dict[int, HydraStore] = rt["hydra_stores"]
        if org_id not in stores:
            settings = rt["settings"].for_org(org_id)
            assert settings.hydra_namespace == hydra_namespace_for(org_id)
            hydra = Hydra(settings)
            stores[org_id] = HydraStore(hydra)
        return stores[org_id]


# `run_lanes` (retrieve/lanes.py) deliberately runs its lanes concurrently
# via ThreadPoolExecutor, and two of them (vector + vec-artifacts) both call
# this on the *same* SentenceTransformer instance for the same question.
# torch's CPU/MPS inference path isn't safe against concurrent `.encode()`
# calls from separate Python threads on one model instance — hitting it that
# way segfaults the whole worker process (reproduced live: a real /api/ask
# call against the real embedding model crashed the server, not just raised
# a catchable exception, which the try/except around answer_question in the
# /api/ask route can't help with). Serialize with a lock; embedding a few
# short strings is fast enough that this isn't a real throughput bottleneck.
_EMBED_LOCK = threading.Lock()


def _embed_fn(texts: list[str]):
    with _EMBED_LOCK:
        return _runtime()["embed_model"].encode(texts, normalize_embeddings=True)

PROVIDER_LABELS = {item.id: item.name for item in INTEGRATIONS}
DEFAULT_INTERVAL = {item.id: item.default_interval_min for item in INTEGRATIONS}
RETURN_PATHS = {
    "connectors": "/integrations",
    "integrations": "/integrations",
    "onboarding": "/onboarding/tools",
}

DEFAULT_SETTINGS: dict[str, str] = {
    "llm_base_url": "https://openrouter.ai/api/v1",
    "llm_api_key": "",
    "llm_model_distill": "anthropic/claude-sonnet-4.5",
    "llm_model_extract": "anthropic/claude-sonnet-4.5",
    "llm_model_answer": "anthropic/claude-sonnet-4.5",
    "llm_model_resolve": "anthropic/claude-haiku-4.5",
    "llm_model_rerank": "anthropic/claude-haiku-4.5",
    "sync_enabled": "true",
    "sync_max_concurrent_jobs": "2",
    "sync_default_interval_min": "15",
    "history_floor": "",
    "composio_api_key": "",
    "embed_model": "BAAI/bge-small-en-v1.5",
    "slack_signing_secret": "",
    # Outbound email — optional. none | smtp | resend
    "mail_provider": "none",
    "mail_from": "",
    "mail_from_name": "joel",
    "mail_app_url": "",
    "mail_smtp_host": "",
    "mail_smtp_port": "587",
    "mail_smtp_user": "",
    "mail_smtp_password": "",
    "mail_smtp_tls": "true",
    "mail_resend_api_key": "",
}


def _is_secret_setting(key: str) -> bool:
    return key.endswith(("key", "secret", "password"))


def _public_app_url(request: Request, settings: dict[str, str]) -> str:
    """Join-link origin for invite emails.

    Prefer the explicit mail_app_url setting, then the browser Origin/Referer
    on the invite request, then JOEL_WEB_ORIGIN (same fallback as OAuth).
    """
    configured = (settings.get("mail_app_url") or "").strip()
    if configured:
        return configured.rstrip("/")
    for header in ("origin", "referer"):
        raw = (request.headers.get(header) or "").strip()
        if not raw:
            continue
        parts = urlsplit(raw)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    return os.getenv("JOEL_WEB_ORIGIN", "http://localhost:3000").rstrip("/")


def _cors_origins() -> list[str]:
    primary = os.getenv("JOEL_WEB_ORIGIN", "http://localhost:3000").rstrip("/")
    origins = [primary, "http://localhost:3000", "http://127.0.0.1:3000"]
    # Preserve order, drop dupes.
    seen: set[str] = set()
    out: list[str] = []
    for origin in origins:
        if origin and origin not in seen:
            seen.add(origin)
            out.append(origin)
    return out


def _cookie_secure() -> bool:
    return os.getenv("JOEL_HTTPS", "").strip().lower() in {"1", "true", "yes"}


def _send_invite_email(
    settings: dict[str, str],
    *,
    email: str,
    role: str,
    token: str,
    workspace_name: str,
    app_url: str,
) -> tuple[bool, str | None]:
    """Attempt invite email. Returns (sent, error_message)."""
    if not joel_mail.is_configured(settings):
        return False, None
    join_url = f"{app_url.rstrip('/')}/join?token={token}"
    try:
        joel_mail.try_send(
            settings,
            joel_mail.invite_email(
                to=email,
                workspace_name=workspace_name,
                role=role,
                join_url=join_url,
                expires_days=identity.INVITE_DAYS,
            ),
        )
    except joel_mail.MailError as exc:
        return False, str(exc)
    return True, None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def run_migrations(conn: sqlite3.Connection) -> None:
    """Numbered SQL files in `migrations/`, applied in order, each inside
    its own transaction (§14.3). `schema_version` is the one unavoidable
    `CREATE TABLE IF NOT EXISTS` in this codebase -- there is no way to ask
    "which migrations have already run" before the table that answers that
    question exists, and every migration framework (Rails, Django, Alembic)
    carries the identical bootstrap exception for its own ledger table.
    Every *application* table below this point comes from a numbered file.
    """
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version(version) VALUES (0)")
        current = 0
    else:
        current = row[0]

    for path in sorted(MIGRATIONS_DIR.glob("[0-9]*.sql")):
        version = int(path.name.split("_", 1)[0])
        if version <= current:
            continue
        # Each file wraps itself in its own BEGIN/COMMIT (executescript runs
        # the file's text verbatim rather than adding its own transaction
        # machinery, so a mid-script failure rolls back to the file's own
        # BEGIN and this migration is retried whole on the next boot).
        conn.executescript(path.read_text())
        conn.execute("UPDATE schema_version SET version = ?", (version,))
        current = version


def seed_org_defaults(conn: sqlite3.Connection, org_id: int) -> None:
    """Seed default settings and spend rows for an org."""
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(org_id, key, value) VALUES (?, ?, ?)",
            (org_id, k, v),
        )
    for stage in ("distill", "extract", "answer", "resolve", "rerank"):
        conn.execute(
            "INSERT OR IGNORE INTO spend(org_id, stage, calls) VALUES (?, ?, 0)",
            (org_id, stage),
        )


def init_db() -> None:
    with db() as conn:
        run_migrations(conn)
        # Seed defaults for existing orgs (backward compat)
        # Don't seed if no orgs exist yet (fresh install, setup will create org 1)
        org_ids = [r["id"] for r in conn.execute("SELECT id FROM orgs")]
        for org_id in org_ids:
            seed_org_defaults(conn, org_id)


def _settings_map(conn: sqlite3.Connection, org_id: int | None = None) -> dict[str, str]:
    """Get settings for org. Falls back to org_id=1 for backward compat."""
    if org_id is None:
        org_id = 1
    return {
        r["key"]: r["value"]
        for r in conn.execute(
            "SELECT key, value FROM settings WHERE org_id=?", (org_id,)
        )
    }


def _checklist_default() -> dict[str, bool]:
    return {
        "fetched": False,
        "distilled": False,
        "people_resolved": False,
        "graph_linked": False,
        "indexes_consistent": False,
        "ready": False,
    }


def _parse_checklist(raw: str) -> dict[str, bool]:
    data = json.loads(raw or "{}")
    base = _checklist_default()
    base.update({k: bool(data.get(k, False)) for k in base})
    return base


def _persist_canonical_docs(
    conn: sqlite3.Connection, docs: list[CanonicalDoc], *, org_id: int
) -> tuple[dict[str, int], list[CanonicalDoc]]:
    """Append new/changed canonical lines and update the disposable docs
    index. Returns (counts, dirty_docs) — dirty_docs (new+changed) is what
    the store pipeline (pipeline.py) needs to know what to upsert/re-distill;
    unchanged docs need no further work downstream."""
    rows = conn.execute(
        "SELECT id, content_hash, forgotten FROM docs WHERE org_id=?", (org_id,)
    ).fetchall()
    forgotten_ids = {r["id"] for r in rows if r["forgotten"]}
    known = {
        r["id"]: r["content_hash"]
        for r in rows
        if not r["forgotten"]
    }
    ignored_forgotten = sum(doc.doc_id in forgotten_ids for doc in docs)
    docs = [apply_visibility(doc) for doc in docs if doc.doc_id not in forgotten_ids]
    report = triage_batch(docs, known)
    seen_at = _now()
    for doc in report.unchanged:
        conn.execute(
            "UPDATE docs SET last_seen=? WHERE id=? AND org_id=?",
            (seen_at, doc.doc_id, org_id),
        )

    canonical_dir = DATA_DIR / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    by_source: dict[str, list[CanonicalDoc]] = {}
    for doc in [*report.new, *report.changed]:
        by_source.setdefault(doc.source_type, []).append(doc)
        first_seen = doc.first_seen.isoformat() if doc.first_seen else seen_at
        conn.execute(
            """INSERT INTO docs(
                 id, source_type, external_id, title, body, content_hash, url,
                 timestamp, thread_id, parent_id, author_raw, container,
                 extra_json, first_seen, last_seen, forgotten, visibility, org_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, body=excluded.body,
                 content_hash=excluded.content_hash, url=excluded.url,
                 timestamp=excluded.timestamp, thread_id=excluded.thread_id,
                 parent_id=excluded.parent_id, author_raw=excluded.author_raw,
                 container=excluded.container, extra_json=excluded.extra_json,
                 last_seen=excluded.last_seen, forgotten=0,
                 visibility=excluded.visibility, org_id=excluded.org_id""",
            (
                doc.doc_id,
                doc.source_type,
                doc.external_id,
                doc.title,
                doc.body,
                doc.content_hash,
                doc.url,
                doc.timestamp.isoformat() if doc.timestamp else None,
                doc.thread_id,
                doc.parent_id,
                doc.author_raw,
                doc.container,
                json.dumps(doc.extra),
                first_seen,
                seen_at,
                doc.visibility,
                org_id,
            ),
        )
    for source_type, source_docs in by_source.items():
        with (canonical_dir / f"{source_type}.jsonl").open("a") as handle:
            for doc in source_docs:
                line = doc.model_copy(
                    update={
                        "first_seen": doc.first_seen
                        or datetime.now(timezone.utc),
                        "last_seen": datetime.now(timezone.utc),
                    }
                ).model_dump_json()
                handle.write(line + "\n")
    counts = report.counts
    counts["unchanged"] += ignored_forgotten
    return counts, [*report.new, *report.changed]


def _credential(conn: sqlite3.Connection, connection_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT encrypted_json FROM connector_credentials WHERE connection_id=?",
        (connection_id,),
    ).fetchone()
    if row is None:
        raise OAuthError("Connector credentials are missing")
    return decrypt_credentials(row["encrypted_json"], DATA_DIR)


def _slack_caller(
    credentials: dict[str, Any],
    settings: dict[str, str],
) -> Callable[[str, dict[str, Any]], dict[str, Any]] | None:
    account_id = credentials.get("composio_account_id")
    if not account_id:
        return None
    composio = get_composio(settings)

    def call(method: str, params: dict[str, Any]) -> dict[str, Any]:
        return slack_proxy_call(composio, str(account_id), method, params)

    return call


def _slack_token(credentials: dict[str, Any]) -> str:
    if credentials.get("composio_account_id"):
        return ""
    token = str(credentials.get("access_token") or "")
    if "…" in token or "..." in token:
        raise SlackAPIError("invalid_auth")
    return token


def _proxy_error_message(data: Any, status: int) -> str:
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str) and err:
            return err
        if data.get("message"):
            return str(data["message"])
    return f"HTTP {status}"


def _provider_request(
    credentials: dict[str, Any],
    settings: dict[str, str],
    error_cls: type,
    extra_headers: dict[str, str] | None = None,
) -> Callable[..., tuple[Any, dict[str, str]]]:
    account_id = credentials.get("composio_account_id")
    if not account_id:
        raise error_cls("missing connected account", status=401)
    composio = get_composio(settings)

    def request(
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> tuple[Any, dict[str, str]]:
        result = proxy_call(
            composio,
            str(account_id),
            endpoint,
            method=method,
            params=params or {},
            headers=extra_headers,
            body=body,
        )
        if result.status >= 400:
            raise error_cls(
                _proxy_error_message(result.data, result.status),
                status=result.status,
            )
        return result.data, result.headers

    return request


def _is_reauth(exc: BaseException) -> bool:
    if isinstance(exc, SlackAPIError) and exc.error in {
        "invalid_auth",
        "account_inactive",
        "token_expired",
        "token_revoked",
    }:
        return True
    if getattr(exc, "status", None) in {401, 403}:
        return True
    text = str(exc).lower()
    return any(
        token in text
        for token in ("invalid_auth", "unauthorized", "invalid credentials")
    )


# ── request bodies ──────────────────────────────────────────────────────────


class ConnectorIn(BaseModel):
    provider: str
    mode: str = "composio"


class ConnectorPatch(BaseModel):
    interval_min: int | None = None
    paused: bool | None = None
    lookback_days: int | None = None
    channel_ids: list[str] | None = None


class ComposioKeyIn(BaseModel):
    api_key: str | None = None


class ComposioConnectIn(BaseModel):
    toolkit: str
    return_to: str = "connectors"
    origin: str
    lookback_days: int = 30
    auth_config_id: str | None = None
    personal: bool = False


class ConversationIn(BaseModel):
    title: str | None = None


class AskIn(BaseModel):
    conversation_id: str
    question: str


class ProfileIn(BaseModel):
    display_name: str | None = None


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


class SettingsIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class WipeIn(BaseModel):
    domain: str


class SetupIn(BaseModel):
    email: str
    password: str
    display_name: str = ""
    domain: str | None = None
    name: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class InviteIn(BaseModel):
    email: str
    role: str = "member"


class TestEmailIn(BaseModel):
    to: str = ""


class AcceptInviteIn(BaseModel):
    password: str | None = None
    display_name: str = ""


class MemberRoleIn(BaseModel):
    role: str


class WorkspacePatch(BaseModel):
    domain: str | None = None
    name: str | None = None


# ── app ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="joel-api", version="0.1.0")

SESSION_COOKIE = joel_auth.SESSION_COOKIE


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        max_age=identity.SESSION_DAYS * 86400,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def _identity_error(exc: identity.IdentityError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


def _request_identity(request: Request) -> joel_auth.RequestIdentity:
    who = getattr(request.state, "identity", None)
    if isinstance(who, joel_auth.RequestIdentity):
        return who
    return joel_auth.RequestIdentity(session_id=None, user_id=None, actor=None)


def _require_actor(request: Request) -> identity.Actor:
    actor = getattr(request.state, "actor", None)
    if not isinstance(actor, identity.Actor):
        raise HTTPException(401, "Not signed in")
    return actor


def _require_session_user(request: Request) -> tuple[str, str]:
    """Signed-in person, even with no active workspace. Returns (session_id, user_id)."""
    who = _request_identity(request)
    if not who.session_id or not who.user_id:
        raise HTTPException(401, "Not signed in")
    return who.session_id, who.user_id


def _require_admin(request: Request) -> identity.Actor:
    actor = _require_actor(request)
    if not actor.is_admin:
        raise HTTPException(403, "Only an admin can do that")
    return actor


def _require_connection_mutate(
    request: Request, row: sqlite3.Row
) -> identity.Actor:
    """Org connectors: admin only. Personal: owner or admin. Always same org."""
    actor = _require_actor(request)
    row_org = int(row["org_id"]) if "org_id" in row.keys() and row["org_id"] is not None else 1
    if row_org != actor.org_id:
        raise HTTPException(404, "Not found")
    owned_by = row["owned_by"] if "owned_by" in row.keys() else None
    if owned_by is None:
        if not actor.is_admin:
            raise HTTPException(403, "Only an admin can manage org connectors")
    elif owned_by != actor.user_id and not actor.is_admin:
        raise HTTPException(403, "Not your connector")
    return actor


def _auth_payload(
    conn: sqlite3.Connection,
    actor: identity.Actor | None,
    *,
    workspaces: list[dict[str, Any]] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Build auth status payload.
    
    States:
    - setup: no users exist
    - login: no session or expired
    - pick_workspace: session valid but active_org_id is null (multi-org user)
    - ok: authenticated with active workspace
    """
    if identity.setup_needed(conn):
        state = "setup"
        workspace = None
    elif actor is None and workspaces:
        # Session valid but no active_org_id (pick_workspace state)
        state = "pick_workspace"
        workspace = None
    elif actor is None:
        state = "login"
        workspace = None
    else:
        state = "ok"
        workspace = identity.workspace_public(conn, actor.org_id)
    return {
        "state": state,
        "me": None if actor is None else identity.actor_dict(actor),
        "workspace": workspace,
        "workspaces": workspaces,
    }


class SessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        needed = joel_auth.classify(request.method, request.url.path)
        with db() as conn:
            who = joel_auth.resolve(conn, request.cookies.get(SESSION_COOKIE))
        request.state.identity = who
        request.state.actor = who.actor
        if joel_auth.unauthorized(who, needed):
            return JSONResponse({"detail": "Not signed in"}, status_code=401)
        return await call_next(request)


app.add_middleware(SessionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _mcp_actor_resolver(raw_key: str) -> identity.Actor | None:
    with db() as conn:
        return identity.actor_from_api_key(conn, raw_key)

_ready_timers: dict[str, threading.Thread] = {}
_scheduler_stop: threading.Event | None = None


def _scheduler_tick() -> None:
    with db() as conn:
        now = _now()
        # status IN ('ready','error'): an errored connector must come back
        # for retry once its backoff window (§11.2) elapses via
        # next_sync_at, not sit invisible to the scheduler forever.
        # needs_reauth is deliberately excluded — only a reconnect flips
        # that back to 'ready'.
        rows = conn.execute(
            """SELECT id, provider, channel_ids_json, org_id FROM connections
               WHERE paused=0 AND status IN ('ready','error')
                 AND next_sync_at IS NOT NULL AND next_sync_at<=?
                 AND id NOT IN (SELECT connection_id FROM jobs WHERE status='running')
               ORDER BY next_sync_at
               LIMIT 32""",
            (now,),
        ).fetchall()
        running = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE status='running'"
        ).fetchone()["n"]

    started = 0
    for row in rows:
        org_id = int(row["org_id"] or 1)
        with db() as conn:
            settings = _settings_map(conn, org_id)
        if settings.get("sync_enabled", "true").lower() in {"0", "false", "no"}:
            continue
        try:
            max_concurrent = max(1, int(settings.get("sync_max_concurrent_jobs", "2")))
        except ValueError:
            max_concurrent = 2
        if running + started >= max_concurrent:
            break
        provider = str(row["provider"])
        if provider not in INGEST_PROVIDERS:
            continue
        if not ingest_is_schedulable(provider, _channel_ids(row)):
            continue
        try:
            _start_ingest(row["id"], first_sync=False, provider=provider)
            started += 1
        except Exception:
            continue

    # §11.3: deep backfill only ever runs with capacity left over after
    # every due incremental sync above has started -- "yields immediately
    # when [an incremental sync] becomes due" is enforced structurally by
    # ordering (incremental first, this second) plus jobs' own
    # one-running-job-per-connection guard, not by preempting a page
    # mid-flight.
    deep_capacity = max(0, 2 - running - started)
    if deep_capacity <= 0:
        return
    with db() as conn:
        placeholders = ",".join("?" * len(DEEP_BACKFILL_PROVIDERS))
        deep_rows = conn.execute(
            f"""SELECT id, provider, org_id FROM connections
                WHERE paused=0 AND status='ready' AND backfill_done=0
                  AND backfill_cursor IS NOT NULL AND provider IN ({placeholders})
                  AND id NOT IN (SELECT connection_id FROM jobs WHERE status='running')
                LIMIT ?""",
            (*DEEP_BACKFILL_PROVIDERS, deep_capacity),
        ).fetchall()
    for row in deep_rows:
        org_id = int(row["org_id"] or 1)
        with db() as conn:
            settings = _settings_map(conn, org_id)
        if settings.get("sync_enabled", "true").lower() in {"0", "false", "no"}:
            continue
        try:
            _start_deep_backfill(row["id"], provider=str(row["provider"]))
        except Exception:
            continue


@app.on_event("startup")
def _startup() -> None:
    global _scheduler_stop
    init_db()
    with db() as conn:
        release_running_jobs(conn, now=_now(), job_error="worker restarted")
    if _scheduler_stop is None:
        _scheduler_stop = start_scheduler(_scheduler_tick, interval_sec=30)


def _channel_ids(row: sqlite3.Row) -> list[str]:
    if "channel_ids_json" not in row.keys():
        return []
    try:
        raw = json.loads(row["channel_ids_json"] or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _row_connector(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"],
        "provider": r["provider"],
        "label": PROVIDER_LABELS.get(r["provider"], r["provider"]),
        "status": r["status"],
        "mode": r["mode"],
        "doc_count": r["doc_count"],
        "last_sync_at": r["last_sync_at"],
        "next_sync_at": r["next_sync_at"],
        "backfill_done": bool(r["backfill_done"]),
        "backfill_progress": r["backfill_progress"],
        "backfill_cursor": r["backfill_cursor"] if "backfill_cursor" in r.keys() else None,
        "error": r["error"],
        "interval_min": r["interval_min"],
        "lookback_days": r["lookback_days"] if "lookback_days" in r.keys() else 30,
        "channel_ids": _channel_ids(r),
        "coming_soon": False,
        "ingest": r["provider"] in INGEST_PROVIDERS,
        "checklist": _parse_checklist(r["checklist_json"]),
        "sync_started_at": None,
    }


def _fetch_provider_docs(
    provider: str,
    credentials: dict[str, Any],
    settings: dict[str, str],
    row: sqlite3.Row | None,
) -> list[CanonicalDoc]:
    lookback_days = 30
    if row is not None:
        try:
            lookback_days = int(row["lookback_days"] or 30)
        except (TypeError, ValueError, KeyError):
            lookback_days = 30
    oldest_dt = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    since = oldest_dt.isoformat().replace("+00:00", "Z")
    if provider == "slack":
        channel_ids = _channel_ids(row) if row is not None else []
        if not channel_ids:
            raise RuntimeError("Pick at least one Slack channel before syncing")
        return fetch_slack_docs(
            _slack_token(credentials),
            oldest=str(oldest_dt.timestamp()),
            channel_ids=channel_ids,
            caller=_slack_caller(credentials, settings),
        ).docs
    if provider == "github":
        return fetch_github_docs(
            since=since,
            request=_provider_request(
                credentials,
                settings,
                GitHubAPIError,
                extra_headers={"Accept": GITHUB_ACCEPT},
            ),
        )
    if provider == "gmail":
        return fetch_gmail_docs(
            after=oldest_dt,
            request=_provider_request(credentials, settings, GmailAPIError),
        )
    account_id = credentials.get("composio_account_id")
    if provider in {"jira", "confluence", "fireflies"}:
        if not account_id:
            raise ProviderAPIError("missing connected account", status=401)
        composio = get_composio(settings)
        account_id = str(account_id)
        if provider == "jira":
            return fetch_jira_docs(
                since=since, composio=composio, account_id=account_id
            )
        if provider == "confluence":
            return fetch_confluence_docs(
                since=since, composio=composio, account_id=account_id
            )
        return fetch_fireflies_docs(
            after=oldest_dt, composio=composio, account_id=account_id
        )
    headers = {
        "linear": {"Content-Type": "application/json"},
        "notion": {"Notion-Version": "2022-06-28"},
    }.get(provider)
    request = _provider_request(
        credentials, settings, ProviderAPIError, extra_headers=headers
    )
    if provider == "linear":
        return fetch_linear_docs(since=since, request=request)
    if provider == "notion":
        return fetch_notion_docs(since=since, request=request)
    if provider == "googledrive":
        return fetch_gdrive_docs(since=since, request=request)
    if provider == "hubspot":
        return fetch_hubspot_docs(since=since, request=request)
    raise RuntimeError(f"Ingest for {provider} isn’t shipped yet")


# §11.3 progressive deep backfill: the fast pass above gets a connector
# ready in minutes on a fixed lookback window; this is the second,
# backward-walking pass that eventually reaches the account's true
# beginning. Built for slack and gmail today -- both have a natural
# symmetric upper bound (`latest`/`before:`) on top of their existing
# lower bound. The other providers stay on the fast-pass-only behavior
# that already shipped (honest scope, not a shortcut: PLAN.md documents
# which providers have the deep pass and which don't, same as CP10's "2 of
# 4 live-lookup ops implemented").
DEEP_BACKFILL_PROVIDERS = {"slack", "gmail"}
DEEP_BACKFILL_PAGE_DAYS = 90
# Gmail has no cheap "mailbox creation date" signal the way a Slack
# channel's own `created` field gives one -- so it gets a user-set floor
# per §11.3's own wording ("...or a user-set floor") instead of a true
# provider-reported beginning.
DEEP_BACKFILL_GMAIL_FLOOR_DAYS = 730

# §0.3/§1.4 personal connectors: mailbox/DM-shaped providers, where "who
# owns this connection" already maps onto Supermemory's own
# personal-then-org-shared model -- a second Gmail inbox or a second
# Slack identity is naturally ONE PERSON's, never the org's. Company-wide
# doc stores (Notion, Drive, ...) stay org-shared only; this allowlist is
# checked server-side (never trust the client for a scope decision), same
# principle as AskContext always being built server-side.
PERSONAL_CONNECTOR_PROVIDERS = {"gmail", "slack"}


def _deep_backfill_floor(
    provider: str, credentials: dict[str, Any], settings: dict[str, str], row: sqlite3.Row | None
) -> datetime:
    if provider == "slack":
        channel_ids = _channel_ids(row) if row is not None else []
        floor_ts = slack_channels_floor(
            _slack_token(credentials), channel_ids=channel_ids, caller=_slack_caller(credentials, settings)
        )
        if floor_ts is not None:
            return datetime.fromtimestamp(floor_ts, timezone.utc)
    return datetime.now(timezone.utc) - timedelta(days=DEEP_BACKFILL_GMAIL_FLOOR_DAYS)


def _fetch_provider_docs_deep(
    provider: str,
    credentials: dict[str, Any],
    settings: dict[str, str],
    row: sqlite3.Row | None,
    *,
    since: datetime,
    until: datetime,
) -> list[CanonicalDoc]:
    if provider == "slack":
        channel_ids = _channel_ids(row) if row is not None else []
        if not channel_ids:
            return []
        return fetch_slack_docs(
            _slack_token(credentials),
            oldest=str(since.timestamp()),
            latest=str(until.timestamp()),
            channel_ids=channel_ids,
            caller=_slack_caller(credentials, settings),
        ).docs
    if provider == "gmail":
        return fetch_gmail_docs(
            after=since,
            before=until,
            request=_provider_request(credentials, settings, GmailAPIError),
        )
    raise RuntimeError(f"Deep backfill for {provider} isn't implemented yet")


def _job_running(job_id: str) -> bool:
    with db() as conn:
        row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
    return row is not None and row["status"] == "running"


def _run_ingest(
    connection_id: str, job_id: str, *, first_sync: bool, provider: str
) -> None:
    started = time.monotonic()
    try:
        with db() as conn:
            credentials = _credential(conn, connection_id)
            row = conn.execute(
                "SELECT lookback_days, channel_ids_json, org_id FROM connections WHERE id=?",
                (connection_id,),
            ).fetchone()
            org_id = int(row["org_id"] or 1) if row is not None else 1
            settings = _settings_map(conn, org_id)
        lookback_days = int(row["lookback_days"] or 30) if row is not None else 30
        docs = _fetch_provider_docs(provider, credentials, settings, row)
        if provider == "slack":
            try:
                with db() as conn:
                    sync_slack_channel_memberships(
                        conn,
                        channel_ids=_channel_ids(row) if row is not None else [],
                        token=_slack_token(credentials),
                        caller=_slack_caller(credentials, settings),
                        now=_now(),
                        org_id=org_id,
                    )
            except Exception:
                # Membership is a read-widening convenience (§1.4), never
                # load-bearing for the sync itself — a scope/permission gap
                # here must not fail an otherwise-good ingest.
                logging.getLogger(__name__).exception(
                    "channel membership sync failed for connection %s", connection_id
                )
        if not _job_running(job_id):
            return
        with db() as conn:
            counts, dirty_docs = _persist_canonical_docs(conn, docs, org_id=org_id)
            row = conn.execute(
                "SELECT checklist_json FROM connections WHERE id=?", (connection_id,)
            ).fetchone()
            if row is None:
                return
            checklist = _parse_checklist(row["checklist_json"])
            checklist["fetched"] = True
            conn.execute(
                """UPDATE connections SET status='distilling', checklist_json=?,
                   backfill_progress=?, doc_count=?, error=NULL WHERE id=?""",
                (
                    json.dumps(checklist),
                    0.35 if first_sync else None,
                    conn.execute(
                        """SELECT COUNT(*) AS n FROM docs
                           WHERE source_type=? AND forgotten=0 AND org_id=?""",
                        (provider, org_id),
                    ).fetchone()["n"],
                    connection_id,
                ),
            )

        # Store pipeline (§8/CP5) + distillation (§7/CP4) for whatever was
        # new or changed this sync — real work now, not a checklist-only
        # stub. Runs regardless of first_sync since dirty threads can show
        # up on any sync. A failure here is recorded but does not fail the
        # job: the fetch already landed durably in `docs`/canonical JSONL,
        # and there's no per-destination retry ledger yet (§8.2, still on
        # CP5's deferred list) so the honest thing is to surface it rather
        # than silently drop it or crash a sync that otherwise succeeded.
        pipeline_error: str | None = None
        try:
            if dirty_docs:
                llm_call = (
                    make_openrouter_caller(settings) if settings.get("llm_api_key") else None
                )
                with db() as conn:
                    pipeline_report = run_store_pipeline(
                        conn,
                        _live_index_for(org_id),
                        _hydra_store_for(org_id),
                        _embed_fn,
                        llm_call,
                        dirty_docs,
                        data_dir=DATA_DIR,
                        org_id=org_id,
                    )
                errors = [*pipeline_report.distill_errors, *pipeline_report.ontology.extract_errors]
                if errors:
                    pipeline_error = "; ".join(errors[:3])
        except Exception as exc:  # store/distill failure must not sink an otherwise-good sync
            pipeline_error = str(exc)

        # distilled, people_resolved, graph_linked and indexes_consistent are
        # all real now (the pipeline call above runs distillation AND
        # ontology extraction/resolution/reconciliation synchronously) —
        # the sleep below is cosmetic onboarding pacing only, so the first-
        # sync checklist doesn't flash through four steps in one frame.
        if first_sync:
            for key, status, progress in (
                ("distilled", "distilling", 0.55),
                ("people_resolved", "linking", 0.72),
                ("graph_linked", "linking", 0.88),
                ("indexes_consistent", "ready", 1.0),
            ):
                if not _job_running(job_id):
                    return
                if key in ("people_resolved", "graph_linked"):
                    time.sleep(0.4)
                if not _job_running(job_id):
                    return
                with db() as conn:
                    row = conn.execute(
                        "SELECT checklist_json FROM connections WHERE id=?",
                        (connection_id,),
                    ).fetchone()
                    if row is None:
                        return
                    checklist = _parse_checklist(row["checklist_json"])
                    checklist[key] = True
                    if key == "indexes_consistent":
                        checklist["ready"] = True
                    conn.execute(
                        """UPDATE connections SET status=?, checklist_json=?,
                           backfill_progress=? WHERE id=?""",
                        (
                            status,
                            json.dumps(checklist),
                            None if checklist["ready"] else progress,
                            connection_id,
                        ),
                    )

        if not _job_running(job_id):
            return
        finished = _now()
        with db() as conn:
            interval = conn.execute(
                "SELECT interval_min FROM connections WHERE id=?", (connection_id,)
            ).fetchone()["interval_min"]
            # §11.3: a provider with a real deep-backfill pass starts that
            # pass fresh (backfill_done=0, cursor = the fast pass's own
            # floor) the first time it goes ready, instead of the old
            # unconditional backfill_done=1 that made the field mean
            # nothing more than "first sync happened." Every other
            # provider, and every non-first sync of a deep-backfill
            # provider, leaves both columns untouched -- the deep-backfill
            # job (if any) owns them from here on, not the incremental
            # sync path.
            if first_sync and provider in DEEP_BACKFILL_PROVIDERS:
                backfill_clause = "backfill_done=0, backfill_progress=NULL, backfill_cursor=?,"
                backfill_params: tuple[Any, ...] = (
                    (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat(),
                )
            elif first_sync:
                backfill_clause = "backfill_done=1, backfill_progress=NULL,"
                backfill_params = ()
            else:
                backfill_clause = "backfill_progress=NULL,"
                backfill_params = ()
            conn.execute(
                f"""UPDATE connections SET status='ready', last_sync_at=?,
                   next_sync_at=?, {backfill_clause}
                   error=NULL, consecutive_failures=0 WHERE id=?""",
                (
                    finished,
                    datetime.fromtimestamp(
                        time.time() + interval * 60, timezone.utc
                    ).isoformat(),
                    *backfill_params,
                    connection_id,
                ),
            )
            conn.execute(
                """UPDATE jobs SET finished_at=?, status='ok', new_count=?,
                   changed_count=?, unchanged_count=?, duration_ms=?, error=?
                   WHERE id=?""",
                (
                    finished,
                    counts["new"],
                    counts["changed"],
                    counts["unchanged"],
                    int((time.monotonic() - started) * 1000),
                    pipeline_error,
                    job_id,
                ),
            )
    except Exception as exc:
        if not _job_running(job_id):
            return
        with db() as conn:
            if _is_reauth(exc):
                # §11.4: auth failures skip the backoff ladder entirely —
                # retrying a revoked token on a timer helps nobody. The
                # scheduler's due-query only ever selects 'ready'/'error',
                # so next_sync_at is irrelevant here until reconnect resets
                # status back to 'ready'.
                conn.execute(
                    "UPDATE connections SET status='needs_reauth', error=? WHERE id=?",
                    (str(exc), connection_id),
                )
            else:
                row = conn.execute(
                    "SELECT consecutive_failures FROM connections WHERE id=?", (connection_id,)
                ).fetchone()
                failures = (row["consecutive_failures"] if row else 0) + 1
                conn.execute(
                    """UPDATE connections SET status='error', error=?,
                       consecutive_failures=?, next_sync_at=? WHERE id=?""",
                    (
                        str(exc),
                        failures,
                        next_retry_at(datetime.now(timezone.utc), failures),
                        connection_id,
                    ),
                )
            conn.execute(
                """UPDATE jobs SET finished_at=?, status='error', duration_ms=?,
                   error=? WHERE id=?""",
                (
                    _now(),
                    int((time.monotonic() - started) * 1000),
                    str(exc),
                    job_id,
                ),
            )


def _start_ingest(connection_id: str, *, first_sync: bool, provider: str) -> str:
    job_id = f"job_{uuid.uuid4().hex[:10]}"
    with db() as conn:
        running = conn.execute(
            "SELECT id FROM jobs WHERE connection_id=? AND status='running'",
            (connection_id,),
        ).fetchone()
        if running:
            raise HTTPException(409, "Job already running")
        conn.execute(
            """INSERT INTO jobs(id, connection_id, started_at, status,
               new_count, changed_count, unchanged_count)
               VALUES (?,?,?,'running',0,0,0)""",
            (job_id, connection_id, _now()),
        )
        conn.execute(
            "UPDATE connections SET status=?, error=NULL WHERE id=?",
            ("backfilling" if first_sync else "syncing", connection_id),
        )
    thread = threading.Thread(
        target=_run_ingest,
        args=(connection_id, job_id),
        kwargs={"first_sync": first_sync, "provider": provider},
        daemon=True,
        name=f"sync-{connection_id}",
    )
    _ready_timers[connection_id] = thread
    thread.start()
    return job_id


def _run_deep_backfill_page(connection_id: str, job_id: str, *, provider: str) -> None:
    """§11.3: one bounded, backward-walking page beyond the fast pass's
    lookback window. Never touches `connections.status` -- the connector
    stays `ready` throughout, this is a background enhancement, not a
    foreground state. A failure here never flips the connector to
    'error'/'needs_reauth' either (that's the incremental sync path's
    retry ladder, §11.2) -- the next scheduler tick just retries the same
    window."""
    started = time.monotonic()
    try:
        with db() as conn:
            credentials = _credential(conn, connection_id)
            row = conn.execute(
                "SELECT backfill_cursor, channel_ids_json, org_id FROM connections WHERE id=?",
                (connection_id,),
            ).fetchone()
            org_id = int(row["org_id"] or 1) if row is not None else 1
            settings = _settings_map(conn, org_id)
        if row is None or not row["backfill_cursor"]:
            with db() as conn:
                conn.execute(
                    "UPDATE jobs SET finished_at=?, status='ok', duration_ms=? WHERE id=?",
                    (_now(), int((time.monotonic() - started) * 1000), job_id),
                )
            return
        until = datetime.fromisoformat(row["backfill_cursor"])
        floor = _deep_backfill_floor(provider, credentials, settings, row)
        since = max(until - timedelta(days=DEEP_BACKFILL_PAGE_DAYS), floor)
        docs = _fetch_provider_docs_deep(provider, credentials, settings, row, since=since, until=until)
        if not _job_running(job_id):
            return
        with db() as conn:
            counts, dirty_docs = _persist_canonical_docs(conn, docs, org_id=org_id)

        pipeline_error: str | None = None
        try:
            if dirty_docs:
                llm_call = (
                    make_openrouter_caller(settings) if settings.get("llm_api_key") else None
                )
                with db() as conn:
                    pipeline_report = run_store_pipeline(
                        conn,
                        _live_index_for(org_id),
                        _hydra_store_for(org_id),
                        _embed_fn,
                        llm_call,
                        dirty_docs,
                        data_dir=DATA_DIR,
                        org_id=org_id,
                    )
                errors = [*pipeline_report.distill_errors, *pipeline_report.ontology.extract_errors]
                if errors:
                    pipeline_error = "; ".join(errors[:3])
        except Exception as exc:
            pipeline_error = str(exc)

        if not _job_running(job_id):
            return
        finished = _now()
        done = since <= floor
        with db() as conn:
            conn.execute(
                """UPDATE connections SET backfill_done=?, backfill_cursor=?,
                   doc_count=(SELECT COUNT(*) FROM docs
                              WHERE source_type=? AND forgotten=0 AND org_id=?)
                   WHERE id=?""",
                (
                    1 if done else 0,
                    None if done else since.isoformat(),
                    provider,
                    org_id,
                    connection_id,
                ),
            )
            conn.execute(
                """UPDATE jobs SET finished_at=?, status='ok', new_count=?,
                   changed_count=?, unchanged_count=?, duration_ms=?, error=?
                   WHERE id=?""",
                (
                    finished,
                    counts["new"],
                    counts["changed"],
                    counts["unchanged"],
                    int((time.monotonic() - started) * 1000),
                    pipeline_error,
                    job_id,
                ),
            )
    except Exception as exc:
        if not _job_running(job_id):
            return
        with db() as conn:
            conn.execute(
                """UPDATE jobs SET finished_at=?, status='error', duration_ms=?,
                   error=? WHERE id=?""",
                (_now(), int((time.monotonic() - started) * 1000), str(exc), job_id),
            )


def _start_deep_backfill(connection_id: str, *, provider: str) -> str:
    job_id = f"job_{uuid.uuid4().hex[:10]}"
    with db() as conn:
        running = conn.execute(
            "SELECT id FROM jobs WHERE connection_id=? AND status='running'",
            (connection_id,),
        ).fetchone()
        if running:
            raise HTTPException(409, "Job already running")
        conn.execute(
            """INSERT INTO jobs(id, connection_id, started_at, status,
               new_count, changed_count, unchanged_count)
               VALUES (?,?,?,'running',0,0,0)""",
            (job_id, connection_id, _now()),
        )
    thread = threading.Thread(
        target=_run_deep_backfill_page,
        args=(connection_id, job_id),
        kwargs={"provider": provider},
        daemon=True,
        name=f"deep-backfill-{connection_id}",
    )
    thread.start()
    return job_id


def _upsert_connection(
    provider: str,
    mode: str,
    credentials: dict[str, Any],
    *,
    org_id: int,
    lookback_days: int = 30,
    status: str = "backfilling",
    reset_progress: bool = True,
    owned_by: str | None = None,
) -> tuple[str, bool]:
    """§0.3/§1.4 personal connectors: `owned_by=None` is the org-shared
    connection every provider has always had (unchanged default, backward
    compatible); a real user id makes this THAT PERSON's own connection,
    coexisting with the org one and any other person's, per provider
    (`UNIQUE(org_id, provider, owned_by)`, migration 011)."""
    spec = INTEGRATION_BY_ID[provider]
    with db() as conn:
        if conn.execute("SELECT id FROM orgs WHERE id=?", (org_id,)).fetchone() is None:
            raise HTTPException(400, "Create an org first")
        existing = conn.execute(
            "SELECT id FROM connections WHERE org_id=? AND provider=? AND owned_by IS ?",
            (org_id, provider, owned_by),
        ).fetchone()
        created = existing is None
        connection_id = (
            existing["id"]
            if existing
            else f"conn_{provider}_{uuid.uuid4().hex[:8]}"
        )
        if created:
            conn.execute(
                """INSERT INTO connections(
                     id, org_id, provider, mode, status, interval_min, checklist_json,
                     created_at, backfill_progress, lookback_days, owned_by, kind)
                   VALUES (?,?,?,?,?,?,?,?,0.05,?,?,?)""",
                (
                    connection_id,
                    org_id,
                    provider,
                    mode,
                    status,
                    spec.default_interval_min,
                    json.dumps(_checklist_default()),
                    _now(),
                    lookback_days,
                    owned_by,
                    "personal" if owned_by else "org",
                ),
            )
        elif reset_progress:
            conn.execute(
                """UPDATE connections SET mode=?, status=?, checklist_json=?,
                   error=NULL, backfill_progress=0.05, lookback_days=?
                   WHERE id=?""",
                (
                    mode,
                    status,
                    json.dumps(_checklist_default()),
                    lookback_days,
                    connection_id,
                ),
            )
        else:
            conn.execute(
                """UPDATE connections SET mode=?, lookback_days=? WHERE id=?""",
                (mode, lookback_days, connection_id),
            )
        conn.execute(
            """INSERT INTO connector_credentials(
                 connection_id, encrypted_json, updated_at)
               VALUES (?,?,?)
               ON CONFLICT(connection_id) DO UPDATE SET
                 encrypted_json=excluded.encrypted_json,
                 updated_at=excluded.updated_at""",
            (
                connection_id,
                encrypt_credentials(credentials, DATA_DIR),
                _now(),
            ),
        )
    return connection_id, created


def _empty_connector(spec: IntegrationDef) -> dict[str, Any]:
    return {
        "id": None,
        "provider": spec.id,
        "label": spec.name,
        "status": "coming_soon" if not spec.connectable else "pending_auth",
        "mode": None,
        "doc_count": 0,
        "last_sync_at": None,
        "next_sync_at": None,
        "backfill_done": False,
        "backfill_progress": None,
        "error": None,
        "interval_min": spec.default_interval_min,
        "lookback_days": spec.default_lookback_days,
        "channel_ids": [],
        "coming_soon": not spec.connectable,
        "ingest": spec.ingest,
        "checklist": _checklist_default(),
        "sync_started_at": None,
    }


def _app_redirect(origin: str, return_to: str, **params: str) -> RedirectResponse:
    path = RETURN_PATHS.get(return_to, RETURN_PATHS["connectors"])
    try:
        origin = validate_return_to(origin)
    except OAuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    target = origin.rstrip("/") + path
    return _oauth_redirect(target, **params)


def _pending_lookback(toolkit: str) -> tuple[int, str, str, str | None, int]:
    with db() as conn:
        row = conn.execute(
            "SELECT lookback_days, return_to, origin, owned_by, org_id FROM pending_connects WHERE toolkit=?",
            (toolkit,),
        ).fetchone()
    if row is None:
        return 30, "connectors", "", None, 1
    days = int(row["lookback_days"] or 30)
    if days not in LOOKBACK_DAYS:
        days = 30
    owned_by = row["owned_by"] if "owned_by" in row.keys() else None
    org_id = int(row["org_id"] or 1) if "org_id" in row.keys() else 1
    return days, str(row["return_to"] or "connectors"), str(row["origin"] or ""), owned_by, org_id


def _activate_composio_toolkit(
    toolkit: str,
    *,
    lookback_days: int,
    start_sync: bool,
    org_id: int,
    account_id: str | None = None,
    owned_by: str | None = None,
) -> str | None:
    spec = INTEGRATION_BY_TOOLKIT.get(toolkit)
    if spec is None or not spec.connectable:
        return None
    with db() as conn:
        settings = _settings_map(conn, org_id)
    composio = get_composio(settings)
    account = None
    if account_id:
        account = {"id": account_id, "label": None}
    else:
        account = find_active_account(composio, toolkit)
    if account is None:
        return None
    credentials: dict[str, Any] = {
        "composio_account_id": account["id"],
        "account_label": account.get("label"),
    }
    if spec.ingest:
        status = "pending_setup"
    else:
        status = "ready"
    connection_id, created = _upsert_connection(
        spec.id,
        "composio",
        credentials,
        org_id=org_id,
        lookback_days=lookback_days,
        status=status,
        reset_progress=start_sync,
        owned_by=owned_by,
    )
    if spec.ingest:
        with db() as conn:
            conn.execute(
                """UPDATE connections SET status='pending_setup',
                   backfill_progress=NULL, error=NULL WHERE id=?""",
                (connection_id,),
            )
    else:
        with db() as conn:
            conn.execute(
                """UPDATE connections SET status='ready', backfill_progress=NULL,
                   backfill_done=1 WHERE id=?""",
                (connection_id,),
            )
    return connection_id


# ── auth / workspace ────────────────────────────────────────────────────────


def _session_response(
    payload: dict[str, Any], session_id: str | None, *, clear: bool = False
) -> JSONResponse:
    response = JSONResponse(payload)
    if clear:
        _clear_session_cookie(response)
    elif session_id:
        _set_session_cookie(response, session_id)
    return response


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    who = _request_identity(request)
    with db() as conn:
        if who.actor is None and who.user_id:
            workspaces = identity.list_workspaces_for_user(conn, who.user_id)
            return _auth_payload(conn, None, workspaces=workspaces, user_id=who.user_id)
        return _auth_payload(conn, who.actor)


@app.post("/api/auth/setup")
def auth_setup(body: SetupIn) -> JSONResponse:
    try:
        with db() as conn:
            actor, session_id = identity.setup(
                conn,
                email=body.email,
                password=body.password,
                display_name=body.display_name,
                domain=body.domain,
                company_name=body.name,
            )
            seed_org_defaults(conn, actor.org_id)
            payload = _auth_payload(conn, actor)
    except identity.IdentityError as exc:
        raise _identity_error(exc) from exc
    return _session_response(payload, session_id)


@app.post("/api/auth/login")
def auth_login(body: LoginIn) -> JSONResponse:
    try:
        with db() as conn:
            actor, session_id, workspaces = identity.login(conn, body.email, body.password)
            payload = _auth_payload(conn, actor, workspaces=workspaces)
    except identity.IdentityError as extra:
        raise _identity_error(extra) from extra
    return _session_response(payload, session_id)


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> JSONResponse:
    with db() as conn:
        identity.logout(conn, request.cookies.get(SESSION_COOKIE))
    return _session_response({"status": "ok"}, None, clear=True)


class SwitchWorkspaceIn(BaseModel):
    org_id: int


@app.post("/api/auth/workspace")
def auth_switch_workspace(body: SwitchWorkspaceIn, request: Request) -> JSONResponse:
    """Switch active workspace. Session must exist (may be in pick_workspace state)."""
    session_id, _user_id = _require_session_user(request)
    try:
        with db() as conn:
            actor = identity.switch_workspace(conn, session_id, body.org_id)
            payload = _auth_payload(conn, actor)
    except identity.IdentityError as extra:
        raise _identity_error(extra) from extra
    return _session_response(payload, session_id)


@app.get("/api/workspaces")
def list_workspaces(request: Request) -> dict[str, Any]:
    """List workspaces for current user. Works in pick_workspace state."""
    _session_id, user_id = _require_session_user(request)
    with db() as conn:
        workspaces = identity.list_workspaces_for_user(conn, user_id)
    return {"workspaces": workspaces}


class CreateWorkspaceIn(BaseModel):
    name: str | None = None
    domain: str | None = None
    slug: str | None = None


@app.post("/api/workspaces")
def create_workspace(body: CreateWorkspaceIn, request: Request) -> JSONResponse:
    """Create a new workspace. Any signed-in user becomes its owner."""
    session_id, user_id = _require_session_user(request)
    with db() as conn:
        try:
            org_id, new_actor = identity.create_workspace(
                conn,
                user_id,
                name=body.name,
                domain=body.domain,
                slug=body.slug,
                session_id=session_id,
            )
            seed_org_defaults(conn, org_id)
            payload = _auth_payload(conn, new_actor)
        except identity.IdentityError as exc:
            raise _identity_error(exc) from exc
    return _session_response(payload, session_id)


@app.get("/api/auth/invite/{token}")
def auth_peek_invite(token: str, request: Request) -> dict[str, Any]:
    who = _request_identity(request)
    try:
        with db() as conn:
            return identity.peek_invite(conn, token, viewer_user_id=who.user_id)
    except identity.IdentityError as exc:
        raise _identity_error(exc) from exc


@app.post("/api/auth/invite/{token}/accept")
def auth_accept_invite(
    token: str, body: AcceptInviteIn, request: Request
) -> JSONResponse:
    who = _request_identity(request)
    try:
        with db() as conn:
            actor, session_id = identity.accept_invite(
                conn,
                token,
                password=body.password,
                display_name=body.display_name,
                session_id=who.session_id,
            )
            payload = _auth_payload(conn, actor)
    except identity.IdentityError as extra:
        raise _identity_error(extra) from extra
    return _session_response(payload, session_id)


@app.get("/api/workspace")
def get_workspace(request: Request) -> dict[str, Any]:
    actor = _require_actor(request)
    with db() as conn:
        workspace = identity.workspace_public(conn, actor.org_id)
        if workspace is None:
            raise HTTPException(404, "Workspace not created yet")
        members = identity.list_members(conn, actor.org_id)
        invites = identity.list_invites(conn, actor.org_id) if actor.is_admin else []
    return {
        "workspace": workspace,
        "me": identity.actor_dict(actor),
        "members": members,
        "invites": invites,
    }


@app.patch("/api/workspace")
def patch_workspace(body: WorkspacePatch, request: Request) -> dict[str, Any]:
    actor = _require_admin(request)
    try:
        with db() as conn:
            identity.update_workspace(
                conn, actor, domain=body.domain, name=body.name
            )
            workspace = identity.workspace_public(conn, actor.org_id)
    except identity.IdentityError as extra:
        raise _identity_error(extra) from extra
    return {"workspace": workspace}


@app.post("/api/workspace/invites")
def create_workspace_invite(body: InviteIn, request: Request) -> dict[str, Any]:
    actor = _require_admin(request)
    try:
        with db() as conn:
            invite_id, raw = identity.create_invite(
                conn, actor, email=body.email, role=body.role
            )
            invites = identity.list_invites(conn, actor.org_id)
            settings = _settings_map(conn, actor.org_id)
            workspace = identity.workspace_public(conn, actor.org_id) or {}
    except identity.IdentityError as extra:
        raise _identity_error(extra) from extra

    email_sent, email_error = _send_invite_email(
        settings,
        email=body.email.strip().lower(),
        role=body.role,
        token=raw,
        workspace_name=str(workspace.get("name") or "joel"),
        app_url=_public_app_url(request, settings),
    )
    # Prefer the normalized address stored on the invite row when present.
    invited_email = body.email.strip().lower()
    for row in invites:
        if row.get("id") == invite_id and row.get("email"):
            invited_email = str(row["email"])
            break
    return {
        "invite_id": invite_id,
        "token": raw,
        "email": invited_email,
        "invites": invites,
        "email_sent": email_sent,
        "email_error": email_error,
        "mail_configured": joel_mail.is_configured(settings),
    }


@app.delete("/api/workspace/invites/{invite_id}")
def delete_workspace_invite(invite_id: str, request: Request) -> dict[str, str]:
    actor = _require_admin(request)
    try:
        with db() as conn:
            identity.revoke_invite(conn, actor, invite_id)
    except identity.IdentityError as extra:
        raise _identity_error(extra) from extra
    return {"status": "revoked"}


@app.post("/api/workspace/invites/{invite_id}/resend")
def resend_workspace_invite(invite_id: str, request: Request) -> dict[str, Any]:
    actor = _require_admin(request)
    try:
        with db() as conn:
            invite_id, raw, email, role = identity.resend_invite(
                conn, actor, invite_id
            )
            invites = identity.list_invites(conn, actor.org_id)
            settings = _settings_map(conn, actor.org_id)
            workspace = identity.workspace_public(conn, actor.org_id) or {}
    except identity.IdentityError as extra:
        raise _identity_error(extra) from extra

    email_sent, email_error = _send_invite_email(
        settings,
        email=email,
        role=role,
        token=raw,
        workspace_name=str(workspace.get("name") or "joel"),
        app_url=_public_app_url(request, settings),
    )
    return {
        "invite_id": invite_id,
        "token": raw,
        "email": email,
        "invites": invites,
        "email_sent": email_sent,
        "email_error": email_error,
        "mail_configured": joel_mail.is_configured(settings),
    }


@app.patch("/api/workspace/members/{user_id}")
def patch_workspace_member(
    user_id: str, body: MemberRoleIn, request: Request
) -> dict[str, str]:
    actor = _require_admin(request)
    try:
        with db() as conn:
            identity.set_member_role(conn, actor, user_id, body.role)
    except identity.IdentityError as extra:
        raise _identity_error(extra) from extra
    return {"status": "ok"}


@app.delete("/api/workspace/members/{user_id}")
def delete_workspace_member(user_id: str, request: Request) -> dict[str, str]:
    actor = _require_admin(request)
    try:
        with db() as conn:
            identity.remove_member(conn, actor, user_id)
    except identity.IdentityError as extra:
        raise _identity_error(extra) from extra
    return {"status": "removed"}


# ── org ─────────────────────────────────────────────────────────────────────


@app.get("/api/org")
def get_org(request: Request) -> dict[str, Any]:
    actor = _require_actor(request)
    with db() as conn:
        org = conn.execute(
            "SELECT * FROM orgs WHERE id=?", (actor.org_id,)
        ).fetchone()
        providers = tuple(sorted(INGEST_PROVIDERS))
        placeholders = ",".join("?" * len(providers))
        first = conn.execute(
            f"""SELECT * FROM connections
               WHERE org_id=? AND provider IN ({placeholders})
               ORDER BY backfill_done DESC, created_at ASC LIMIT 1""",
            (actor.org_id, *providers),
        ).fetchone()
        checklist = (
            _parse_checklist(first["checklist_json"]) if first else _checklist_default()
        )
        return {
            "org": None
            if org is None
            else {
                "domain": org["domain"],
                "name": org["name"],
                "logo_url": org["logo_url"],
                "created_at": org["created_at"],
            },
            "checklist": checklist,
            "first_connector_id": first["id"] if first else None,
        }


@app.post("/api/org/wipe")
def wipe_org(body: WipeIn, request: Request) -> dict[str, str]:
    actor = _require_admin(request)
    org_id = actor.org_id
    with db() as conn:
        org = conn.execute(
            "SELECT domain FROM orgs WHERE id=?", (org_id,)
        ).fetchone()
        if org is None or org["domain"] != body.domain.strip().lower():
            raise HTTPException(400, "Domain confirmation does not match")
        # FTS contentless delete needs old title/body before removing docs.
        for row in conn.execute(
            "SELECT rowid, title, body FROM docs WHERE org_id=?", (org_id,)
        ):
            conn.execute(
                "INSERT INTO docs_fts(docs_fts, rowid, title, body) VALUES('delete', ?, ?, ?)",
                (row["rowid"], row["title"], row["body"]),
            )
        conn.execute(
            "DELETE FROM messages WHERE conversation_id IN "
            "(SELECT id FROM conversations WHERE org_id=?)",
            (org_id,),
        )
        conn.execute("DELETE FROM conversations WHERE org_id=?", (org_id,))
        conn.execute(
            "DELETE FROM jobs WHERE connection_id IN "
            "(SELECT id FROM connections WHERE org_id=?)",
            (org_id,),
        )
        conn.execute(
            "DELETE FROM connector_credentials WHERE connection_id IN "
            "(SELECT id FROM connections WHERE org_id=?)",
            (org_id,),
        )
        conn.execute("DELETE FROM connections WHERE org_id=?", (org_id,))
        conn.execute("DELETE FROM oauth_states WHERE org_id=?", (org_id,))
        conn.execute("DELETE FROM pending_connects WHERE org_id=?", (org_id,))
        conn.execute("DELETE FROM docs WHERE org_id=?", (org_id,))
        conn.execute("DELETE FROM graph_written WHERE org_id=?", (org_id,))
        conn.execute("DELETE FROM thread_state WHERE org_id=?", (org_id,))
        conn.execute("UPDATE spend SET calls=0 WHERE org_id=?", (org_id,))
    index_path = DATA_DIR / "index" / f"org-{org_id}.npz"
    if index_path.exists():
        index_path.unlink()
    with _RUNTIME_LOCK:
        indexes = _RUNTIME.get("live_indexes")
        if isinstance(indexes, dict):
            indexes.pop(org_id, None)
        stores = _RUNTIME.get("hydra_stores")
        if isinstance(stores, dict):
            stores.pop(org_id, None)
    return {"status": "wiped"}


# ── connectors ──────────────────────────────────────────────────────────────


def _connectors_for_actor(all_rows: Sequence[sqlite3.Row], actor_id: str) -> dict[str, sqlite3.Row]:
    """§0.3/§1.4: with personal connectors, a provider can now have more
    than one row (one org-shared, one per person who's personally
    connected it) -- keying a dict by provider alone would silently drop
    every row but the last one iterated. Returns each provider's ONE row
    for THIS actor's view: their own personal connection if they have
    one, the org-shared one otherwise. Never another person's personal
    connection -- that's private to them, same as any other visibility
    boundary in this app. A pure function (no db/request) so it's directly
    unit-testable."""
    rows: dict[str, sqlite3.Row] = {}
    for r in all_rows:
        provider = r["provider"]
        owned_by = r["owned_by"] if "owned_by" in r.keys() else None
        if owned_by is not None and owned_by != actor_id:
            continue  # someone else's personal connection -- never listed here
        existing = rows.get(provider)
        # A personal row (this actor's own) always wins over the
        # org-shared one for the same provider, if both exist.
        if existing is None or owned_by == actor_id:
            rows[provider] = r
    return rows


@app.get("/api/connectors")
def list_connectors(request: Request) -> list[dict[str, Any]]:
    actor = _require_actor(request)
    with db() as conn:
        all_rows = conn.execute(
            "SELECT * FROM connections WHERE org_id=?", (actor.org_id,)
        ).fetchall()
        rows = _connectors_for_actor(all_rows, actor.user_id)
        started = {
            r["connection_id"]: r["started_at"]
            for r in conn.execute(
                """SELECT j.connection_id, j.started_at FROM jobs j
                   JOIN connections c ON c.id = j.connection_id
                   WHERE j.status='running' AND c.org_id=?""",
                (actor.org_id,),
            )
        }
    out: list[dict[str, Any]] = []
    for spec in INTEGRATIONS:
        if spec.id in rows:
            card = _row_connector(rows[spec.id])
            card["coming_soon"] = not spec.connectable
            card["ingest"] = spec.ingest
            card["sync_started_at"] = started.get(card["id"])
            out.append(card)
        else:
            out.append(_empty_connector(spec))
    return out


def _oauth_redirect(return_to: str, **params: str) -> RedirectResponse:
    parts = urlsplit(return_to)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    target = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
    return RedirectResponse(target, status_code=303)


@app.post("/api/connectors")
def create_connector(_body: ConnectorIn) -> dict[str, Any]:
    raise HTTPException(
        400,
        "Connect tools from Integrations with a Composio API key",
    )


@app.delete("/api/connectors/{connection_id}")
def delete_connector(connection_id: str, request: Request) -> dict[str, str]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE id=?", (connection_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Not found")
        actor = _require_connection_mutate(request, row)
        cred_row = conn.execute(
            "SELECT encrypted_json FROM connector_credentials WHERE connection_id=?",
            (connection_id,),
        ).fetchone()
        settings = _settings_map(conn, actor.org_id)
    account_id = None
    if cred_row is not None:
        try:
            account_id = decrypt_credentials(cred_row["encrypted_json"], DATA_DIR).get(
                "composio_account_id"
            )
        except OAuthError:
            account_id = None
    if account_id:
        try:
            get_composio(settings).connected_accounts.delete(str(account_id))
        except Exception as exc:
            raise HTTPException(502, f"Composio disconnect failed: {exc}") from exc
    with db() as conn:
        conn.execute("DELETE FROM connections WHERE id=?", (connection_id,))
    return {"status": "disconnected"}


@app.post("/api/connectors/{connection_id}/sync")
def sync_now(connection_id: str, request: Request) -> dict[str, str]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE id=?", (connection_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Not found")
        _require_connection_mutate(request, row)
        running = conn.execute(
            "SELECT id FROM jobs WHERE connection_id=? AND status='running'",
            (connection_id,),
        ).fetchone()
        if running:
            raise HTTPException(409, "Job already running")
        provider = row["provider"]
        channel_ids = _channel_ids(row)
        first_sync = not bool(row["last_sync_at"])
    if provider not in INGEST_PROVIDERS:
        raise HTTPException(400, "Ingest for this tool isn’t shipped yet")
    if provider == "slack" and not channel_ids:
        raise HTTPException(400, "Pick at least one channel, then start ingest")
    return {
        "job_id": _start_ingest(
            connection_id, first_sync=first_sync, provider=provider
        )
    }


@app.post("/api/connectors/{connection_id}/cancel")
def cancel_sync(connection_id: str, request: Request) -> dict[str, str]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE id=?", (connection_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Not found")
        _require_connection_mutate(request, row)
        released = release_running_jobs(conn, now=_now(), connection_id=connection_id)
        if released == 0:
            raise HTTPException(409, "Nothing to cancel")
    return {"status": "cancelled"}


@app.patch("/api/connectors/{connection_id}")
def patch_connector(
    connection_id: str, body: ConnectorPatch, request: Request
) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE id=?", (connection_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Not found")
        _require_connection_mutate(request, row)
        if body.interval_min is not None:
            conn.execute(
                "UPDATE connections SET interval_min=? WHERE id=?",
                (body.interval_min, connection_id),
            )
        if body.lookback_days is not None:
            if body.lookback_days not in LOOKBACK_DAYS:
                raise HTTPException(400, "Lookback must be 7, 30, 90, or 365 days")
            conn.execute(
                "UPDATE connections SET lookback_days=? WHERE id=?",
                (body.lookback_days, connection_id),
            )
        if body.channel_ids is not None:
            ids = [cid.strip() for cid in body.channel_ids if cid.strip()]
            conn.execute(
                "UPDATE connections SET channel_ids_json=? WHERE id=?",
                (json.dumps(ids), connection_id),
            )
        if body.paused is not None:
            conn.execute(
                "UPDATE connections SET paused=?, status=? WHERE id=?",
                (
                    1 if body.paused else 0,
                    "ready" if not body.paused else row["status"],
                    connection_id,
                ),
            )
        row = conn.execute(
            "SELECT * FROM connections WHERE id=?", (connection_id,)
        ).fetchone()
    return _row_connector(row)


@app.get("/api/connectors/{connection_id}/jobs")
def list_jobs(connection_id: str) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs WHERE connection_id=?
               ORDER BY started_at DESC LIMIT 20""",
            (connection_id,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "started_at": r["started_at"],
            "finished_at": r["finished_at"],
            "status": r["status"],
            "new_count": r["new_count"],
            "changed_count": r["changed_count"],
            "unchanged_count": r["unchanged_count"],
            "duration_ms": r["duration_ms"],
            "error": r["error"],
        }
        for r in rows
    ]


@app.get("/api/connectors/{connection_id}/channels")
def list_connector_channels(connection_id: str, request: Request) -> dict[str, Any]:
    actor = _require_actor(request)
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE id=? AND org_id=?",
            (connection_id, actor.org_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Not found")
        if row["provider"] != "slack":
            raise HTTPException(400, "Channel picker is only for Slack")
        credentials = _credential(conn, connection_id)
        settings = _settings_map(conn, actor.org_id)
    try:
        client = SlackClient(
            _slack_token(credentials),
            caller=_slack_caller(credentials, settings),
        )
        listed = client.channels()
    except (SlackAPIError, ComposioError, OAuthError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "channels": [
            {
                "id": str(channel.get("id") or ""),
                "name": str(channel.get("name") or channel.get("id") or ""),
                "is_private": bool(channel.get("is_private")),
            }
            for channel in listed
            if channel.get("id")
        ]
    }


# ── composio ────────────────────────────────────────────────────────────────


@app.get("/api/composio")
def composio_status(request: Request) -> dict[str, Any]:
    actor = _require_actor(request)
    with db() as conn:
        settings = _settings_map(conn, actor.org_id)
    api_key, source = resolve_composio_key(settings)
    if not api_key:
        return {
            "configured": False,
            "key_source": "none",
            "masked_key": None,
            "accounts": [],
        }
    try:
        composio = get_composio(settings)
        accounts = [
            account
            for account in list_connected_accounts(composio)
            if account["toolkit"] in INTEGRATION_BY_TOOLKIT
        ]
        with db() as conn:
            known = {
                r["provider"]
                for r in conn.execute(
                    "SELECT provider FROM connections WHERE org_id=?", (actor.org_id,)
                ).fetchall()
            }
        for account in accounts:
            spec = INTEGRATION_BY_TOOLKIT.get(account["toolkit"])
            if spec is None or spec.id in known:
                continue
            lookback, _return_to, _origin, _owned_by, org_id = _pending_lookback(
                account["toolkit"]
            )
            try:
                _activate_composio_toolkit(
                    account["toolkit"],
                    lookback_days=lookback,
                    start_sync=False,
                    org_id=org_id if org_id else actor.org_id,
                )
            except (HTTPException, ComposioError):
                pass
        return {
            "configured": True,
            "key_source": source,
            "masked_key": mask_api_key(api_key),
            "accounts": accounts,
        }
    except Exception as exc:
        logging.getLogger(__name__).warning("composio status: %s", exc)
        msg = str(exc)
        auth = bool(
            re.search(r"401|unauthorized|invalid.{0,20}key|forbidden", msg, re.I)
        )
        # Listing accounts can flake with httpx "Connection error." A saved
        # key is still usable for connect — don't treat that as a key failure.
        return {
            "configured": True,
            "key_source": source,
            "masked_key": mask_api_key(api_key),
            "accounts": [],
            **({"error": msg} if auth else {}),
        }


@app.put("/api/composio/key")
def set_composio_key(body: ComposioKeyIn, request: Request) -> dict[str, Any]:
    actor = _require_admin(request)
    with db() as conn:
        conn.execute(
            "INSERT INTO settings(org_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(org_id, key) DO UPDATE SET value=excluded.value",
            (actor.org_id, "composio_api_key", (body.api_key or "").strip()),
        )
        settings = _settings_map(conn, actor.org_id)
    api_key, source = resolve_composio_key(settings)
    return {
        "configured": bool(api_key),
        "key_source": source,
        "masked_key": mask_api_key(api_key) if api_key else None,
    }


@app.post("/api/composio/connect")
def composio_connect(request: Request, body: ComposioConnectIn) -> dict[str, str]:
    actor = _require_actor(request)
    if not body.personal:
        if not actor.is_admin:
            raise HTTPException(403, "Only an admin can connect org tools")
    try:
        spec = require_connectable(body.toolkit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if body.lookback_days not in LOOKBACK_DAYS:
        raise HTTPException(400, "Lookback must be 7, 30, 90, or 365 days")
    if body.return_to not in RETURN_PATHS:
        raise HTTPException(400, "return_to must be connectors or onboarding")
    if body.personal and spec.id not in PERSONAL_CONNECTOR_PROVIDERS:
        raise HTTPException(400, f"{spec.name} can't be connected as a personal connector")
    try:
        origin = validate_return_to(body.origin.strip())
    except OAuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    owned_by = actor.user_id if body.personal else None
    with db() as conn:
        if conn.execute("SELECT id FROM orgs WHERE id=?", (actor.org_id,)).fetchone() is None:
            raise HTTPException(400, "Create an org first")
        settings = _settings_map(conn, actor.org_id)
        conn.execute(
            """INSERT INTO pending_connects(toolkit, lookback_days, return_to, origin, created_at, owned_by, org_id)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(toolkit) DO UPDATE SET
                 lookback_days=excluded.lookback_days,
                 return_to=excluded.return_to,
                 origin=excluded.origin,
                 created_at=excluded.created_at,
                 owned_by=excluded.owned_by,
                 org_id=excluded.org_id""",
            (
                spec.toolkit,
                body.lookback_days,
                body.return_to,
                origin,
                _now(),
                owned_by,
                actor.org_id,
            ),
        )
    callback_url = (
        f"{origin.rstrip('/')}/api/composio/callback"
        f"?toolkit={spec.toolkit}&returnTo={body.return_to}"
    )
    last_exc: Exception | None = None
    redirect_url = ""
    for attempt in range(2):
        try:
            redirect_url = start_toolkit_connect(
                get_composio(settings),
                spec.toolkit,
                callback_url,
                body.auth_config_id,
            )
            last_exc = None
            break
        except ComposioError as exc:
            last_exc = exc
            break
        except Exception as exc:
            last_exc = exc
            if attempt == 0 and re.search(r"connection error", str(exc), re.I):
                continue
            break
    if last_exc is not None:
        msg = str(last_exc).strip() or "Composio request failed"
        if re.search(r"connection error", msg, re.I):
            msg = "Composio didn't respond. Try Connect again."
        raise HTTPException(502, msg) from last_exc
    return {"redirect_url": redirect_url}


@app.get("/api/composio/callback")
def composio_callback(
    toolkit: str | None = None,
    app: str | None = None,
    returnTo: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    connected_account_id: str | None = None,
) -> RedirectResponse:
    slug = (toolkit or app or "connected").strip().lower()
    lookback, stored_return, origin, owned_by, org_id = _pending_lookback(slug)
    return_to = returnTo or stored_return or "connectors"
    if not origin:
        origin = os.getenv("JOEL_WEB_ORIGIN", "http://localhost:3001")
    fail = error or error_description
    if fail:
        return _app_redirect(origin, return_to, error=str(fail))
    try:
        _activate_composio_toolkit(
            slug,
            lookback_days=lookback,
            start_sync=True,
            org_id=org_id,
            account_id=connected_account_id,
            owned_by=owned_by,
        )
    except Exception as exc:
        return _app_redirect(origin, return_to, error=str(exc))
    return _app_redirect(origin, return_to, connected=slug)


# ── conversations / ask ─────────────────────────────────────────────────────


@app.get("/api/conversations")
def list_conversations(request: Request) -> list[dict[str, Any]]:
    actor = _require_actor(request)
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM conversations
               WHERE org_id=? AND user_id=?
               ORDER BY created_at DESC""",
            (actor.org_id, actor.user_id),
        ).fetchall()
    return [
        {"id": r["id"], "title": r["title"], "created_at": r["created_at"]}
        for r in rows
    ]


@app.post("/api/conversations")
def create_conversation(body: ConversationIn, request: Request) -> dict[str, Any]:
    actor = _require_actor(request)
    cid = f"c_{uuid.uuid4().hex[:12]}"
    title = (body.title or "New conversation").strip() or "New conversation"
    created = _now()
    with db() as conn:
        conn.execute(
            "INSERT INTO conversations(id, title, created_at, org_id, user_id) VALUES (?,?,?,?,?)",
            (cid, title, created, actor.org_id, actor.user_id),
        )
    return {"id": cid, "title": title, "created_at": created}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    actor = _require_actor(request)
    with db() as conn:
        c = conn.execute(
            "SELECT * FROM conversations WHERE id=? AND org_id=? AND user_id=?",
            (conversation_id, actor.org_id, actor.user_id),
        ).fetchone()
        if c is None:
            raise HTTPException(404, "Not found")
        msgs = conn.execute(
            """SELECT * FROM messages WHERE conversation_id=?
               ORDER BY created_at ASC""",
            (conversation_id,),
        ).fetchall()
    return {
        "id": c["id"],
        "title": c["title"],
        "created_at": c["created_at"],
        "messages": [
            {"id": m["id"], **json.loads(m["content_json"]), "created_at": m["created_at"]}
            for m in msgs
        ],
    }


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


_CHITCHAT_RE = re.compile(
    r"^(hi|hello|hey|yo|sup|hiya|howdy|thanks|thank you|thx|ty|ok|okay|k|cool|"
    r"nice|great|got it|sounds good|bye|goodbye)[!.?\s]*$",
    re.IGNORECASE,
)


def _is_chitchat(question: str) -> bool:
    return bool(_CHITCHAT_RE.match(question.strip()))


def _assistant_payload(
    content: str,
    *,
    status: str,
    citations: list[dict[str, Any]] | None = None,
    lanes: list[str] | None = None,
    reasoning_path: list[str] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content,
        "status": status,
        "citations": citations or [],
        "lanes": lanes or [],
        "reasoning_path": reasoning_path or [],
        "tool_calls": tool_calls or [],
        "conflicts": conflicts or [],
        "not_found": [],
    }


def _save_assistant_message(conn: sqlite3.Connection, conversation_id: str, assistant: dict[str, Any]) -> None:
    mid = f"m_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """INSERT INTO messages(id, conversation_id, role, content_json, created_at)
           VALUES (?,?,?,?,?)""",
        (mid, conversation_id, "assistant", json.dumps(assistant), _now()),
    )


def _run_live_lookup(
    conn: sqlite3.Connection,
    settings_map: dict[str, str],
    llm_call: Any,
    question: str,
    plan: QueryPlan,
    *,
    actor_id: str,
    org_id: int,
) -> tuple[list[str], list[str]]:
    """§13.2: at most `live.MAX_LOOKUPS` whitelisted point-lookups, each
    under `live.TIMEOUT_SECONDS`, only against providers this workspace has
    actually connected. Fetched docs go through the exact same
    `_persist_canonical_docs` + `run_store_pipeline` front door as a
    scheduled sync (§13.2's "nothing skips distillation and the noise
    filter" rule) — no second write path. Returns `(stored_doc_ids,
    checked_descriptions)`; `stored_doc_ids` is empty when nothing
    whitelisted matched, nothing was found, or a fetch timed out/errored —
    all of which degrade to "not found live either", never a crash.
    """
    targets = detect_live_targets(conn, question, plan)
    if not targets:
        return [], []

    ready_providers = {
        r["provider"]
        for r in conn.execute(
            "SELECT provider FROM connections WHERE status='ready' AND org_id=?",
            (org_id,),
        )
    }
    checked: list[str] = []
    fetched_docs: list[CanonicalDoc] = []

    for target in targets:
        provider = "github" if isinstance(target, GitHubItemTarget) else "slack"
        if provider not in ready_providers:
            continue
        # §1.4/§0.3 personal-then-org-shared read resolution: this actor's
        # own personal connection (if one exists and is ready) is used
        # over the org-shared one -- e.g. a live Slack lookup should read
        # with the asking person's own identity when they have one,
        # falling back to the shared connection otherwise. Only
        # gmail/slack can even have a personal row (PERSONAL_CONNECTOR_
        # PROVIDERS), so this is a no-op for github today.
        conn_row = conn.execute(
            """SELECT id FROM connections WHERE provider=? AND status='ready'
               AND org_id=? AND (owned_by=? OR owned_by IS NULL)
               ORDER BY (owned_by IS NULL) LIMIT 1""",
            (provider, org_id, actor_id),
        ).fetchone()
        if conn_row is None:
            continue
        try:
            credentials = _credential(conn, conn_row["id"])
            if provider == "github":
                request = _provider_request(
                    credentials, settings_map, GitHubAPIError, extra_headers={"Accept": GITHUB_ACCEPT}
                )
                kwargs: dict[str, Any] = {"github_request": request}
            else:
                kwargs = {
                    "slack_token": _slack_token(credentials),
                    "slack_caller": _slack_caller(credentials, settings_map),
                }
        except Exception:
            continue  # credentials missing/invalid -- skip this lookup, don't fail the question

        checked.append(target.description)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fetch_live_target, target, **kwargs)
            try:
                result = future.result(timeout=LIVE_TIMEOUT_SECONDS)
            except Exception:
                continue  # timeout, network error, or provider error -- skip, not a crash
        fetched_docs.extend(result.docs)

    if not fetched_docs:
        return [], checked

    live_docs = [d.model_copy(update={"ingested_via": "live"}) for d in fetched_docs]
    _, dirty_docs = _persist_canonical_docs(conn, live_docs, org_id=org_id)
    if dirty_docs and llm_call is not None:
        run_store_pipeline(
            conn,
            _live_index_for(org_id),
            _hydra_store_for(org_id),
            _embed_fn,
            llm_call,
            dirty_docs,
            data_dir=DATA_DIR,
            org_id=org_id,
        )
    # Every fetched doc is now indexed (freshly, via dirty_docs above, or
    # already from an earlier live/sync pass) and citable — not just the
    # ones that happened to change THIS call.
    return [d.doc_id for d in live_docs], checked


def _mcp_ask_sync(actor: identity.Actor, question: str) -> dict[str, Any]:
    """§13's MCP surface: the same `answer_question` retrieval/synthesis
    pipeline `/api/ask` uses, AskContext built server-side from the
    API-key's owner exactly like the web session path. Deliberately NOT
    (yet) wrapped in follow-up rewriting or live lookup -- each MCP call
    is a standalone question answered from memory alone; see
    `mcp_server.py`'s module docstring for the honest scope note."""
    question = question.strip()
    if not question:
        return {"answer": "Ask a question.", "status": "absent", "citations": []}
    with db() as conn:
        settings_map = _settings_map(conn, actor.org_id)
        ask_ctx = AskContext.web(
            actor.user_id,
            aliases={Visibility.user("gmail", actor.email).stamp},
            channels=member_channel_stamps(conn, actor.user_id, org_id=actor.org_id),
            org_id=actor.org_id,
        )
    llm_call = make_openrouter_caller(settings_map) if settings_map.get("llm_api_key") else None
    with db() as conn:
        trace = answer_question(
            conn,
            _live_index_for(actor.org_id),
            _embed_fn,
            llm_call,
            question,
            ask=ask_ctx,
            hydra_store=_hydra_store_for(actor.org_id),
        )
    doc_lookup = {r.doc.id: r.doc for r in trace.reranked} or {d.id: d for d in trace.fused}
    citations = [
        {
            "title": doc_lookup[doc_id].title if doc_id in doc_lookup else doc_id,
            "url": doc_lookup[doc_id].url if doc_id in doc_lookup else None,
        }
        for doc_id in trace.answer.citations
    ]
    return {"answer": trace.answer.answer, "status": trace.answer.status, "citations": citations}


async def _mcp_ask(actor: identity.Actor, question: str) -> dict[str, Any]:
    return await anyio.to_thread.run_sync(_mcp_ask_sync, actor, question)


_slack_seen_events = SeenEvents()


def _resolve_slack_actor(conn: sqlite3.Connection, slack_user_id: str) -> identity.Actor | None:
    """§1.4's email-matching signal, reapplied a third time (Gmail
    visibility, channel membership, and now this): a Slack user is only
    ever an Actor if their Slack profile email matches a real workspace
    member's. No match -> no Actor -> the mention is silently declined,
    never answered with an org-wide AskContext for someone unrecognized."""
    row = conn.execute(
        """SELECT id, org_id FROM connections
           WHERE provider='slack' AND status='ready' LIMIT 1"""
    ).fetchone()
    if row is None:
        return None
    org_id = int(row["org_id"] or 1)
    try:
        credentials = _credential(conn, row["id"])
        settings_map = _settings_map(conn, org_id)
        client = SlackClient(_slack_token(credentials), caller=_slack_caller(credentials, settings_map))
        emails = client.user_emails()
    except Exception:
        return None
    email = emails.get(slack_user_id)
    if not email:
        return None
    user_row = conn.execute("SELECT id FROM users WHERE email=?", (email.lower(),)).fetchone()
    if user_row is None:
        return None
    return identity.actor_for_user(conn, user_row["id"], org_id)


def _handle_slack_mention(event_id: str, channel: str, slack_user_id: str, text: str, thread_ts: str, bot_user_id: str) -> None:
    """Runs on a background thread -- Slack's Events API needs a 200
    within 3 seconds or it retries the whole delivery, and real retrieval
    is real LLM calls, seconds not milliseconds."""
    try:
        with db() as conn:
            actor = _resolve_slack_actor(conn, slack_user_id)
            if actor is None:
                return
            row = conn.execute(
                """SELECT id FROM connections
                   WHERE provider='slack' AND status='ready' AND org_id=?""",
                (actor.org_id,),
            ).fetchone()
            if row is None:
                return
            credentials = _credential(conn, row["id"])
            settings_map = _settings_map(conn, actor.org_id)
            caller = _slack_caller(credentials, settings_map)
        question = strip_mention(text, bot_user_id)
        if not question:
            return
        result = _mcp_ask_sync(actor, question)
        answer = str(result.get("answer") or "")
        if not answer:
            return
        if caller is not None:
            post_reply(caller, channel=channel, thread_ts=thread_ts, text=answer)
    except Exception:
        logging.getLogger(__name__).exception("slack bot mention handling failed for event %s", event_id)


@app.post("/api/slack/events")
async def slack_events(request: Request) -> dict[str, Any]:
    body = await request.body()
    timestamp = request.headers.get("x-slack-request-timestamp", "")
    signature = request.headers.get("x-slack-signature", "")
    # Slack signing secret is per-org; try each org that has a ready slack
    # connection until one verifies (Mode B: multiple workspaces may share
    # one Events URL on a single install).
    verified = False
    with db() as conn:
        org_ids = [
            int(r["org_id"] or 1)
            for r in conn.execute(
                "SELECT DISTINCT org_id FROM connections WHERE provider='slack'"
            ).fetchall()
        ]
        if not org_ids:
            org_ids = [1]
        for org_id in org_ids:
            settings_map = _settings_map(conn, org_id)
            signing_secret = settings_map.get("slack_signing_secret", "")
            if verify_signature(
                signing_secret=signing_secret,
                timestamp=timestamp,
                body=body,
                signature=signature,
            ):
                verified = True
                break
    if not verified:
        raise HTTPException(401, "Invalid Slack signature")

    payload = await request.json()
    if payload.get("type") == "url_verification":
        # The one-time handshake Slack does when you first save the
        # Events API request URL in the app's settings.
        return {"challenge": payload.get("challenge", "")}

    mention = parse_app_mention(payload)
    if mention is None:
        return {"ok": True}
    if _slack_seen_events.already_seen(mention.event_id):
        return {"ok": True}

    with db() as conn:
        row = conn.execute(
            "SELECT id, org_id FROM connections WHERE provider='slack' AND status='ready' LIMIT 1"
        ).fetchone()
        bot_user_id = ""
        if row is not None:
            try:
                credentials = _credential(conn, row["id"])
                settings_map = _settings_map(conn, int(row["org_id"] or 1))
                client = SlackClient(_slack_token(credentials), caller=_slack_caller(credentials, settings_map))
                bot_user_id = str(client.call("auth.test").get("user_id") or "")
            except Exception:
                bot_user_id = ""

    thread_ts = mention.thread_ts or mention.ts
    threading.Thread(
        target=_handle_slack_mention,
        args=(mention.event_id, mention.channel, mention.user, mention.text, thread_ts, bot_user_id),
        daemon=True,
        name=f"slack-mention-{mention.event_id}",
    ).start()
    return {"ok": True}


_mcp_mount = build_mcp_app(ask_fn=_mcp_ask, actor_resolver=_mcp_actor_resolver)
app.mount("/mcp", _mcp_mount.asgi_app)
_mcp_session_cm = None


@app.on_event("startup")
async def _start_mcp_session_manager() -> None:
    # `app.mount()` does not chain a sub-app's `lifespan` into the outer
    # app's -- the Streamable HTTP transport's task group is never
    # started/stopped unless something does that explicitly. This is that
    # something, kept separate from `_startup()` above (which is sync)
    # rather than folding MCP's async setup into it.
    global _mcp_session_cm
    _mcp_session_cm = _mcp_mount.run_forever()
    await _mcp_session_cm.__aenter__()


@app.on_event("shutdown")
async def _stop_mcp_session_manager() -> None:
    if _mcp_session_cm is not None:
        await _mcp_session_cm.__aexit__(None, None, None)


@app.post("/api/ask")
def ask(request: Request, body: AskIn) -> StreamingResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Empty question")
    actor = _require_actor(request)

    with db() as conn:
        # Web is the asker's desk: the workspace email is the one mailbox
        # identity we have until connectors are owned per person (§0.3),
        # and private Slack channels the actor is a member of (§1.4) —
        # closing the literal gap the plan named: "web cannot yet include
        # channel:slack:… even for people who are in that Slack room."
        ask_ctx = AskContext.web(
            actor.user_id,
            aliases={Visibility.user("gmail", actor.email).stamp},
            channels=member_channel_stamps(conn, actor.user_id, org_id=actor.org_id),
            org_id=actor.org_id,
        )
        c = conn.execute(
            "SELECT * FROM conversations WHERE id=? AND org_id=? AND user_id=?",
            (body.conversation_id, actor.org_id, actor.user_id),
        ).fetchone()
        if c is None:
            raise HTTPException(404, "Conversation not found")

        if c["title"] == "New conversation":
            title = question[:72] + ("…" if len(question) > 72 else "")
            conn.execute(
                "UPDATE conversations SET title=? WHERE id=?",
                (title, body.conversation_id),
            )

        user_id = f"m_{uuid.uuid4().hex[:12]}"
        user_payload = {"role": "user", "content": question}
        conn.execute(
            """INSERT INTO messages(id, conversation_id, role, content_json, created_at)
               VALUES (?,?,?,?,?)""",
            (user_id, body.conversation_id, "user", json.dumps(user_payload), _now()),
        )

    def stream() -> Iterator[str]:
        yield _sse("status", {"stage": "rewriting"})

        if _is_chitchat(question):
            # Zero-cost fast path for the most obvious greetings/acks — a
            # bare "hi" costs zero retrieval AND zero LLM calls, strictly
            # better than §13.1's "one cheap call" floor. Anything less
            # obvious falls through to the real rewrite_question call below,
            # which also classifies chitchat (just not for free).
            answer_text = (
                "Hey! Ask me anything about the company and I'll answer from "
                "what's been ingested — or say honestly when it's not in there."
            )
            yield _sse("rewritten", {"question": question, "kind": "chitchat"})
            yield _sse("status", {"stage": "answering"})
            for token in answer_text.split(" "):
                yield _sse("token", {"text": token + " "})
            assistant = _assistant_payload(answer_text, status="answered")
            yield _sse("citations", {"citations": []})
            yield _sse("reasoning_path", {"paths": []})
            yield _sse("done", {"status": "answered", "message": assistant})
            with db() as conn:
                _save_assistant_message(conn, body.conversation_id, assistant)
            return

        with db() as conn:
            settings_map = _settings_map(conn, actor.org_id)
            turns = load_recent_turns(conn, body.conversation_id)
        llm_call = make_openrouter_caller(settings_map) if settings_map.get("llm_api_key") else None
        call_counts: dict[str, int] = {}

        def tracked_llm(stage: str, system_prompt: str, user_prompt: str) -> str:
            raw = llm_call(stage, system_prompt, user_prompt)
            call_counts[stage] = call_counts.get(stage, 0) + 1
            return raw

        # §13.1: rewrite the raw message into a standalone question and
        # classify it — knowledge/meta/chitchat — before planning anything.
        rewritten_question = question
        kind = "knowledge"
        if llm_call is not None:
            result = rewrite_question(tracked_llm, turns, question)
            rewritten_question = result.question
            kind = result.kind
        yield _sse("rewritten", {"question": rewritten_question, "kind": kind})

        if kind == "chitchat":
            answer_text = (
                "Hey! Ask me anything about the company and I'll answer from "
                "what's been ingested — or say honestly when it's not in there."
            )
            yield _sse("status", {"stage": "answering"})
            for token in answer_text.split(" "):
                yield _sse("token", {"text": token + " "})
            assistant = _assistant_payload(answer_text, status="answered")
            yield _sse("citations", {"citations": []})
            yield _sse("reasoning_path", {"paths": []})
            yield _sse("done", {"status": "answered", "message": assistant})
            with db() as conn:
                _save_assistant_message(conn, body.conversation_id, assistant)
                for stage, n in call_counts.items():
                    conn.execute(
                        "UPDATE spend SET calls = calls + ? WHERE org_id=? AND stage=?",
                        (n, actor.org_id, stage),
                    )
            return

        if kind == "meta":
            # §13.1: answered from the conversation alone — no lanes, no
            # rerank, no ingest.
            answer_text = answer_meta(turns, rewritten_question)
            yield _sse("status", {"stage": "answering"})
            for token in answer_text.split(" "):
                yield _sse("token", {"text": token + " "})
            assistant = _assistant_payload(answer_text, status="answered")
            yield _sse("citations", {"citations": []})
            yield _sse("reasoning_path", {"paths": []})
            yield _sse("done", {"status": "answered", "message": assistant})
            with db() as conn:
                _save_assistant_message(conn, body.conversation_id, assistant)
                for stage, n in call_counts.items():
                    conn.execute(
                        "UPDATE spend SET calls = calls + ? WHERE org_id=? AND stage=?",
                        (n, actor.org_id, stage),
                    )
            return

        yield _sse("status", {"stage": "planning"})

        try:
            with db() as conn:
                trace = answer_question(
                    conn,
                    _live_index_for(actor.org_id),
                    _embed_fn,
                    tracked_llm if llm_call else None,
                    rewritten_question,
                    ask=ask_ctx,
                    hydra_store=_hydra_store_for(actor.org_id),
                )
        except Exception:
            # Retrieval must never crash the stream — an unexpected failure
            # (a store/model/network fault none of the per-stage LLMError
            # handling caught) degrades to the same honest "absent" a weak
            # context would, not a dropped connection the UI can't recover
            # from. Logged server-side; not surfaced to the user as a stack
            # trace.
            logging.getLogger(__name__).exception("answer_question failed for %r", rewritten_question)
            trace = RetrievalTrace(question=rewritten_question, plan=QueryPlan(intent="lookup"))

        yield _sse("plan", {"lanes": list(trace.lane_results.keys()), "intent": trace.plan.intent})
        for lane, docs in trace.lane_results.items():
            yield _sse("lane", {"lane": lane, "status": "done", "hits": len(docs), "provider": None})
        yield _sse("status", {"stage": "reranking"})

        # §13.2: live lookup fires on exactly two conditions — planner
        # intent is "live", or the abstention gate fired. Memory-first,
        # always: this only ever runs AFTER the real retrieval above.
        live_doc_ids: list[str] = []
        live_checked: list[str] = []
        if llm_call is not None and (trace.plan.intent == "live" or trace.answer.status == "absent"):
            yield _sse("status", {"stage": "live"})
            try:
                with db() as conn:
                    live_doc_ids, live_checked = _run_live_lookup(
                        conn,
                        settings_map,
                        tracked_llm,
                        rewritten_question,
                        trace.plan,
                        actor_id=actor.user_id,
                        org_id=actor.org_id,
                    )
            except Exception:
                logging.getLogger(__name__).exception("live lookup failed for %r", rewritten_question)
            if live_checked:
                yield _sse("live", {"checked": live_checked, "found": bool(live_doc_ids)})
            if live_doc_ids:
                # Something new (or already-live-known) is now in the index
                # — re-run retrieval once so this turn can actually cite it,
                # rather than making the user ask again.
                try:
                    with db() as conn:
                        trace = answer_question(
                            conn,
                            _live_index_for(actor.org_id),
                            _embed_fn,
                            tracked_llm,
                            rewritten_question,
                            ask=ask_ctx,
                            hydra_store=_hydra_store_for(actor.org_id),
                            extra_doc_ids=tuple(live_doc_ids),
                        )
                except Exception:
                    logging.getLogger(__name__).exception(
                        "post-live-lookup answer_question failed for %r", rewritten_question
                    )

        yield _sse("status", {"stage": "answering"})

        answer_text = trace.answer.answer
        live_doc_id_set = set(live_doc_ids)
        cited_live = live_doc_id_set.intersection(trace.answer.citations)
        if live_checked and not live_doc_ids and trace.answer.status == "absent":
            # §13.2's ✅ DO: abstain honestly, don't hide the live attempt.
            answer_text += f" A live check of {', '.join(live_checked)} found nothing either."
        elif cited_live and trace.answer.status in {"answered", "partial"}:
            answer_text = f"As of just now: {answer_text}"
        for token in answer_text.split(" "):
            yield _sse("token", {"text": token + " "})

        # §13.2's whitelisted point-lookups ARE the agent's only tool calls
        # today -- surfaced on the message so the UI can show what was
        # actually checked live, not just the resulting citation.
        tool_calls = [
            {
                "id": f"live_{i}",
                "name": "live_lookup",
                "provider": "github" if desc.startswith("GitHub") else "slack",
                "status": "done",
                "detail": "found new content" if live_doc_ids else "nothing new found",
            }
            for i, desc in enumerate(live_checked)
        ]

        doc_lookup = {r.doc.id: r.doc for r in trace.reranked} or {d.id: d for d in trace.fused}
        citations = [
            {
                "doc_id": doc_id,
                "title": doc_lookup[doc_id].title if doc_id in doc_lookup else doc_id,
                "url": doc_lookup[doc_id].url if doc_id in doc_lookup else None,
                "live": doc_id in live_doc_id_set,
                "provider": None,
                "source_type": doc_lookup[doc_id].source_type if doc_id in doc_lookup else None,
            }
            for doc_id in trace.answer.citations
        ]
        conflicts = []
        if trace.answer.conflict is not None:
            conflicts = [
                {
                    "assessment": trace.answer.conflict.assessment,
                    "positions": [
                        {"claim": p.claim, "date": p.when, "source": p.source_type, "url": None}
                        for p in trace.answer.conflict.positions
                    ],
                }
            ]

        for call in tool_calls:
            yield _sse("tool_call", call)

        assistant = _assistant_payload(
            answer_text,
            status=trace.answer.status,
            citations=citations,
            lanes=list(trace.lane_results.keys()),
            reasoning_path=trace.answer.reasoning_path,
            conflicts=conflicts,
            tool_calls=tool_calls,
        )
        yield _sse("citations", {"citations": citations})
        yield _sse("reasoning_path", {"paths": trace.answer.reasoning_path})
        yield _sse("done", {"status": trace.answer.status, "message": assistant})

        with db() as conn:
            _save_assistant_message(conn, body.conversation_id, assistant)
            for stage, n in call_counts.items():
                conn.execute(
                    "UPDATE spend SET calls = calls + ? WHERE org_id=? AND stage=?",
                    (n, actor.org_id, stage),
                )
        try:
            log_trace(
                DATA_DIR / "state" / "traces.jsonl",
                trace,
                extra={"conversation_id": body.conversation_id},
            )
        except OSError:
            pass  # traces are diagnostic only — never fail the answer over a log write

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/docs/{doc_id}/forget")
def forget_doc(doc_id: str, request: Request) -> dict[str, str]:
    actor = _require_actor(request)
    forgotten_at = _now()
    with db() as conn:
        row = conn.execute(
            "SELECT source_type, org_id FROM docs WHERE id=?", (doc_id,)
        ).fetchone()
        if row is None or int(row["org_id"] or 1) != actor.org_id:
            raise HTTPException(404, "Document not found")
        source_type = row["source_type"]
        org_id = int(row["org_id"] or 1)
        # Purge FTS/vectors/graph BEFORE blanking the row below — the FTS5
        # 'delete' command needs the title/body that's actually indexed,
        # not the blanked-out text this function is about to write. The
        # docs row itself is kept (keep_row=True): forgotten=1 is the
        # tombstone `_persist_canonical_docs` checks so a later re-sync
        # can't resurrect this doc (§5.7/CP11.4).
        remove_docs(
            conn,
            _live_index_for(org_id),
            _hydra_store_for(org_id),
            [doc_id],
            keep_row=True,
        )
        conn.execute(
            """UPDATE docs SET title='[forgotten]', body='', content_hash='',
               url=NULL, timestamp=NULL, thread_id=NULL, parent_id=NULL,
               author_raw=NULL, container=NULL, extra_json='{}', forgotten=1,
               last_seen=? WHERE id=?""",
            (forgotten_at, doc_id),
        )
        conn.execute(
            """UPDATE connections SET doc_count=(
                 SELECT COUNT(*) FROM docs
                 WHERE source_type=connections.provider AND forgotten=0
                   AND org_id=connections.org_id)
               WHERE provider=? AND org_id=?""",
            (source_type, org_id),
        )

    # Forget is the one operation allowed to rewrite canonical history: remove
    # every body-bearing revision and leave one tombstone so rebuilds cannot
    # resurrect the document.
    canonical = DATA_DIR / "canonical" / f"{source_type}.jsonl"
    if canonical.exists():
        kept: list[str] = []
        for line in canonical.read_text().splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            if payload.get("doc_id") != doc_id:
                kept.append(line)
        kept.append(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "source_type": source_type,
                    "forgotten": True,
                    "forgotten_at": forgotten_at,
                }
            )
        )
        temporary = canonical.with_suffix(".jsonl.tmp")
        temporary.write_text("\n".join(kept) + "\n")
        temporary.replace(canonical)
    return {"status": "forgotten", "doc_id": doc_id}


# ── settings / profile / health ─────────────────────────────────────────────


@app.get("/api/settings")
def get_settings(request: Request) -> dict[str, Any]:
    actor = _require_actor(request)
    with db() as conn:
        s = _settings_map(conn, actor.org_id)
    mail_provider = joel_mail.provider_name(s)
    return {
        "llm_base_url": s.get("llm_base_url", ""),
        "llm_api_key_set": bool(s.get("llm_api_key")),
        "llm_model_distill": s.get("llm_model_distill", ""),
        "llm_model_extract": s.get("llm_model_extract", ""),
        "llm_model_answer": s.get("llm_model_answer", ""),
        "llm_model_resolve": s.get("llm_model_resolve", ""),
        "llm_model_rerank": s.get("llm_model_rerank", ""),
        "sync_enabled": s.get("sync_enabled", "true") == "true",
        "sync_default_interval_min": int(s.get("sync_default_interval_min", "15")),
        "history_floor": s.get("history_floor") or None,
        "composio_api_key_set": bool(s.get("composio_api_key")),
        "embed_model": s.get("embed_model", ""),
        "slack_signing_secret_set": bool(s.get("slack_signing_secret")),
        "mail_provider": mail_provider,
        "mail_configured": joel_mail.is_configured(s),
        "mail_from": s.get("mail_from", ""),
        "mail_from_name": s.get("mail_from_name", "joel"),
        "mail_app_url": s.get("mail_app_url", ""),
        "mail_smtp_host": s.get("mail_smtp_host", ""),
        "mail_smtp_port": s.get("mail_smtp_port", "587"),
        "mail_smtp_user": s.get("mail_smtp_user", ""),
        "mail_smtp_password_set": bool(s.get("mail_smtp_password")),
        "mail_smtp_tls": s.get("mail_smtp_tls", "true"),
        "mail_resend_api_key_set": bool(s.get("mail_resend_api_key")),
        "raw": {
            k: ("" if _is_secret_setting(k) else v)
            for k, v in s.items()
            if k
            in {
                "llm_base_url",
                "llm_api_key",
                "llm_model_distill",
                "llm_model_extract",
                "llm_model_answer",
                "llm_model_resolve",
                "llm_model_rerank",
                "sync_enabled",
                "embed_model",
                "mail_provider",
                "mail_from",
                "mail_from_name",
                "mail_app_url",
                "mail_smtp_host",
                "mail_smtp_port",
                "mail_smtp_user",
                "mail_smtp_password",
                "mail_smtp_tls",
                "mail_resend_api_key",
            }
        },
    }


@app.put("/api/settings")
def put_settings(body: SettingsIn, request: Request) -> dict[str, str]:
    actor = _require_admin(request)
    with db() as conn:
        for k, v in body.values.items():
            if k not in DEFAULT_SETTINGS:
                continue
            # don't wipe secrets on empty submit
            if _is_secret_setting(k) and v == "":
                continue
            if k == "mail_provider":
                provider = str(v).strip().lower()
                if provider not in joel_mail.PROVIDERS:
                    raise HTTPException(status_code=400, detail="Invalid mail provider")
                v = provider
            conn.execute(
                "INSERT INTO settings(org_id, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(org_id, key) DO UPDATE SET value=excluded.value",
                (actor.org_id, k, str(v)),
            )
    return {"status": "ok"}


@app.post("/api/settings/email/test")
def test_outbound_email(body: TestEmailIn, request: Request) -> dict[str, str]:
    actor = _require_admin(request)
    with db() as conn:
        settings = _settings_map(conn, actor.org_id)
    to = (body.to or actor.email).strip()
    if not to:
        raise HTTPException(status_code=400, detail="Enter a recipient email")
    try:
        result = joel_mail.try_send(settings, joel_mail.test_email(to=to))
    except joel_mail.MailError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=400, detail="Configure an email provider first"
        )
    return {"status": "sent", "provider": result.provider}


@app.get("/api/profile")
def get_profile(request: Request) -> dict[str, Any] | None:
    actor = _require_actor(request)
    with db() as conn:
        org = conn.execute("SELECT * FROM orgs WHERE id=?", (actor.org_id,)).fetchone()
        if org is None:
            return None
        spend = {
            r["stage"]: r["calls"]
            for r in conn.execute("SELECT * FROM spend WHERE org_id=?", (actor.org_id,))
        }
    return {
        "display_name": actor.display_name,
        "org": {
            "domain": org["domain"],
            "name": org["name"],
            "logo_url": org["logo_url"],
            "created_at": org["created_at"],
        },
        "corpus": {
            "docs": 0,
            "artifacts": 0,
            "entities": 0,
            "oldest_doc": None,
            "index": {
                "sqlite": 0,
                "vectors": 0,
                "graph": 0,
                "consistent": True,
            },
        },
        "spend_30d": spend,
    }


@app.put("/api/profile")
def put_profile(body: ProfileIn, request: Request) -> dict[str, str]:
    actor = _require_actor(request)
    if body.display_name is not None:
        with db() as conn:
            identity.update_display_name(conn, actor, body.display_name)
    return {"status": "ok"}


@app.put("/api/profile/password")
def put_profile_password(body: PasswordIn, request: Request) -> dict[str, str]:
    actor = _require_actor(request)
    try:
        with db() as conn:
            identity.change_password(
                conn,
                actor,
                current_password=body.current_password,
                new_password=body.new_password,
            )
    except identity.IdentityError as extra:
        raise _identity_error(extra) from extra
    return {"status": "ok"}


# ── API keys (§13's MCP surface identity) ───────────────────────────────────


class ApiKeyIn(BaseModel):
    label: str = "API key"


@app.get("/api/api-keys")
def list_api_keys_route(request: Request) -> list[dict[str, Any]]:
    actor = _require_actor(request)
    with db() as conn:
        rows = identity.list_api_keys(conn, actor)
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "last4": r["key_last4"],
            "created_at": r["created_at"],
            "last_used_at": r["last_used_at"],
        }
        for r in rows
    ]


@app.post("/api/api-keys")
def create_api_key_route(body: ApiKeyIn, request: Request) -> dict[str, str]:
    """The raw key is returned exactly once, here -- only its hash is ever
    stored (identity.py's create_api_key), same as an invite token."""
    actor = _require_actor(request)
    with db() as conn:
        key_id, raw = identity.create_api_key(conn, actor, body.label)
    return {"id": key_id, "key": raw}


@app.delete("/api/api-keys/{key_id}")
def delete_api_key_route(key_id: str, request: Request) -> dict[str, str]:
    actor = _require_actor(request)
    with db() as conn:
        removed = identity.revoke_api_key(conn, actor, key_id)
    if not removed:
        raise HTTPException(404, "Key not found")
    return {"status": "ok"}


@app.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    actor = _require_actor(request)
    with db() as conn:
        s = _settings_map(conn, actor.org_id)
        connectors = []
        for r in conn.execute("SELECT * FROM connections WHERE org_id=?", (actor.org_id,)):
            connectors.append(
                {
                    "provider": r["provider"],
                    "status": r["status"],
                    "last_success": r["last_sync_at"],
                    "next_run": r["next_sync_at"],
                }
            )
        spend = {
            r["stage"]: r["calls"]
            for r in conn.execute("SELECT * FROM spend WHERE org_id=?", (actor.org_id,))
        }
        schema_version_row = conn.execute(
            "SELECT version FROM schema_version"
        ).fetchone()
        queue_depth = conn.execute(
            """SELECT COUNT(*) AS n FROM jobs j
               JOIN connections c ON c.id = j.connection_id
               WHERE j.status='running' AND c.org_id=?""",
            (actor.org_id,),
        ).fetchone()["n"]
        sqlite_count = conn.execute(
            "SELECT COUNT(*) AS n FROM docs WHERE forgotten=0 AND org_id=?",
            (actor.org_id,),
        ).fetchone()["n"]
        oldest_doc = conn.execute(
            """SELECT MIN(timestamp) AS t FROM docs
               WHERE forgotten=0 AND timestamp IS NOT NULL AND org_id=?""",
            (actor.org_id,),
        ).fetchone()["t"]
        artifact_count = conn.execute(
            """SELECT COUNT(*) AS n FROM docs
               WHERE forgotten=0 AND granularity='artifact' AND org_id=?""",
            (actor.org_id,),
        ).fetchone()["n"]

    # §14.1: the index triple is the drift detector — a real live count on
    # all three sides, not a hardcoded stub that always claims "consistent".
    # HydraDB unreachable degrades this cleanly (§14.6) rather than 500ing
    # the whole endpoint: hydra_status carries the real error, graph/entity
    # counts come back None, and "consistent" is None (unknown) rather than
    # a false True or a false False.
    vectors_count: int | None = None
    graph_count: int | None = None
    entity_count: int | None = None
    hydra_status = "ok"
    try:
        snap = _live_index_for(actor.org_id).snapshot()
        vectors_count = int((~snap.forgotten).sum())
        graph_count = _hydra_store_for(actor.org_id).count_nodes("Doc")
        entity_count = _hydra_store_for(actor.org_id).count_nodes("Entity")
    except Exception as exc:
        hydra_status = f"error: {exc}"

    consistent = (
        None
        if graph_count is None
        else sqlite_count == vectors_count == graph_count
    )

    return {
        "hydra": hydra_status,
        "schema_version": schema_version_row[0] if schema_version_row else 0,
        "sync_enabled": s.get("sync_enabled", "true") == "true",
        "queue_depth": queue_depth,
        "llm_error": None
        if s.get("llm_api_key")
        else "LLM API key not set — add one in Settings",
        "index": {
            "sqlite": sqlite_count,
            "vectors": vectors_count,
            "graph": graph_count,
            "consistent": consistent,
        },
        "connectors": connectors,
        "corpus": {
            "oldest_doc": oldest_doc,
            "artifacts": artifact_count,
            "entities": entity_count,
        },
        "spend_30d": spend,
    }


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Keep module importable as joel.routes for older layout
