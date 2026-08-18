"""§10.2 — the retrieval lanes, run concurrently. GRAPH and WHO_KNOWS are
deliberately not implemented here: both need CP6 (ontology) to exist first,
which it doesn't yet. VECTOR, VEC-ARTIFACTS, FTS and PHRASE need nothing
ontology can't already give them, so they run for real today; `fuse.py`
just receives fewer lists than the full plan calls for until CP6 lands.

Every lane excludes `forgotten=1` — `LiveIndex.search` does this itself;
the FTS/PHRASE lanes (raw SQL against `docs`) do it explicitly here.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

import numpy as np

from joel.live_index import LiveIndex
from joel.retrieve.planner import QueryPlan

EmbedFn = Callable[[list[str]], np.ndarray]

VECTOR_TOP_K = 20
VEC_ARTIFACTS_TOP_K = 15
FTS_TOP_K = 15
PHRASE_TOP_K = 15


@dataclass(frozen=True)
class RetrievedDoc:
    id: str
    title: str
    body: str
    source_type: str
    container: str | None
    granularity: str
    artifact_class: str
    validity: str
    url: str | None
    ts: str | None


def _hydrate(conn: sqlite3.Connection, doc_ids: list[str]) -> dict[str, RetrievedDoc]:
    if not doc_ids:
        return {}
    placeholders = ",".join("?" for _ in doc_ids)
    rows = conn.execute(
        f"""SELECT id, title, body, source_type, container, granularity,
                   artifact_class, validity, url, timestamp
            FROM docs WHERE id IN ({placeholders}) AND forgotten=0""",
        doc_ids,
    ).fetchall()
    return {
        r["id"]: RetrievedDoc(
            id=r["id"],
            title=r["title"] or "",
            body=r["body"] or "",
            source_type=r["source_type"],
            container=r["container"],
            granularity=r["granularity"],
            artifact_class=r["artifact_class"],
            validity=r["validity"],
            url=r["url"],
            ts=r["timestamp"],
        )
        for r in rows
    }


def _order_by_ids(hydrated: dict[str, RetrievedDoc], ordered_ids: list[str]) -> list[RetrievedDoc]:
    out = []
    seen = set()
    for doc_id in ordered_ids:
        if doc_id in hydrated and doc_id not in seen:
            out.append(hydrated[doc_id])
            seen.add(doc_id)
    return out


def _vector_mask(index: LiveIndex, plan: QueryPlan, *, artifacts_only: bool) -> np.ndarray | None:
    """§10.2 modifiers, over `LiveIndex.meta` — re-read on every call, never
    a snapshot taken at startup, so a just-changed validity/period is
    reflected on the very next question."""
    filters: dict[str, object] = {}
    if artifacts_only:
        filters["granularity"] = "artifact"
    if plan.temporal.period and plan.temporal.wants_history:
        filters["period"] = plan.temporal.period
    if plan.needs_current_only and not plan.temporal.wants_history:
        filters["validity"] = "current"
    if not filters:
        return None
    return index.mask(**filters)


def vector_lane(
    conn: sqlite3.Connection,
    index: LiveIndex,
    embed_fn: EmbedFn,
    plan: QueryPlan,
    question: str,
) -> list[RetrievedDoc]:
    """VECTOR (always): npz dot product, top-20 + once per rewrite."""
    queries = [question, *plan.rewrites]
    vectors = embed_fn(queries)
    mask = _vector_mask(index, plan, artifacts_only=False)
    seen_order: list[str] = []
    seen: set[str] = set()
    for vec in vectors:
        for doc_id, _score in index.search(np.asarray(vec), mask=mask, k=VECTOR_TOP_K):
            if doc_id not in seen:
                seen.add(doc_id)
                seen_order.append(doc_id)
    hydrated = _hydrate(conn, seen_order)
    return _order_by_ids(hydrated, seen_order)[:VECTOR_TOP_K]


def vector_artifacts_lane(
    conn: sqlite3.Connection,
    index: LiveIndex,
    embed_fn: EmbedFn,
    plan: QueryPlan,
    question: str,
) -> list[RetrievedDoc]:
    """VEC-ARTIFACTS (always): vector masked to granularity='artifact',
    top-15 — catches distilled resolutions specifically."""
    vec = embed_fn([question])[0]
    mask = _vector_mask(index, plan, artifacts_only=True)
    hits = index.search(np.asarray(vec), mask=mask, k=VEC_ARTIFACTS_TOP_K)
    ordered_ids = [doc_id for doc_id, _score in hits]
    hydrated = _hydrate(conn, ordered_ids)
    return _order_by_ids(hydrated, ordered_ids)


def _quote_fts(text: str) -> str:
    """§18's own gotcha list: quote user text in FTS5, or an unescaped
    `OR`/`NEAR`/`*` in the question crashes (or silently misinterprets) the
    MATCH query. Used by PHRASE, where the whole string genuinely needs to
    match as one consecutive phrase."""
    return '"' + text.replace('"', '""') + '"'


def _or_of_quoted_tokens(text: str) -> str | None:
    """§10.2's FTS lane wants bm25-ranked term overlap ("rare tokens
    (IDF)"), not one giant exact phrase — quoting the *whole* question (like
    PHRASE does) means a natural-language question almost never matches
    anything, since it'd require every word to appear consecutively in that
    exact order in some doc. Quoting each token individually still satisfies
    §18's "quote user text" rule (a bare `OR`/`NEAR`/`*` token becomes a
    quoted literal, not an FTS5 operator) while letting bm25 rank documents
    by how many of the question's words they contain, in any order."""
    tokens = text.split()
    if not tokens:
        return None
    return " OR ".join(_quote_fts(t) for t in tokens)


