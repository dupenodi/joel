"""Joel API — bootable app surface over SQLite (§12.2).

Hydra / ingest / retrieval stay stubs for now; the product UI is fully
wired against these endpoints with empty corpus semantics.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from joel.adapters import triage_batch
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
from joel.syncer import ingest_is_schedulable, start_scheduler
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
from joel.connectors.slack import SlackAPIError, SlackClient, fetch_slack_docs
from joel.config import Settings
from joel.hydra import Hydra
from joel.live_index import LiveIndex
from joel.llm import make_openrouter_caller
from joel.models import CanonicalDoc
from joel.pipeline import run_store_pipeline
from joel.store import HydraStore

DATA_DIR = Path(os.getenv("JOEL_DATA", "data"))
DB_PATH = DATA_DIR / "index" / "joel.db"

# Store-layer singletons (Hydra driver, HydraStore, LiveIndex, embedding
# model) -- built lazily on first real use, never at import time, so
# anything that only needs SQLite (most of the test scripts, most routes)
# never pays for a Hydra connection or a model load. Long-lived by design:
# Hydra's driver and the embedding model are meant to be constructed once
# and reused, not per-request.
_RUNTIME: dict[str, Any] = {}
_RUNTIME_LOCK = threading.Lock()


def _runtime() -> dict[str, Any]:
    with _RUNTIME_LOCK:
        if "embed_model" not in _RUNTIME:
            from sentence_transformers import SentenceTransformer

            settings = Settings.from_env()
            _RUNTIME["settings"] = settings
            _RUNTIME["embed_model"] = SentenceTransformer(settings.embed_model)
        if "hydra_store" not in _RUNTIME:
            hydra = Hydra(_RUNTIME["settings"])
            _RUNTIME["hydra"] = hydra
            _RUNTIME["hydra_store"] = HydraStore(hydra)
        if "live_index" not in _RUNTIME:
            dim = _RUNTIME["embed_model"].get_sentence_embedding_dimension()
            _RUNTIME["live_index"] = LiveIndex(DATA_DIR / "index" / "joel.npz", dim=dim)
        return _RUNTIME


def _embed_fn(texts: list[str]):
    return _runtime()["embed_model"].encode(texts, normalize_embeddings=True)

PROVIDER_LABELS = {item.id: item.name for item in INTEGRATIONS}
DEFAULT_INTERVAL = {item.id: item.default_interval_min for item in INTEGRATIONS}
RETURN_PATHS = {
    "connectors": "/connectors",
    "onboarding": "/onboarding",
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
    "sync_default_interval_min": "15",
    "history_floor": "",
    "composio_api_key": "",
    "embed_model": "BAAI/bge-small-en-v1.5",
    "display_name": "You",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _derive_name(domain: str) -> str:
    host = domain.replace("https://", "").replace("http://", "").split("/")[0]
    host = host.removeprefix("www.")
    base = host.split(".")[0] or host
    return base[:1].upper() + base[1:]


def _favicon(domain: str) -> str:
    host = domain.replace("https://", "").replace("http://", "").split("/")[0]
    return f"https://www.google.com/s2/favicons?domain={host}&sz=128"


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


def init_db() -> None:
    with db() as conn:
        run_migrations(conn)
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (k, v),
            )
        for stage in ("distill", "extract", "answer", "resolve", "rerank"):
            conn.execute(
                "INSERT OR IGNORE INTO spend(stage, calls) VALUES (?, 0)",
                (stage,),
            )


def _settings_map(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


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
    conn: sqlite3.Connection, docs: list[CanonicalDoc]
) -> tuple[dict[str, int], list[CanonicalDoc]]:
    """Append new/changed canonical lines and update the disposable docs
    index. Returns (counts, dirty_docs) — dirty_docs (new+changed) is what
    the store pipeline (pipeline.py) needs to know what to upsert/re-distill;
    unchanged docs need no further work downstream."""
    rows = conn.execute(
        "SELECT id, content_hash, forgotten FROM docs"
    ).fetchall()
    forgotten_ids = {r["id"] for r in rows if r["forgotten"]}
    known = {
        r["id"]: r["content_hash"]
        for r in rows
        if not r["forgotten"]
    }
    ignored_forgotten = sum(doc.doc_id in forgotten_ids for doc in docs)
    docs = [doc for doc in docs if doc.doc_id not in forgotten_ids]
    report = triage_batch(docs, known)
    seen_at = _now()
    for doc in report.unchanged:
        conn.execute("UPDATE docs SET last_seen=? WHERE id=?", (seen_at, doc.doc_id))

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
                 extra_json, first_seen, last_seen, forgotten)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, body=excluded.body,
                 content_hash=excluded.content_hash, url=excluded.url,
                 timestamp=excluded.timestamp, thread_id=excluded.thread_id,
                 parent_id=excluded.parent_id, author_raw=excluded.author_raw,
                 container=excluded.container, extra_json=excluded.extra_json,
                 last_seen=excluded.last_seen, forgotten=0""",
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


