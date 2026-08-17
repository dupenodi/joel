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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

DATA_DIR = Path(os.getenv("JOEL_DATA", "data"))
DB_PATH = DATA_DIR / "index" / "joel.db"

SHIPPED = ("slack", "github", "gmail")
COMING_SOON = (
    "jira",
    "linear",
    "notion",
    "confluence",
    "googledrive",
    "hubspot",
    "fireflies",
)
PROVIDER_LABELS = {
    "slack": "Slack",
    "github": "GitHub",
    "gmail": "Gmail",
    "jira": "Jira",
    "linear": "Linear",
    "notion": "Notion",
    "confluence": "Confluence",
    "googledrive": "Google Drive",
    "hubspot": "HubSpot",
    "fireflies": "Fireflies",
}
DEFAULT_INTERVAL = {
    "slack": 15,
    "github": 30,
    "gmail": 20,
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
    "oauth_slack_client_id": "",
    "oauth_slack_client_secret": "",
    "oauth_github_client_id": "",
    "oauth_github_client_secret": "",
    "oauth_gmail_client_id": "",
    "oauth_gmail_client_secret": "",
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


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS orgs (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              domain TEXT NOT NULL,
              name TEXT NOT NULL,
              logo_url TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS connections (
              id TEXT PRIMARY KEY,
              provider TEXT NOT NULL UNIQUE,
              mode TEXT,
              status TEXT NOT NULL,
              doc_count INTEGER NOT NULL DEFAULT 0,
              last_sync_at TEXT,
              next_sync_at TEXT,
              backfill_done INTEGER NOT NULL DEFAULT 0,
              backfill_progress REAL,
              error TEXT,
              interval_min INTEGER NOT NULL DEFAULT 15,
              paused INTEGER NOT NULL DEFAULT 0,
              checklist_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              connection_id TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT,
              status TEXT NOT NULL,
              new_count INTEGER NOT NULL DEFAULT 0,
              changed_count INTEGER NOT NULL DEFAULT 0,
              unchanged_count INTEGER NOT NULL DEFAULT 0,
              duration_ms INTEGER,
              error TEXT,
              FOREIGN KEY(connection_id) REFERENCES connections(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS conversations (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY,
              conversation_id TEXT NOT NULL,
              role TEXT NOT NULL,
              content_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS spend (
              stage TEXT PRIMARY KEY,
              calls INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version(version) VALUES (1)")
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


# ── request bodies ──────────────────────────────────────────────────────────


class OrgIn(BaseModel):
    domain: str


class ConnectorIn(BaseModel):
    provider: str
    mode: str = "composio"


class ConnectorPatch(BaseModel):
    interval_min: int | None = None
    paused: bool | None = None
    history_floor: str | None = None


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


@app.on_event("startup")
def _startup() -> None:
    init_db()


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
        "coming_soon": False,
        "checklist": _parse_checklist(r["checklist_json"]),
    }


def _simulate_first_sync(connection_id: str) -> None:
    """Advance checklist without real ingest — empty corpus, ready gate."""
    steps = [
        ("fetched", "backfilling", 0.15),
        ("distilled", "distilling", 0.45),
        ("people_resolved", "linking", 0.7),
        ("graph_linked", "linking", 0.9),
        ("indexes_consistent", "ready", 1.0),
    ]
    for key, status, progress in steps:
        time.sleep(1.2)
        with db() as conn:
            row = conn.execute(
                "SELECT checklist_json FROM connections WHERE id=?",
                (connection_id,),
            ).fetchone()
            if row is None:
                return
            cl = _parse_checklist(row["checklist_json"])
            cl[key] = True
            if key == "indexes_consistent":
                cl["ready"] = True
            conn.execute(
                """UPDATE connections SET checklist_json=?, status=?,
                   backfill_progress=?, last_sync_at=?, next_sync_at=?,
                   backfill_done=?, doc_count=? WHERE id=?""",
                (
                    json.dumps(cl),
                    status,
                    progress if not cl["ready"] else None,
                    _now() if cl["ready"] else None,
                    datetime.fromtimestamp(
                        time.time() + 15 * 60, timezone.utc
                    ).isoformat()
                    if cl["ready"]
                    else None,
                    1 if cl["ready"] else 0,
                    0,  # empty corpus
                    connection_id,
                ),
            )
            if cl["ready"]:
                job_id = f"job_{uuid.uuid4().hex[:10]}"
                conn.execute(
                    """INSERT INTO jobs(id, connection_id, started_at, finished_at,
                       status, new_count, changed_count, unchanged_count, duration_ms, error)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        job_id,
                        connection_id,
                        _now(),
                        _now(),
                        "ok",
                        0,
                        0,
                        0,
                        4800,
                        None,
                    ),
                )


# ── org ─────────────────────────────────────────────────────────────────────


@app.get("/api/org")
def get_org() -> dict[str, Any]:
    with db() as conn:
        org = conn.execute("SELECT * FROM orgs WHERE id=1").fetchone()
        first = conn.execute(
            "SELECT * FROM connections ORDER BY created_at ASC LIMIT 1"
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
            "connections",
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
    for p in SHIPPED:
        if p in rows:
            out.append(_row_connector(rows[p]))
        else:
            out.append(
                {
                    "id": None,
                    "provider": p,
                    "label": PROVIDER_LABELS[p],
                    "status": "pending_auth",
                    "mode": None,
                    "doc_count": 0,
                    "last_sync_at": None,
                    "next_sync_at": None,
                    "backfill_done": False,
                    "backfill_progress": None,
                    "error": None,
                    "interval_min": DEFAULT_INTERVAL.get(p, 15),
                    "coming_soon": False,
                    "checklist": _checklist_default(),
                }
            )
    for p in COMING_SOON:
        out.append(
            {
                "id": None,
                "provider": p,
                "label": PROVIDER_LABELS[p],
                "status": "coming_soon",
                "mode": None,
                "doc_count": 0,
                "last_sync_at": None,
                "next_sync_at": None,
                "backfill_done": False,
                "backfill_progress": None,
                "error": None,
                "interval_min": 60,
                "coming_soon": True,
                "checklist": _checklist_default(),
            }
        )
    return out


@app.post("/api/connectors")
def create_connector(body: ConnectorIn) -> dict[str, Any]:
    if body.provider not in SHIPPED:
        raise HTTPException(400, "Provider not available yet")
    with db() as conn:
        if conn.execute("SELECT id FROM orgs WHERE id=1").fetchone() is None:
            raise HTTPException(400, "Create an org first")
        existing = conn.execute(
            "SELECT id FROM connections WHERE provider=?", (body.provider,)
        ).fetchone()
        if existing:
            raise HTTPException(409, "Already connected")
        cid = f"conn_{body.provider}_{uuid.uuid4().hex[:8]}"
        cl = _checklist_default()
        conn.execute(
            """INSERT INTO connections(
                 id, provider, mode, status, interval_min, checklist_json, created_at,
                 backfill_progress)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                cid,
                body.provider,
                body.mode,
                "backfilling",
                DEFAULT_INTERVAL.get(body.provider, 15),
                json.dumps(cl),
                _now(),
                0.05,
            ),
        )
        row = conn.execute("SELECT * FROM connections WHERE id=?", (cid,)).fetchone()
    t = threading.Thread(
        target=_simulate_first_sync, args=(cid,), daemon=True, name=f"sync-{cid}"
    )
    _ready_timers[cid] = t
    t.start()
    return _row_connector(row)


@app.delete("/api/connectors/{connection_id}")
def delete_connector(connection_id: str) -> dict[str, str]:
    with db() as conn:
        cur = conn.execute("DELETE FROM connections WHERE id=?", (connection_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Not found")
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
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        started = _now()
        conn.execute(
            """INSERT INTO jobs(id, connection_id, started_at, status,
               new_count, changed_count, unchanged_count)
               VALUES (?,?,?,'running',0,0,0)""",
            (job_id, connection_id, started),
        )
        conn.execute(
            "UPDATE connections SET status='syncing' WHERE id=?", (connection_id,)
        )
    # Instant empty sync — no real fetch
    time.sleep(0.3)
    with db() as conn:
        conn.execute(
            """UPDATE jobs SET finished_at=?, status='ok', unchanged_count=0,
               duration_ms=? WHERE id=?""",
            (_now(), 300, job_id),
        )
        interval = conn.execute(
            "SELECT interval_min FROM connections WHERE id=?", (connection_id,)
        ).fetchone()["interval_min"]
        conn.execute(
            """UPDATE connections SET status='ready', last_sync_at=?, next_sync_at=?
               WHERE id=?""",
            (
                _now(),
                datetime.fromtimestamp(
                    time.time() + interval * 60, timezone.utc
                ).isoformat(),
                connection_id,
            ),
        )
    return {"job_id": job_id}


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
    # Empty corpus — acknowledge the control
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
        "oauth": {
            p: {
                "client_id_set": bool(s.get(f"oauth_{p}_client_id")),
                "client_secret_set": bool(s.get(f"oauth_{p}_client_secret")),
            }
            for p in SHIPPED
        },
        # raw editable values for the form (secrets masked client-side)
        "raw": {
            k: ("" if "key" in k or "secret" in k else v)
            if k.endswith("key") or k.endswith("secret")
            else v
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
                "sync_default_interval_min",
                "history_floor",
                "composio_api_key",
                "embed_model",
                "oauth_slack_client_id",
                "oauth_slack_client_secret",
                "oauth_github_client_id",
                "oauth_github_client_secret",
                "oauth_gmail_client_id",
                "oauth_gmail_client_secret",
            }
        },
    }


@app.put("/api/settings")
def put_settings(body: SettingsIn) -> dict[str, str]:
    with db() as conn:
        for k, v in body.values.items():
            if k not in DEFAULT_SETTINGS and not k.startswith("oauth_"):
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
    return {
        "hydra": "ok",  # stub — real hydra wire comes later
        "schema_version": 1,
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
