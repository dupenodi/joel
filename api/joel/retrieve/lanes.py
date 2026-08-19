"""§10.2 — the retrieval lanes, run concurrently. GRAPH and WHO_KNOWS need
CP6's ontology (`HydraStore.graph_expand`/`who_knows`, §9) to have written
`:Entity`/`:Alias` nodes and ontology edges — they're wired in here but a
caller that doesn't pass `hydra_store` (or asks a question the planner
found no entities in) simply gets empty lists back, same degrade-safe shape
as every other lane's zero-hit case.

Every lane excludes `forgotten=1` — `LiveIndex.search` does this itself;
the FTS/PHRASE lanes (raw SQL against `docs`) do it explicitly here, and
GRAPH/WHO_KNOWS inherit it for free by hydrating through `_hydrate`, which
already filters `forgotten=0`. When an AskContext is provided, every lane
also restricts to `allowed_stamps(ask)` so a public-room question cannot
surface a private-channel or personal doc.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

import numpy as np

from joel.live_index import LiveIndex
from joel.ontology.resolve import norm as _norm_alias
from joel.retrieve.planner import QueryPlan
from joel.store import HydraStore
from joel.visibility import AskContext, allowed_stamps, sql_in

EmbedFn = Callable[[list[str]], np.ndarray]

VECTOR_TOP_K = 20
VEC_ARTIFACTS_TOP_K = 15
GRAPH_TOP_K = 200  # §10.2's own cap
WHO_KNOWS_TOP_K = 50
ONTOLOGY_PREDICATES = (
    "OWNS",
    "DECIDED",
    "COMMITTED_TO",
    "OBJECTED_TO",
    "DEPENDS_ON",
    "BLOCKS",
    "ASSIGNED_TO",
    "REPORTED",
    "ESCALATED",
    "APPROVED",
    "RESOLVED",
    "AFFECTS",
)
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


def hydrate_doc_ids(
    conn: sqlite3.Connection,
    doc_ids: list[str],
    *,
    allowed: frozenset[str] | None = None,
) -> list[RetrievedDoc]:
    """Public wrapper around `_hydrate`, in id order — for callers that
    already know exactly which doc_ids they want (§13.2's live lookup:
    a freshly-fetched doc must get a real shot at this turn's rerank, not
    hope RRF happens to rediscover it among everything else in the corpus)."""
    hydrated = _hydrate(conn, doc_ids, allowed=allowed)
    return _order_by_ids(hydrated, doc_ids)


def _hydrate(
    conn: sqlite3.Connection,
    doc_ids: list[str],
    *,
    allowed: frozenset[str] | None = None,
) -> dict[str, RetrievedDoc]:
    if not doc_ids:
        return {}
    placeholders = ",".join("?" for _ in doc_ids)
    vis_sql, vis_params = ("", ())
    if allowed is not None:
        vis_sql, vis_params = sql_in(allowed, column="visibility")
        vis_sql = f" AND {vis_sql}"
    rows = conn.execute(
        f"""SELECT id, title, body, source_type, container, granularity,
                   artifact_class, validity, url, timestamp
            FROM docs WHERE id IN ({placeholders}) AND forgotten=0{vis_sql}""",
        (*doc_ids, *vis_params),
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


def _vector_mask(
    index: LiveIndex,
    plan: QueryPlan,
    *,
    artifacts_only: bool,
    allowed: frozenset[str] | None = None,
) -> np.ndarray | None:
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
    if allowed is not None:
        filters["visibility"] = tuple(sorted(allowed))
    if not filters:
        return None
    return index.mask(**filters)


def _visible_sql(allowed: frozenset[str] | None) -> tuple[str, tuple[str, ...]]:
    if allowed is None:
        return "", ()
    clause, params = sql_in(allowed)
    return f" AND {clause}", params


def vector_lane(
    conn: sqlite3.Connection,
    index: LiveIndex,
    embed_fn: EmbedFn,
    plan: QueryPlan,
    question: str,
    *,
    allowed: frozenset[str] | None = None,
) -> list[RetrievedDoc]:
    """VECTOR (always): npz dot product, top-20 + once per rewrite."""
    queries = [question, *plan.rewrites]
    vectors = embed_fn(queries)
    mask = _vector_mask(index, plan, artifacts_only=False, allowed=allowed)
    seen_order: list[str] = []
    seen: set[str] = set()
    for vec in vectors:
        for doc_id, _score in index.search(np.asarray(vec), mask=mask, k=VECTOR_TOP_K):
            if doc_id not in seen:
                seen.add(doc_id)
                seen_order.append(doc_id)
    hydrated = _hydrate(conn, seen_order, allowed=allowed)
    return _order_by_ids(hydrated, seen_order)[:VECTOR_TOP_K]


def vector_artifacts_lane(
    conn: sqlite3.Connection,
    index: LiveIndex,
    embed_fn: EmbedFn,
    plan: QueryPlan,
    question: str,
    *,
    allowed: frozenset[str] | None = None,
) -> list[RetrievedDoc]:
    """VEC-ARTIFACTS (always): vector masked to granularity='artifact',
    top-15 — catches distilled resolutions specifically."""
    vec = embed_fn([question])[0]
    mask = _vector_mask(index, plan, artifacts_only=True, allowed=allowed)
    hits = index.search(np.asarray(vec), mask=mask, k=VEC_ARTIFACTS_TOP_K)
    ordered_ids = [doc_id for doc_id, _score in hits]
    hydrated = _hydrate(conn, ordered_ids, allowed=allowed)
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


def fts_lane(
    conn: sqlite3.Connection,
    plan: QueryPlan,
    question: str,
    *,
    allowed: frozenset[str] | None = None,
) -> list[RetrievedDoc]:
    """FTS (bm25 rank, top-15) — catches rare tokens plain vector similarity
    misses. `docs_fts` is contentless, so results join back through rowid;
    `id` on the fts table itself is never populated (see store_sql.py)."""
    match_query = _or_of_quoted_tokens(question)
    if match_query is None:
        return []
    vis_sql, vis_params = _visible_sql(allowed)
    rows = conn.execute(
        f"""SELECT d.id AS id, bm25(docs_fts) AS rank
           FROM docs_fts f JOIN docs d ON d.rowid = f.rowid
           WHERE docs_fts MATCH ? AND d.forgotten = 0{vis_sql}
           ORDER BY rank LIMIT ?""",
        (match_query, *vis_params, FTS_TOP_K),
    ).fetchall()
    ordered_ids = [r["id"] for r in rows]
    hydrated = _hydrate(conn, ordered_ids, allowed=allowed)
    return _order_by_ids(hydrated, ordered_ids)


def phrase_lane(
    conn: sqlite3.Connection,
    plan: QueryPlan,
    question: str,
    *,
    allowed: frozenset[str] | None = None,
) -> list[RetrievedDoc]:
    """PHRASE: FTS5 exact-phrase match per `exact_token` from the plan —
    catches pasted errors and identifiers a vector/bm25 lane would blur
    across near-synonyms. Falls back to the whole question as one phrase
    when the planner found no tokens (e.g. planner failure), matching
    §10.1's "exact_tokens ... else []" contract without ever running zero
    exact-match queries."""
    tokens = plan.exact_tokens or [question]
    ordered_ids: list[str] = []
    seen: set[str] = set()
    vis_sql, vis_params = _visible_sql(allowed)
    for token in tokens:
        rows = conn.execute(
            f"""SELECT d.id AS id, bm25(docs_fts) AS rank
               FROM docs_fts f JOIN docs d ON d.rowid = f.rowid
               WHERE docs_fts MATCH ? AND d.forgotten = 0{vis_sql}
               ORDER BY rank LIMIT ?""",
            (_quote_fts(token), *vis_params, PHRASE_TOP_K),
        ).fetchall()
        for r in rows:
            if r["id"] not in seen:
                seen.add(r["id"])
                ordered_ids.append(r["id"])
    hydrated = _hydrate(conn, ordered_ids, allowed=allowed)
    return _order_by_ids(hydrated, ordered_ids)[:PHRASE_TOP_K]


def graph_lane(
    conn: sqlite3.Connection,
    hydra_store: HydraStore,
    plan: QueryPlan,
    *,
    allowed: frozenset[str] | None = None,
) -> list[RetrievedDoc]:
    """GRAPH: aliases -> entities -> expand ontology+MENTIONS <=2 hops ->
    doc_ids ranked by hop distance then ts (§10.2), via
    `HydraStore.graph_expand`. Empty when the planner found no entities in
    the question — this lane has nothing to seed a traversal from without
    at least one surface form."""
    if not plan.entities:
        return []
    names = [_norm_alias(name) for name in plan.entities if name.strip()]
    if not names:
        return []
    try:
        hits = hydra_store.graph_expand(names, ONTOLOGY_PREDICATES, max_hops=2, result_limit=GRAPH_TOP_K)
    except Exception:
        # §14.5's degraded mode: HydraDB unreachable must drop to the other
        # four lanes with a banner, not a 500 — this lane failing is exactly
        # the case that has to degrade, not propagate.
        return []
    ordered_ids = [doc_id for doc_id, _hop in hits]  # already hop-sorted; ts tiebreak happens in fuse's age decay
    hydrated = _hydrate(conn, ordered_ids, allowed=allowed)
    return _order_by_ids(hydrated, ordered_ids)


def who_knows_lane(
    conn: sqlite3.Connection,
    hydra_store: HydraStore,
    plan: QueryPlan,
    *,
    allowed: frozenset[str] | None = None,
) -> list[RetrievedDoc]:
    """WHO_KNOWS (intent=who, §4.3): the evidence doc for every ontology
    edge touching an entity the question names — via `HydraStore.who_knows`.
    Only runs for `intent == "who"`; every other intent skips it (empty
    list), matching §10.2's own gating."""
    if plan.intent != "who" or not plan.entities:
        return []
    names = [_norm_alias(name) for name in plan.entities if name.strip()]
    if not names:
        return []
    try:
        edges = hydra_store.who_knows(names, ONTOLOGY_PREDICATES)
    except Exception:
        return []  # same degrade-safe reasoning as graph_lane above
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for edge in edges:
        doc_id = edge.get("doc_id")
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            ordered_ids.append(doc_id)
    ordered_ids = ordered_ids[:WHO_KNOWS_TOP_K]
    hydrated = _hydrate(conn, ordered_ids, allowed=allowed)
    return _order_by_ids(hydrated, ordered_ids)