class OrgIn(BaseModel):
    domain: str


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


class ConversationIn(BaseModel):
    title: str | None = None


class AskIn(BaseModel):
    conversation_id: str
    question: str


class ProfileIn(BaseModel):
    display_name: str | None = None


class SettingsIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class WipeIn(BaseModel):
    domain: str


# ── app ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="joel-api", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ready_timers: dict[str, threading.Thread] = {}
_scheduler_stop: threading.Event | None = None


def _scheduler_tick() -> None:
    with db() as conn:
        settings = _settings_map(conn)
        if settings.get("sync_enabled", "true").lower() in {"0", "false", "no"}:
            return
        now = _now()
        rows = conn.execute(
            """SELECT id, provider, channel_ids_json FROM connections
               WHERE paused=0 AND status='ready'
                 AND next_sync_at IS NOT NULL AND next_sync_at<=?
                 AND id NOT IN (SELECT connection_id FROM jobs WHERE status='running')""",
            (now,),
        ).fetchall()
    for row in rows:
        provider = str(row["provider"])
        if provider not in INGEST_PROVIDERS:
            continue
        if not ingest_is_schedulable(provider, _channel_ids(row)):
            continue
        try:
            _start_ingest(row["id"], first_sync=False, provider=provider)
        except Exception:
            continue


@app.on_event("startup")
def _startup() -> None:
    global _scheduler_stop
    init_db()
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
        "error": r["error"],
        "interval_min": r["interval_min"],
        "lookback_days": r["lookback_days"] if "lookback_days" in r.keys() else 30,
        "channel_ids": _channel_ids(r),
        "coming_soon": False,
        "ingest": r["provider"] in INGEST_PROVIDERS,
        "checklist": _parse_checklist(r["checklist_json"]),
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


