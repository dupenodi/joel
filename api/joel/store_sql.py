"""`upsert_docs` — one call, three destinations (§8.2): SQLite (+FTS5),
vectors (`LiveIndex`), and HydraDB's `:Doc` nodes (§4.1). Graph writes
compare against `graph_written.content_hash` rather than "already present" —
an edited or re-distilled doc must update its graph node, not be silently
skipped forever, which is the bug §8.2 calls out by name.

`StoreDoc` is the store layer's own generic notion of one indexable unit —
a raw ingested document, a distilled thread artifact, or a kept burst.
Ingest (`CanonicalDoc`) and distill (`ThreadArtifact`/`Burst`) each get a
small mapper into this shape (see `from_canonical_doc` below; distill's
mapper lands with the CP5↔CP4 wiring pass) rather than this module knowing
their field names.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np

from joel.live_index import META_FIELDS, LiveIndex
from joel.models import Burst, CanonicalDoc, ThreadArtifact, compute_content_hash, period_of
from joel.store import HydraStore

DOC_LABEL = "Doc"
DISTILLED_FROM = "DISTILLED_FROM"

EmbedFn = Callable[[list[str]], np.ndarray]

_GRAPH_PROPS = (
    "title",
    "source_type",
    "container",
    "granularity",
    "artifact_class",
    "validity",
    "resolved",
    "ts",
    "period",
    "url",
    "visibility",
)


@dataclass(frozen=True)
class StoreDoc:
    id: str
    title: str
    body: str
    source_type: str
    container: str | None
    granularity: str  # artifact|burst|document|record|code
    artifact_class: str
    validity: str  # current|superseded
    resolved: str  # true|false|na
    ts: str | None  # ISO timestamp or None
    period: str | None  # "2026Q2" or None
    url: str | None
    content_hash: str
    visibility: str = "org"
    distilled_from: tuple[str, ...] = ()  # kept-burst StoreDoc ids (artifacts only)
    embed_text: str | None = None  # override text to embed; None -> title+"\n"+body[:2000]


@dataclass
class UpsertReport:
    sqlite_upserted: list[str] = field(default_factory=list)
    vectors_upserted: list[str] = field(default_factory=list)
    graph_created: list[str] = field(default_factory=list)
    graph_updated: list[str] = field(default_factory=list)
    graph_skipped: list[str] = field(default_factory=list)
    distilled_from_edges: int = 0


def from_canonical_doc(doc: CanonicalDoc) -> StoreDoc:
    """Ingest's mapper into the store layer's generic shape — CanonicalDoc
    already carries §4.1's fields (defaulted to document/current/na until a
    later phase fills them in), so this is a straight field carry, not a
    re-derivation."""
    return StoreDoc(
        id=doc.doc_id,
        title=doc.title,
        body=doc.body,
        source_type=doc.source_type,
        container=doc.container,
        granularity=doc.granularity,
        artifact_class=doc.artifact_class,
        validity=doc.validity,
        resolved=doc.resolved,
        ts=doc.timestamp.isoformat() if doc.timestamp else None,
        period=period_of(doc.timestamp) if doc.timestamp else None,
        url=doc.url,
        content_hash=doc.content_hash,
        visibility=doc.visibility,
    )


def from_thread_artifact(
    artifact: ThreadArtifact,
    kept_burst_ids: Iterable[str],
    *,
    visibility: str = "org",
) -> StoreDoc:
    """§7.4's artifact row: `title=question[:300]`, `body=normalized_body()`,
    `granularity="artifact"`, `DISTILLED_FROM` -> every kept burst."""
    body = artifact.normalized_body()
    return StoreDoc(
        id=artifact.artifact_id,
        title=artifact.question[:300],
        body=body,
        source_type=artifact.source_type,
        container=artifact.container,
        granularity="artifact",
        artifact_class=artifact.artifact_class,
        validity="current",
        resolved=str(artifact.resolved).lower(),
        ts=artifact.timestamp.isoformat() if artifact.timestamp else None,
        period=period_of(artifact.timestamp) if artifact.timestamp else None,
        url=None,
        content_hash=compute_content_hash(artifact.question, body),
        visibility=visibility,
        distilled_from=tuple(kept_burst_ids),
    )


def from_burst(
    burst: Burst,
    *,
    source_type: str,
    container: str | None,
    thread_question: str,
    visibility: str = "org",
) -> StoreDoc:
    """§7.4's kept-burst row: bare `burst.text` as `body` (display + FTS),
    but the embedding gets the thread-question prefix (§7.4's "burst text
    carries its thread's context") so a tangent whose own vocabulary never
    reached the thread summary still surfaces on a semantic query about the
    thread's topic. Title isn't specified by the plan; using
    "{author}: {question}" gives FTS/graph something legible to show rather
    than a bare timestamp."""
    title = f"{burst.author_raw}: {thread_question}"[:300]
    return StoreDoc(
        id=burst.burst_id,
        title=title,
        body=burst.text,
        source_type=source_type,
        container=container,
        granularity="burst",
        artifact_class="document",
        validity="current",
        resolved="na",
        ts=burst.end_ts.isoformat(),
        period=period_of(burst.end_ts),
        url=None,
        content_hash=compute_content_hash(title, burst.text),
        visibility=visibility,
        embed_text=f"Thread: {thread_question}\n{burst.text}",
    )


def _fts_delete(conn: sqlite3.Connection, rowid: int, title: str, body: str) -> None:
    conn.execute(
        "INSERT INTO docs_fts(docs_fts, rowid, title, body) VALUES('delete', ?, ?, ?)",
        (rowid, title, body),
    )


def _fts_insert(conn: sqlite3.Connection, rowid: int, title: str, body: str) -> None:
    conn.execute(
        "INSERT INTO docs_fts(rowid, title, body) VALUES (?, ?, ?)",
        (rowid, title, body),
    )


def _upsert_sqlite_and_fts(
    conn: sqlite3.Connection,
    docs: list[StoreDoc],
    now: str,
    *,
    org_id: int | None = None,
) -> list[str]:
    """SQLite `docs` row (partial UPDATE on conflict — ingest-only columns
    like external_id/thread_id are never touched here) + FTS5 delete-before-
    insert (contentless tables can't reconstruct old text themselves, so the
    'delete' command needs the OLD title/body passed in explicitly).

    Whether to fire that delete must be keyed off whether `docs_fts` already
    has a row for this id — NOT whether `docs` does. A doc landed in `docs`
    by plain ingest (§6) long before it ever went through this function, so
    `docs` having a row is not proof `docs_fts` does too; issuing a
    contentless-FTS5 'delete' for a rowid that was never inserted corrupts
    the index rather than erroring immediately (surfaces later as
    'database disk image is malformed' on an unrelated query)."""
    upserted: list[str] = []
    for doc in docs:
        existing = conn.execute(
            "SELECT rowid, title, body FROM docs WHERE id=?", (doc.id,)
        ).fetchone()
        had_fts_row = existing is not None and conn.execute(
            "SELECT 1 FROM docs_fts WHERE rowid=?", (existing["rowid"],)
        ).fetchone() is not None
        if org_id is not None:
            conn.execute(
                """INSERT INTO docs(
                     id, source_type, external_id, title, body, content_hash, url,
                     timestamp, container, extra_json, first_seen, last_seen, forgotten,
                     granularity, artifact_class, validity, resolved, period, visibility,
                     org_id)
                   VALUES (?,?,?,?,?,?,?,?,?,'{}',?,?,0,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title, body=excluded.body, content_hash=excluded.content_hash,
                     url=excluded.url, timestamp=excluded.timestamp, container=excluded.container,
                     granularity=excluded.granularity, artifact_class=excluded.artifact_class,
                     validity=excluded.validity, resolved=excluded.resolved, period=excluded.period,
                     visibility=excluded.visibility,
                     last_seen=excluded.last_seen, forgotten=0""",
                (
                    doc.id,
                    doc.source_type,
                    doc.id,
                    doc.title,
                    doc.body,
                    doc.content_hash,
                    doc.url,
                    doc.ts,
                    doc.container,
                    now,
                    now,
                    doc.granularity,
                    doc.artifact_class,
                    doc.validity,
                    doc.resolved,
                    doc.period,
                    doc.visibility,
                    org_id,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO docs(
                     id, source_type, external_id, title, body, content_hash, url,
                     timestamp, container, extra_json, first_seen, last_seen, forgotten,
                     granularity, artifact_class, validity, resolved, period, visibility)
                   VALUES (?,?,?,?,?,?,?,?,?,'{}',?,?,0,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title, body=excluded.body, content_hash=excluded.content_hash,
                     url=excluded.url, timestamp=excluded.timestamp, container=excluded.container,
                     granularity=excluded.granularity, artifact_class=excluded.artifact_class,
                     validity=excluded.validity, resolved=excluded.resolved, period=excluded.period,
                     visibility=excluded.visibility,
                     last_seen=excluded.last_seen, forgotten=0""",
                (
                    doc.id,
                    doc.source_type,
                    doc.id,  # external_id default for a store-native doc (artifact/burst)
                    doc.title,
                    doc.body,
                    doc.content_hash,
                    doc.url,
                    doc.ts,
                    doc.container,
                    now,
                    now,
                    doc.granularity,
                    doc.artifact_class,
                    doc.validity,
                    doc.resolved,
                    doc.period,
                    doc.visibility,
                ),
            )
        rowid = conn.execute("SELECT rowid FROM docs WHERE id=?", (doc.id,)).fetchone()[0]
        if had_fts_row:
            _fts_delete(conn, existing["rowid"], existing["title"], existing["body"])
        _fts_insert(conn, rowid, doc.title, doc.body)
        upserted.append(doc.id)
    return upserted


def _upsert_vectors(index: LiveIndex, docs: list[StoreDoc], embed_fn: EmbedFn) -> list[str]:
    if not docs:
        return []
    texts = [doc.embed_text or f"{doc.title}\n{doc.body[:2000]}" for doc in docs]
    vectors = embed_fn(texts)
    upserts = {
        doc.id: (
            np.asarray(vectors[i]),
            {
                "granularity": doc.granularity,
                "artifact_class": doc.artifact_class,
                "validity": doc.validity,
                "resolved": doc.resolved,
                "period": doc.period,
                "source_type": doc.source_type,
                "visibility": doc.visibility,
            },
        )
        for i, doc in enumerate(docs)
    }
    index.apply(upserts, deleted=[])
    return [doc.id for doc in docs]


def _upsert_graph(
    conn: sqlite3.Connection, hydra_store: HydraStore, docs: list[StoreDoc], report: UpsertReport
) -> None:
    if not docs:
        return
    ids = [doc.id for doc in docs]
    placeholders = ",".join("?" for _ in ids)
    known_hashes = {
        r["id"]: r["content_hash"]
        for r in conn.execute(
            f"SELECT id, content_hash FROM graph_written WHERE id IN ({placeholders})", ids
        )
    }

    to_write: list[StoreDoc] = []
    for doc in docs:
        prior = known_hashes.get(doc.id)
        if prior is None:
            report.graph_created.append(doc.id)
            to_write.append(doc)
        elif prior != doc.content_hash:
            report.graph_updated.append(doc.id)
            to_write.append(doc)
        else:
            report.graph_skipped.append(doc.id)

    if to_write:
        hydra_store.upsert_nodes(
            DOC_LABEL,
            (
                {"key": doc.id, **{p: getattr(doc, p) for p in _GRAPH_PROPS}}
                for doc in to_write
            ),
        )
        for doc in to_write:
            conn.execute(
                """INSERT INTO graph_written(id, content_hash) VALUES (?, ?)
                   ON CONFLICT(id) DO UPDATE SET content_hash=excluded.content_hash""",
                (doc.id, doc.content_hash),
            )

    edge_rows = [
        {"from_key": doc.id, "to_key": burst_id, "rel_key": f"{doc.id}::{burst_id}"}
        for doc in docs
        for burst_id in doc.distilled_from
    ]
    if edge_rows:
        hydra_store.link_nodes(DISTILLED_FROM, DOC_LABEL, DOC_LABEL, edge_rows)
        report.distilled_from_edges += len(edge_rows)


def remove_docs(
    conn: sqlite3.Connection,
    index: LiveIndex,
    hydra_store: HydraStore,
    doc_ids: Iterable[str],
    *,
    keep_row: bool = False,
) -> list[str]:
    """Purge FTS, vectors and the graph node for each doc id. Used today by
    §7.5's dropped-burst cleanup (a burst that stops being kept on
    re-distillation), where `keep_row=False` (the default) also hard-deletes
    the SQLite row since a burst/artifact has no tombstone concept.

    The store reuses this with `keep_row=True` for tombstones: leave a
    `forgotten=1` row behind in `docs` (checked by `_persist_canonical_docs`'s
    `forgotten_ids` so a later re-sync can't resurrect it) rather than
    deleting it outright. Canonical JSONL tombstones are a separate concern
    this function deliberately does not know about. Call this BEFORE blanking
    the docs row's title/body — the FTS 'delete' command needs the OLD
    text that was actually indexed, not whatever the caller is about to
    overwrite it with."""
    doc_ids = list(doc_ids)
    removed: list[str] = []
    for doc_id in doc_ids:
        row = conn.execute("SELECT rowid, title, body FROM docs WHERE id=?", (doc_id,)).fetchone()
        if row is None:
            continue
        had_fts_row = conn.execute("SELECT 1 FROM docs_fts WHERE rowid=?", (row["rowid"],)).fetchone() is not None
        if had_fts_row:
            _fts_delete(conn, row["rowid"], row["title"], row["body"])
        if not keep_row:
            conn.execute("DELETE FROM docs WHERE id=?", (doc_id,))
        conn.execute("DELETE FROM graph_written WHERE id=?", (doc_id,))
        hydra_store.delete_node(DOC_LABEL, doc_id)
        removed.append(doc_id)
    if removed:
        index.apply({}, deleted=removed)
    return removed


def refresh_validity(index: LiveIndex, doc_ids: Iterable[str], validity: str) -> None:
    """Flip `validity` in the hot vector index for docs whose SQLite/graph
    validity already changed elsewhere (§9.3 supersession) — reuses each
    doc's existing vector as-is, no re-embedding, since only metadata
    changed. Doc ids not currently in the index (never vectorized, or
    already forgotten) are skipped rather than erroring."""
    snap = index.snapshot()
    upserts: dict[str, tuple[np.ndarray, dict[str, object]]] = {}
    for doc_id in doc_ids:
        row = snap.row_of.get(doc_id)
        if row is None:
            continue
        meta = {f: snap.meta[f][row] for f in META_FIELDS}
        meta["validity"] = validity
        upserts[doc_id] = (snap.matrix[row], meta)
    if upserts:
        index.apply(upserts, deleted=[])


def upsert_docs(
    conn: sqlite3.Connection,
    index: LiveIndex,
    hydra_store: HydraStore,
    docs: list[StoreDoc],
    *,
    embed_fn: EmbedFn,
    now: str,
    org_id: int | None = None,
) -> UpsertReport:
    """The §8.2 orchestrator. Order matters: SQLite/FTS first (source of
    truth for retrieval text), then vectors, then the graph — a crash
    between steps leaves SQLite ahead of the graph, which the content-hash
    compare in `_upsert_graph` will simply catch and repair on the next
    call rather than needing a separate retry ledger to be correct."""
    report = UpsertReport()
    if not docs:
        return report
    report.sqlite_upserted = _upsert_sqlite_and_fts(conn, docs, now, org_id=org_id)
    report.vectors_upserted = _upsert_vectors(index, docs, embed_fn)
    _upsert_graph(conn, hydra_store, docs, report)
    return report


__all__ = [
    "StoreDoc",
    "UpsertReport",
    "EmbedFn",
    "from_canonical_doc",
    "from_thread_artifact",
    "from_burst",
    "upsert_docs",
    "remove_docs",
    "refresh_validity",
    "DOC_LABEL",
    "DISTILLED_FROM",
]