def run_lanes(
    conn: sqlite3.Connection,
    index: LiveIndex,
    embed_fn: EmbedFn,
    plan: QueryPlan,
    question: str,
    *,
    ask: AskContext | None = None,
    hydra_store: HydraStore | None = None,
) -> dict[str, list[RetrievedDoc]]:
    """Run every implemented lane concurrently (§10.2's own requirement —
    lanes must not run serially). Callers must pass a connection opened
    with `check_same_thread=False` (as `app.db()` already does) — every
    lane here only reads, so sharing one connection across the pool's
    threads is safe and avoids the ":memory:"-database trap of each thread
    opening its own connection and seeing an empty, unrelated database.

    `hydra_store=None` (e.g. HydraDB is unreachable, §14's degraded mode)
    skips GRAPH/WHO_KNOWS entirely rather than failing the whole question —
    the other four lanes still answer."""
    allowed = None if ask is None else allowed_stamps(ask)
    with ThreadPoolExecutor(max_workers=6) as pool:
        vector_f = pool.submit(
            vector_lane, conn, index, embed_fn, plan, question, allowed=allowed
        )
        vec_art_f = pool.submit(
            vector_artifacts_lane, conn, index, embed_fn, plan, question, allowed=allowed
        )
        fts_f = pool.submit(fts_lane, conn, plan, question, allowed=allowed)
        phrase_f = pool.submit(phrase_lane, conn, plan, question, allowed=allowed)
        graph_f = (
            pool.submit(graph_lane, conn, hydra_store, plan, allowed=allowed)
            if hydra_store is not None
            else None
        )
        who_f = (
            pool.submit(who_knows_lane, conn, hydra_store, plan, allowed=allowed)
            if hydra_store is not None
            else None
        )

        results = {
            "vector": vector_f.result(),
            "vec_artifacts": vec_art_f.result(),
            "fts": fts_f.result(),
            "phrase": phrase_f.result(),
        }
        if graph_f is not None:
            results["graph"] = graph_f.result()
        if who_f is not None:
            results["who_knows"] = who_f.result()
        return results


__all__ = [
    "RetrievedDoc",
    "vector_lane",
    "vector_artifacts_lane",
    "fts_lane",
    "phrase_lane",
    "graph_lane",
    "who_knows_lane",
    "run_lanes",
    "hydrate_doc_ids",
    "ONTOLOGY_PREDICATES",
]