def _run_ingest(
    connection_id: str, job_id: str, *, first_sync: bool, provider: str
) -> None:
    started = time.monotonic()
    try:
        with db() as conn:
            credentials = _credential(conn, connection_id)
            settings = _settings_map(conn)
            row = conn.execute(
                "SELECT lookback_days, channel_ids_json FROM connections WHERE id=?",
                (connection_id,),
            ).fetchone()
        docs = _fetch_provider_docs(provider, credentials, settings, row)
        with db() as conn:
            counts, dirty_docs = _persist_canonical_docs(conn, docs)
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
                        "SELECT COUNT(*) AS n FROM docs WHERE source_type=? AND forgotten=0",
                        (provider,),
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
                rt = _runtime()
                llm_call = (
                    make_openrouter_caller(settings) if settings.get("llm_api_key") else None
                )
                with db() as conn:
                    pipeline_report = run_store_pipeline(
                        conn, rt["live_index"], rt["hydra_store"], _embed_fn, llm_call, dirty_docs
                    )
                if pipeline_report.distill_errors:
                    pipeline_error = "; ".join(pipeline_report.distill_errors[:3])
        except Exception as exc:  # store/distill failure must not sink an otherwise-good sync
            pipeline_error = str(exc)

        # people_resolved/graph_linked are ontology (§9/CP6 — not built yet),
        # still simulated pacing for the onboarding UI. distilled and
        # indexes_consistent are real now (the pipeline call above).
        if first_sync:
            for key, status, progress in (
                ("distilled", "distilling", 0.55),
                ("people_resolved", "linking", 0.72),
                ("graph_linked", "linking", 0.88),
                ("indexes_consistent", "ready", 1.0),
            ):
                if key in ("people_resolved", "graph_linked"):
                    time.sleep(0.4)
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

        finished = _now()
        with db() as conn:
            interval = conn.execute(
                "SELECT interval_min FROM connections WHERE id=?", (connection_id,)
            ).fetchone()["interval_min"]
            conn.execute(
                """UPDATE connections SET status='ready', last_sync_at=?,
                   next_sync_at=?, backfill_done=1, backfill_progress=NULL,
                   error=NULL WHERE id=?""",
                (
                    finished,
                    datetime.fromtimestamp(
                        time.time() + interval * 60, timezone.utc
                    ).isoformat(),
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
        with db() as conn:
            conn.execute(
                "UPDATE connections SET status=?, error=? WHERE id=?",
                ("needs_reauth" if _is_reauth(exc) else "error", str(exc), connection_id),
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


def _upsert_connection(
    provider: str,
    mode: str,
    credentials: dict[str, Any],
    *,
    lookback_days: int = 30,
    status: str = "backfilling",
    reset_progress: bool = True,
) -> tuple[str, bool]:
    spec = INTEGRATION_BY_ID[provider]
    with db() as conn:
        if conn.execute("SELECT id FROM orgs WHERE id=1").fetchone() is None:
            raise HTTPException(400, "Create an org first")
        existing = conn.execute(
            "SELECT id FROM connections WHERE provider=?", (provider,)
        ).fetchone()
        created = existing is None
        connection_id = (
            existing["id"] if existing else f"conn_{provider}_{uuid.uuid4().hex[:8]}"
        )
        if created:
            conn.execute(
                """INSERT INTO connections(
                     id, provider, mode, status, interval_min, checklist_json,
                     created_at, backfill_progress, lookback_days)
                   VALUES (?,?,?,?,?,?,?,0.05,?)""",
                (
                    connection_id,
                    provider,
                    mode,
                    status,
                    spec.default_interval_min,
                    json.dumps(_checklist_default()),
                    _now(),
                    lookback_days,
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
    }


def _app_redirect(origin: str, return_to: str, **params: str) -> RedirectResponse:
    path = RETURN_PATHS.get(return_to, RETURN_PATHS["connectors"])
    try:
        origin = validate_return_to(origin)
    except OAuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    target = origin.rstrip("/") + path
    return _oauth_redirect(target, **params)


def _pending_lookback(toolkit: str) -> tuple[int, str, str]:
    with db() as conn:
        row = conn.execute(
            "SELECT lookback_days, return_to, origin FROM pending_connects WHERE toolkit=?",
            (toolkit,),
        ).fetchone()
    if row is None:
        return 30, "connectors", ""
    days = int(row["lookback_days"] or 30)
    if days not in LOOKBACK_DAYS:
        days = 30
    return days, str(row["return_to"] or "connectors"), str(row["origin"] or "")


def _activate_composio_toolkit(
    toolkit: str,
    *,
    lookback_days: int,
    start_sync: bool,
    account_id: str | None = None,
) -> str | None:
    spec = INTEGRATION_BY_TOOLKIT.get(toolkit)
    if spec is None or not spec.connectable:
        return None
    with db() as conn:
        settings = _settings_map(conn)
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
        lookback_days=lookback_days,
        status=status,
        reset_progress=start_sync,
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


# ── org ─────────────────────────────────────────────────────────────────────


@app.get("/api/org")
def get_org() -> dict[str, Any]:
    with db() as conn:
        org = conn.execute("SELECT * FROM orgs WHERE id=1").fetchone()
        providers = tuple(sorted(INGEST_PROVIDERS))
        placeholders = ",".join("?" * len(providers))
        first = conn.execute(
            f"""SELECT * FROM connections
               WHERE provider IN ({placeholders})
               ORDER BY backfill_done DESC, created_at ASC LIMIT 1""",
            providers,
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


@app.post("/api/org")
def create_org(body: OrgIn) -> dict[str, Any]:
    domain = (
        body.domain.strip()
        .removeprefix("https://")
        .removeprefix("http://")
        .split("/")[0]
        .lower()
    )
    if "." not in domain:
        raise HTTPException(400, "Enter a domain like yourco.dev")
    org = {
        "domain": domain,
        "name": _derive_name(domain),
        "logo_url": _favicon(domain),
        "created_at": _now(),
    }
    with db() as conn:
        existing = conn.execute("SELECT domain FROM orgs WHERE id=1").fetchone()
        if existing:
            conn.execute(
                "UPDATE orgs SET domain=?, name=?, logo_url=? WHERE id=1",
                (org["domain"], org["name"], org["logo_url"]),
            )
            org["created_at"] = (
                conn.execute("SELECT created_at FROM orgs WHERE id=1").fetchone()[
                    "created_at"
                ]
            )
        else:
            conn.execute(
                "INSERT INTO orgs(id, domain, name, logo_url, created_at) VALUES (1,?,?,?,?)",
                (org["domain"], org["name"], org["logo_url"], org["created_at"]),
            )
    return org


@app.post("/api/org/wipe")
def wipe_org(body: WipeIn) -> dict[str, str]:
    with db() as conn:
        org = conn.execute("SELECT domain FROM orgs WHERE id=1").fetchone()
        if org is None or org["domain"] != body.domain.strip().lower():
            raise HTTPException(400, "Domain confirmation does not match")
        for table in (
            "messages",
            "conversations",
            "jobs",
            "connector_credentials",
            "connections",
            "oauth_states",
            "docs",
            "orgs",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("UPDATE spend SET calls=0")
    return {"status": "wiped"}


# ── connectors ──────────────────────────────────────────────────────────────


@app.get("/api/connectors")
def list_connectors() -> list[dict[str, Any]]:
    with db() as conn:
        rows = {
            r["provider"]: r
            for r in conn.execute("SELECT * FROM connections").fetchall()
        }
    out: list[dict[str, Any]] = []
    for spec in INTEGRATIONS:
        if spec.id in rows:
            card = _row_connector(rows[spec.id])
            card["coming_soon"] = not spec.connectable
            card["ingest"] = spec.ingest
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
def delete_connector(connection_id: str) -> dict[str, str]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE id=?", (connection_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Not found")
        cred_row = conn.execute(
            "SELECT encrypted_json FROM connector_credentials WHERE connection_id=?",
            (connection_id,),
        ).fetchone()
        settings = _settings_map(conn)
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
def sync_now(connection_id: str) -> dict[str, str]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE id=?", (connection_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Not found")
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


@app.patch("/api/connectors/{connection_id}")
def patch_connector(connection_id: str, body: ConnectorPatch) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE id=?", (connection_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Not found")
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
def list_connector_channels(connection_id: str) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE id=?", (connection_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Not found")
        if row["provider"] != "slack":
            raise HTTPException(400, "Channel picker is only for Slack")
        credentials = _credential(conn, connection_id)
        settings = _settings_map(conn)
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
def composio_status() -> dict[str, Any]:
    with db() as conn:
        settings = _settings_map(conn)
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
                for r in conn.execute("SELECT provider FROM connections").fetchall()
            }
        for account in accounts:
            spec = INTEGRATION_BY_TOOLKIT.get(account["toolkit"])
            if spec is None or spec.id in known:
                continue
            lookback, _return_to, _origin = _pending_lookback(account["toolkit"])
            try:
                _activate_composio_toolkit(
                    account["toolkit"],
                    lookback_days=lookback,
                    start_sync=False,
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
        return {
            "configured": True,
            "key_source": source,
            "masked_key": mask_api_key(api_key),
            "accounts": [],
            "error": str(exc),
        }


@app.put("/api/composio/key")
def set_composio_key(body: ComposioKeyIn) -> dict[str, Any]:
    with db() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("composio_api_key", (body.api_key or "").strip()),
        )
        settings = _settings_map(conn)
    api_key, source = resolve_composio_key(settings)
    return {
        "configured": bool(api_key),
        "key_source": source,
        "masked_key": mask_api_key(api_key) if api_key else None,
    }


@app.post("/api/composio/connect")
def composio_connect(body: ComposioConnectIn) -> dict[str, str]:
    try:
        spec = require_connectable(body.toolkit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if body.lookback_days not in LOOKBACK_DAYS:
        raise HTTPException(400, "Lookback must be 7, 30, 90, or 365 days")
    if body.return_to not in RETURN_PATHS:
        raise HTTPException(400, "return_to must be connectors or onboarding")
    try:
        origin = validate_return_to(body.origin.strip())
    except OAuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    with db() as conn:
        if conn.execute("SELECT id FROM orgs WHERE id=1").fetchone() is None:
            raise HTTPException(400, "Create an org first")
        settings = _settings_map(conn)
        conn.execute(
            """INSERT INTO pending_connects(toolkit, lookback_days, return_to, origin, created_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(toolkit) DO UPDATE SET
                 lookback_days=excluded.lookback_days,
                 return_to=excluded.return_to,
                 origin=excluded.origin,
                 created_at=excluded.created_at""",
            (spec.toolkit, body.lookback_days, body.return_to, origin, _now()),
        )
    callback_url = (
        f"{origin.rstrip('/')}/api/composio/callback"
        f"?toolkit={spec.toolkit}&returnTo={body.return_to}"
    )
    try:
        redirect_url = start_toolkit_connect(
            get_composio(settings),
            spec.toolkit,
            callback_url,
            body.auth_config_id,
        )
    except ComposioError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
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
    lookback, stored_return, origin = _pending_lookback(slug)
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
            account_id=connected_account_id,
        )
    except Exception as exc:
        return _app_redirect(origin, return_to, error=str(exc))
    return _app_redirect(origin, return_to, connected=slug)


# ── conversations / ask ─────────────────────────────────────────────────────


@app.get("/api/conversations")
def list_conversations() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY created_at DESC"
        ).fetchall()
    return [
        {"id": r["id"], "title": r["title"], "created_at": r["created_at"]}
        for r in rows
    ]