def fts_lane(conn: sqlite3.Connection, plan: QueryPlan, question: str) -> list[RetrievedDoc]:
    """FTS (bm25 rank, top-15) — catches rare tokens plain vector similarity
    misses. `docs_fts` is contentless, so results join back through rowid;
    `id` on the fts table itself is never populated (see store_sql.py)."""
    match_query = _or_of_quoted_tokens(question)
    if match_query is None:
        return []
    rows = conn.execute(
        """SELECT d.id AS id, bm25(docs_fts) AS rank
           FROM docs_fts f JOIN docs d ON d.rowid = f.rowid
           WHERE docs_fts MATCH ? AND d.forgotten = 0
           ORDER BY rank LIMIT ?""",
        (match_query, FTS_TOP_K),
    ).fetchall()
    ordered_ids = [r["id"] for r in rows]
    hydrated = _hydrate(conn, ordered_ids)
    return _order_by_ids(hydrated, ordered_ids)


def phrase_lane(conn: sqlite3.Connection, plan: QueryPlan, question: str) -> list[RetrievedDoc]:
    """PHRASE: FTS5 exact-phrase match per `exact_token` from the plan —
    catches pasted errors and identifiers a vector/bm25 lane would blur
    across near-synonyms. Falls back to the whole question as one phrase
    when the planner found no tokens (e.g. planner failure), matching
    §10.1's "exact_tokens ... else []" contract without ever running zero
    exact-match queries."""
    tokens = plan.exact_tokens or [question]
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        rows = conn.execute(
            """SELECT d.id AS id, bm25(docs_fts) AS rank
               FROM docs_fts f JOIN docs d ON d.rowid = f.rowid
               WHERE docs_fts MATCH ? AND d.forgotten = 0
               ORDER BY rank LIMIT ?""",
            (_quote_fts(token), PHRASE_TOP_K),
        ).fetchall()
        for r in rows:
            if r["id"] not in seen:
                seen.add(r["id"])
                ordered_ids.append(r["id"])
    hydrated = _hydrate(conn, ordered_ids)
    return _order_by_ids(hydrated, ordered_ids)[:PHRASE_TOP_K]


def run_lanes(
    conn: sqlite3.Connection,
    index: LiveIndex,
    embed_fn: EmbedFn,
    plan: QueryPlan,
    question: str,
) -> dict[str, list[RetrievedDoc]]:
    """Run every implemented lane concurrently (§10.2's own requirement —
    lanes must not run serially). Callers must pass a connection opened
    with `check_same_thread=False` (as `app.db()` already does) — every
    lane here only reads, so sharing one connection across the pool's
    threads is safe and avoids the ":memory:"-database trap of each thread
    opening its own connection and seeing an empty, unrelated database."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        vector_f = pool.submit(vector_lane, conn, index, embed_fn, plan, question)
        vec_art_f = pool.submit(vector_artifacts_lane, conn, index, embed_fn, plan, question)
        fts_f = pool.submit(fts_lane, conn, plan, question)
        phrase_f = pool.submit(phrase_lane, conn, plan, question)

        return {
            "vector": vector_f.result(),
            "vec_artifacts": vec_art_f.result(),
            "fts": fts_f.result(),
            "phrase": phrase_f.result(),
        }


__all__ = [
    "RetrievedDoc",
    "vector_lane",
    "vector_artifacts_lane",
    "fts_lane",
    "phrase_lane",
    "run_lanes",
]