@app.post("/api/conversations")
def create_conversation(body: ConversationIn) -> dict[str, Any]:
    cid = f"c_{uuid.uuid4().hex[:12]}"
    title = (body.title or "New conversation").strip() or "New conversation"
    created = _now()
    with db() as conn:
        conn.execute(
            "INSERT INTO conversations(id, title, created_at) VALUES (?,?,?)",
            (cid, title, created),
        )
    return {"id": cid, "title": title, "created_at": created}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict[str, Any]:
    with db() as conn:
        c = conn.execute(
            "SELECT * FROM conversations WHERE id=?", (conversation_id,)
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


@app.post("/api/ask")
def ask(body: AskIn) -> StreamingResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Empty question")

    with db() as conn:
        c = conn.execute(
            "SELECT * FROM conversations WHERE id=?", (body.conversation_id,)
        ).fetchone()
        if c is None:
            raise HTTPException(404, "Conversation not found")
        ready = conn.execute(
            """SELECT id FROM connections WHERE json_extract(checklist_json, '$.ready') = 1
               OR status='ready' LIMIT 1"""
        ).fetchone()
        # sqlite json_extract may not work on all; fallback:
        if ready is None:
            for r in conn.execute("SELECT id, checklist_json, status FROM connections"):
                cl = _parse_checklist(r["checklist_json"])
                if cl.get("ready") or r["status"] == "ready":
                    ready = r
                    break
        if ready is None:
            raise HTTPException(
                409, "Chat locked until the first connector is ready"
            )

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
        # Agent pipeline events — empty corpus → honest absent
        yield _sse("status", {"stage": "rewriting"})
        time.sleep(0.15)
        yield _sse(
            "rewritten",
            {"question": question, "kind": "knowledge"},
        )
        yield _sse("status", {"stage": "planning"})
        time.sleep(0.1)
        yield _sse(
            "plan",
            {
                "lanes": ["vector", "fts", "artifacts", "phrase", "graph", "who_knows"],
                "intent": "knowledge",
            },
        )
        for lane in ("vector", "fts", "artifacts", "phrase", "graph", "who_knows"):
            yield _sse(
                "lane",
                {
                    "lane": lane,
                    "status": "done",
                    "hits": 0,
                    "provider": None,
                },
            )
            time.sleep(0.05)
        yield _sse("status", {"stage": "reranking"})
        time.sleep(0.1)
        yield _sse(
            "tool_call",
            {
                "id": "t_live_1",
                "name": "live_lookup",
                "provider": None,
                "status": "skipped",
                "detail": "No authorized live target for an empty corpus",
            },
        )
        yield _sse("status", {"stage": "answering"})
        answer = "Not in the company's memory."
        for token in answer.split(" "):
            yield _sse("token", {"text": token + " "})
            time.sleep(0.03)
        assistant = {
            "role": "assistant",
            "content": answer,
            "status": "absent",
            "citations": [],
            "lanes": [],
            "reasoning_path": [],
            "tool_calls": [
                {
                    "id": "t_live_1",
                    "name": "live_lookup",
                    "provider": None,
                    "status": "skipped",
                    "detail": "No authorized live target for an empty corpus",
                }
            ],
            "conflicts": [],
            "not_found": [],
        }
        yield _sse("citations", {"citations": []})
        yield _sse("reasoning_path", {"paths": []})
        yield _sse("done", {"status": "absent", "message": assistant})

        with db() as conn:
            mid = f"m_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO messages(id, conversation_id, role, content_json, created_at)
                   VALUES (?,?,?,?,?)""",
                (
                    mid,
                    body.conversation_id,
                    "assistant",
                    json.dumps(assistant),
                    _now(),
                ),
            )
            conn.execute(
                "UPDATE spend SET calls = calls + 1 WHERE stage='answer'"
            )

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/docs/{doc_id}/forget")
def forget_doc(doc_id: str) -> dict[str, str]:
    forgotten_at = _now()
    with db() as conn:
        row = conn.execute(
            "SELECT source_type FROM docs WHERE id=?", (doc_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Document not found")
        source_type = row["source_type"]
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
                 WHERE source_type=connections.provider AND forgotten=0)
               WHERE provider=?""",
            (source_type,),
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
def get_settings() -> dict[str, Any]:
    with db() as conn:
        s = _settings_map(conn)
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
        "raw": {
            k: ("" if k.endswith("key") or k.endswith("secret") else v)
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
            }
        },
    }


@app.put("/api/settings")
def put_settings(body: SettingsIn) -> dict[str, str]:
    with db() as conn:
        for k, v in body.values.items():
            if k not in DEFAULT_SETTINGS:
                continue
            # don't wipe secrets on empty submit
            if (k.endswith("key") or k.endswith("secret")) and v == "":
                continue
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, str(v)),
            )
    return {"status": "ok"}


@app.get("/api/profile")
def get_profile() -> dict[str, Any] | None:
    with db() as conn:
        org = conn.execute("SELECT * FROM orgs WHERE id=1").fetchone()
        if org is None:
            return None
        s = _settings_map(conn)
        spend = {
            r["stage"]: r["calls"] for r in conn.execute("SELECT * FROM spend")
        }
    return {
        "display_name": s.get("display_name", "You"),
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
def put_profile(body: ProfileIn) -> dict[str, str]:
    if body.display_name is not None:
        with db() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES ('display_name', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (body.display_name.strip() or "You",),
            )
    return {"status": "ok"}


@app.get("/api/health")
def health() -> dict[str, Any]:
    with db() as conn:
        s = _settings_map(conn)
        connectors = []
        for r in conn.execute("SELECT * FROM connections"):
            connectors.append(
                {
                    "provider": r["provider"],
                    "status": r["status"],
                    "last_success": r["last_sync_at"],
                    "next_run": r["next_sync_at"],
                }
            )
        spend = {
            r["stage"]: r["calls"] for r in conn.execute("SELECT * FROM spend")
        }
        schema_version_row = conn.execute(
            "SELECT version FROM schema_version"
        ).fetchone()
    return {
        "hydra": "ok",  # stub — real hydra wire comes later
        "schema_version": schema_version_row[0] if schema_version_row else 0,
        "sync_enabled": s.get("sync_enabled", "true") == "true",
        "queue_depth": 0,
        "llm_error": None
        if s.get("llm_api_key")
        else "LLM API key not set — add one in Settings",
        "index": {"sqlite": 0, "vectors": 0, "graph": 0, "consistent": True},
        "connectors": connectors,
        "corpus": {"oldest_doc": None, "artifacts": 0, "entities": 0},
        "spend_30d": spend,
    }


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Keep module importable as joel.routes for older layout
