"""Bounded neighborhood around one entity for the graph page.

Hydra owns topology. SQLite owns titles, validity, urls, and the
visibility filter. Alias and Root nodes never leave this module.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from joel.ontology.resolve import norm
from joel.retrieve.lanes import ONTOLOGY_PREDICATES, hydrate_doc_ids
from joel.store import ALIAS_LABEL, ENTITY_LABEL, HydraStore
from joel.visibility import sql_in

MAX_NODES = 80
MAX_EDGES = 200
MAX_DOCS = 36
MENTIONS = "MENTIONS"
AUTHORED = "AUTHORED"
REVERSED = "REVERSED"

# ---- overview bounds ------------------------------------------------
#
# These are readability limits, not tuning knobs: past roughly this many
# marks a force-directed graph stops being a picture anyone can read and
# becomes a texture, regardless of what the corpus contains. They bound how
# much is drawn, never which corpus is "right" — anything beyond the bound
# is reachable by isolating a node and traversing, so nothing is hidden,
# only deferred.
OVERVIEW_MAX_ENTITIES = 140
OVERVIEW_MAX_DOCS = 60
OVERVIEW_MAX_EDGES = 420
# With fewer claim-carrying entities than this the view is too sparse to
# read as a graph at all, so the most-mentioned entities are admitted to
# give it structure. This matters most on a young workspace where only a
# handful of threads have been distilled.
ENTITY_FLOOR = 24

# §9.1 extracts ontology from every non-threaded doc, which includes source
# files. Extraction over code tends to produce entities that are really
# identifier names ("thread_id", "summary") related by verbs that assert
# nothing about the organization, and on a code-heavy corpus those outnumber
# the real claims.
#
# Whether to trust them is a workspace decision, not a universal one: a team
# whose decisions live in code review, or one indexing runbooks and
# infrastructure-as-code, loses real knowledge to this filter. The caller
# passes `quality` from the `graph_trust_code` setting; this constant only
# names which granularities count as code.
CODE_EVIDENCE_GRANULARITIES = frozenset({"code"})


def _evidence_index(
    conn: sqlite3.Connection,
    org_id: int | None,
    allowed: frozenset[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """doc_id -> {validity, granularity, source_type} for every doc this
    viewer may read. Ontology edges carry a `doc_id` but Hydra holds no copy
    of that doc's validity or visibility, so both tests happen here.

    `allowed` is not optional in spirit: an ontology edge carries the
    sentence it was extracted from in `ctx`, so admitting an edge whose
    evidence the viewer cannot open would republish that document's content
    as a graph label. Callers pass the same stamp set they pass to
    `hydrate_doc_ids`."""
    sql = (
        "SELECT id, validity, granularity, source_type FROM docs WHERE forgotten=0"
    )
    params: tuple[Any, ...] = ()
    if org_id is not None:
        sql += " AND org_id=?"
        params = (org_id,)
    if allowed is not None:
        vis_sql, vis_params = sql_in(allowed, column="visibility")
        sql += f" AND {vis_sql}"
        params = (*params, *vis_params)
    return {
        row["id"]: {
            "validity": row["validity"],
            "granularity": row["granularity"],
            "source_type": row["source_type"],
        }
        for row in conn.execute(sql, params)
    }


def _edge_is_admissible(
    doc_id: str | None,
    evidence: dict[str, dict[str, Any]],
    *,
    quality: bool,
) -> bool:
    """An ontology edge earns its place only if its evidence doc is one this
    org can still see and still believes.

    Superseded evidence is the load-bearing case: §9.4 flips a doc's
    `validity` when a newer claim wins, but nothing deletes the edge the old
    doc wrote. Re-distilling one Slack thread five times therefore left five
    parallel `joel DEPENDS_ON HydraDB` edges, only the last of which is
    current -- drawn on top of each other they read as noise, not as
    provenance."""
    if doc_id is None:
        # A claim with no evidence doc cannot be checked or cited. Older
        # writes left `doc_id` empty; treat them as unverifiable, not as
        # trusted.
        return False
    meta = evidence.get(doc_id)
    if meta is None:
        return False  # not in this org, or forgotten
    if meta["validity"] == "superseded":
        return False
    if quality and meta["granularity"] in CODE_EVIDENCE_GRANULARITIES:
        return False
    return True


def empty_slice(query: str = "", *, hydra: str = "ok") -> dict[str, Any]:
    return {
        "query": query,
        "focus": None,
        "nodes": [],
        "edges": [],
        "who_knows": [],
        "reversals": [],
        "truncated": False,
        "hydra": hydra,
    }


CONTAINS = "CONTAINS"
FEEDS = "FEEDS"
WORLD_MAX_DOCS = 90

# Distilled artifacts are the knowledge-bearing documents; a raw newsletter
# is not. When the document layer has to be capped, rank by how much meaning
# a doc carries before falling back to how connected it is.
_CLASS_RANK = {
    "decision": 6,
    "commitment": 6,
    "incident": 6,
    "objection": 5,
    "qa": 4,
    "status_update": 3,
    "reference": 2,
    "document": 1,
    "noise": 0,
}


def _source_label(source_type: str) -> str:
    return {
        "gmail": "Gmail",
        "github": "GitHub",
        "slack": "Slack",
        "notion": "Notion",
        "googledrive": "Google Drive",
        "confluence": "Confluence",
        "jira": "Jira",
        "fireflies": "Fireflies",
    }.get(source_type, source_type or "unknown")


def _container_label(source_type: str, container: str) -> str:
    """Containers are stored as whatever the provider calls them, which is a
    repo path for GitHub, a channel name for Slack, and an opaque uuid for
    Notion/Drive. Show the readable part and let the inspector carry the
    raw value."""
    if not container:
        return "(uncontained)"
    if source_type == "slack":
        return f"#{container}"
    if source_type == "github":
        return container.split("/")[-1] or container
    if source_type in {"notion", "googledrive"} and len(container) > 24:
        return f"{container[:8]}…"
    return container


def world(
    hydra_store: HydraStore,
    conn: sqlite3.Connection,
    *,
    allowed: frozenset[str] | None = None,
    org_id: int | None = None,
    quality: bool = True,
) -> dict[str, Any]:
    """The whole brain in one graph: where knowledge came from, and what it
    turned into.

    `overview()` shows the entity layer alone, which answers "what is
    related to what" but not "how do you know that" — a graph of nouns with
    no provenance reads as a word cloud, and the connectors that produced
    every one of those nouns are invisible. This adds the two structural
    layers above documents:

        Source (a connector)  ──FEEDS──▶  Container (repo/channel/mailbox)
        Container             ──CONTAINS─▶  Doc
        Doc                   ──MENTIONS─▶  Entity
        Entity                ──<predicate>──▶ Entity

    so a single picture carries the full chain from "Gmail" down to a claim,
    and clicking any node can walk it in either direction. Both structural
    layers are cheap: they come from `docs.source_type`/`docs.container`,
    which every ingested document already carries, and there are ~20 of them
    for a corpus of thousands of documents.
    """
    base = overview(
        hydra_store, conn, allowed=allowed, org_id=org_id, quality=quality
    )
    nodes: list[dict[str, Any]] = list(base["nodes"])
    edges: list[dict[str, Any]] = list(base["edges"])
    shown_docs = {n["id"] for n in nodes if n["kind"] == "doc"}

    # Documents already pulled in by the entity layer are the ones holding
    # claims. Top up with the highest-meaning documents in the corpus so the
    # structural layers are not hanging off a handful of nodes.
    extra_needed = max(0, WORLD_MAX_DOCS - len(shown_docs))
    if extra_needed:
        sql = """SELECT id, title, source_type, container, granularity,
                        artifact_class, validity, url, timestamp
                 FROM docs
                 WHERE forgotten=0 AND granularity != 'burst'"""
        params: tuple[Any, ...] = ()
        if org_id is not None:
            sql += " AND org_id=?"
            params = (org_id,)
        if allowed is not None:
            vis_sql, vis_params = sql_in(allowed, column="visibility")
            sql += f" AND {vis_sql}"
            params = (*params, *vis_params)
        candidates = [
            r for r in conn.execute(sql, params) if r["id"] not in shown_docs
        ]
        candidates.sort(
            key=lambda r: (
                -_CLASS_RANK.get((r["artifact_class"] or "document").lower(), 1),
                -(1 if r["granularity"] == "artifact" else 0),
                r["timestamp"] or "",
            ),
        )
        # Interleave by container before truncating. A pure global ranking
        # fills the whole document layer from the two largest sources and
        # leaves Notion, Drive and Slack drawn as sources with nothing
        # hanging off them — technically honest, visually useless. Round
        # robin gives every container its best documents first.
        by_container: dict[tuple[str, str], list[Any]] = {}
        for r in candidates:
            by_container.setdefault(
                (r["source_type"] or "unknown", r["container"] or ""), []
            ).append(r)
        interleaved: list[Any] = []
        while len(interleaved) < extra_needed and by_container:
            for key in list(by_container):
                bucket = by_container[key]
                interleaved.append(bucket.pop(0))
                if not bucket:
                    del by_container[key]
                if len(interleaved) >= extra_needed:
                    break

        for r in interleaved[:extra_needed]:
            shown_docs.add(r["id"])
            nodes.append(
                {
                    "id": r["id"],
                    "kind": "doc",
                    "label": r["title"] or r["id"],
                    "unnamed": not r["title"],
                    "degree": 0,
                    "etype": None,
                    "validity": r["validity"],
                    "url": r["url"],
                    "source_type": r["source_type"],
                    "artifact_class": r["artifact_class"],
                    "container": r["container"],
                    "timestamp": r["timestamp"],
                    "hop": 1,
                }
            )

    # -- structural layers, counted over the WHOLE corpus ---------------
    # Counts describe everything ingested, not just the documents on
    # screen: a Gmail node saying "880 documents" when 12 are drawn is the
    # honest number, and shrinking it to the visible subset would
    # understate what the system actually holds.
    count_sql = """SELECT source_type, container, COUNT(*) AS n
                   FROM docs WHERE forgotten=0 AND granularity != 'burst'"""
    count_params: tuple[Any, ...] = ()
    if org_id is not None:
        count_sql += " AND org_id=?"
        count_params = (org_id,)
    if allowed is not None:
        vis_sql, vis_params = sql_in(allowed, column="visibility")
        count_sql += f" AND {vis_sql}"
        count_params = (*count_params, *vis_params)
    count_sql += " GROUP BY source_type, container"

    source_totals: dict[str, int] = {}
    container_totals: dict[tuple[str, str], int] = {}
    for row in conn.execute(count_sql, count_params):
        source_type = row["source_type"] or "unknown"
        container = row["container"] or ""
        source_totals[source_type] = source_totals.get(source_type, 0) + row["n"]
        container_totals[(source_type, container)] = (
            container_totals.get((source_type, container), 0) + row["n"]
        )

    doc_by_id = {n["id"]: n for n in nodes if n["kind"] == "doc"}
    for node in doc_by_id.values():
        node.setdefault("container", None)

    # Every container and every source is drawn, including ones with no
    # document on screen. A connector that ingested 9 Notion pages, none of
    # which ranked into the document layer, still has to appear: the
    # question this view answers first is "what are you connected to", and
    # silently omitting a source because its documents lost a ranking
    # contest would answer it wrongly. Such a node shows its real corpus
    # count and simply has no CONTAINS edges yet.
    live_containers = set(container_totals)

    for source_type, container in sorted(live_containers):
        cid = f"container::{source_type}::{container}"
        nodes.append(
            {
                "id": cid,
                "kind": "container",
                "label": _container_label(source_type, container),
                "unnamed": False,
                "degree": container_totals.get((source_type, container), 0),
                "etype": None,
                "validity": None,
                "url": None,
                "source_type": source_type,
                "artifact_class": None,
                "container": container or None,
                "doc_count": container_totals.get((source_type, container), 0),
                "hop": 2,
            }
        )
        edges.append(
            {
                "id": f"source::{source_type}::{FEEDS}::{cid}",
                "source": f"source::{source_type}",
                "target": cid,
                "predicate": FEEDS,
                "kind": "feeds",
                "doc_id": None,
                "ctx": None,
                "ts": None,
            }
        )

    for node in doc_by_id.values():
        cid = f"container::{node.get('source_type') or 'unknown'}::{node.get('container') or ''}"
        edges.append(
            {
                "id": f"{cid}::{CONTAINS}::{node['id']}",
                "source": cid,
                "target": node["id"],
                "predicate": CONTAINS,
                "kind": "contains",
                "doc_id": node["id"],
                "ctx": None,
                "ts": None,
            }
        )

    for source_type in sorted(source_totals):
        nodes.append(
            {
                "id": f"source::{source_type}",
                "kind": "source",
                "label": _source_label(source_type),
                "unnamed": False,
                "degree": source_totals.get(source_type, 0),
                "etype": None,
                "validity": None,
                "url": None,
                "source_type": source_type,
                "artifact_class": None,
                "container": None,
                "doc_count": source_totals.get(source_type, 0),
                "hop": 3,
            }
        )

    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    return {
        **base,
        "nodes": nodes,
        "edges": edges,
        "totals": {
            "docs": sum(source_totals.values()),
            "sources": len(source_totals),
            "containers": len(container_totals),
            "by_source": source_totals,
        },
    }


def overview(
    hydra_store: HydraStore,
    conn: sqlite3.Connection,
    *,
    allowed: frozenset[str] | None = None,
    org_id: int | None = None,
    quality: bool = True,
) -> dict[str, Any]:
    """The whole entity layer at once -- the graph page's default view.

    `around()` answers "what surrounds this one thing?" and needs a focus to
    do it. That made the graph page blank until someone typed a name, which
    is the wrong default for a page whose job is to show that a memory
    exists at all. This builds the unfocused counterpart: every entity, the
    ontology claims still believed between them, and the documents backing
    those claims, bounded and ranked by connectedness rather than by a
    search term.

    Ranking is degree over *admissible* edges, so an entity that is only
    connected by stale or code-derived claims sorts to the bottom and falls
    off the bound, instead of occupying the middle of the picture."""
    evidence = _evidence_index(conn, org_id, allowed)

    entities = {e["key"]: e for e in hydra_store.all_entities()}

    # Every Hydra sweep this view needs, in flight at once. Each is a
    # separate round trip costing seconds regardless of row count, and none
    # depends on another's result, so running them in sequence just added
    # their latencies together.
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_edges = pool.submit(hydra_store.all_ontology_edges, ONTOLOGY_PREDICATES)
        f_mentions = pool.submit(hydra_store.all_mentions)
        f_authored = pool.submit(hydra_store.all_authored)
        f_reversals = pool.submit(hydra_store.all_reversals)
        by_predicate = f_edges.result()
        all_mentions = f_mentions.result()
        all_authored_pairs = f_authored.result()
        all_reversal_hits = f_reversals.result()

    raw_edges: list[dict[str, Any]] = []
    for predicate, hits in by_predicate.items():
        for hit in hits:
            if not _edge_is_admissible(hit.get("doc_id"), evidence, quality=quality):
                continue
            source = str(hit["source_key"])
            target = str(hit["target_key"])
            if source not in entities or target not in entities:
                continue
            if source == target:
                continue
            raw_edges.append(_rel(source, target, predicate, hit, kind="ontology"))

    # Collapse repeat assertions of the same (source, predicate, target).
    # Two docs independently asserting one fact is corroboration, not two
    # facts; the graph draws one edge and keeps the newest evidence on it.
    collapsed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in raw_edges:
        signature = (edge["source"], edge["predicate"], edge["target"])
        current = collapsed.get(signature)
        if current is None:
            edge = {**edge, "corroborations": 1}
            collapsed[signature] = edge
            continue
        current["corroborations"] += 1
        if (edge["ts"] or "") > (current["ts"] or ""):
            current["doc_id"] = edge["doc_id"]
            current["ctx"] = edge["ctx"]
            current["ts"] = edge["ts"]
    ontology_edges = list(collapsed.values())

    degree: dict[str, int] = {}
    for edge in ontology_edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1

    mention_count: dict[str, int] = {}
    for doc_id, entity_key in all_mentions:
        if doc_id in evidence:
            mention_count[entity_key] = mention_count.get(entity_key, 0) + 1

    # Which entities are worth drawing.
    #
    # Extraction produced an entity for every capitalised noun it met,
    # including identifier names lifted out of source files. Once
    # code-derived claims are dropped those entities keep their name but
    # lose every edge, so "has a name" is not evidence that a thing belongs
    # on the page -- participating in a claim someone can still cite is.
    # Entities carrying a live ontology claim are the graph; the rest are
    # admitted only to fill a thin picture, most-mentioned first, so a
    # corpus whose extraction has barely run still shows something real.
    connected = [key for key in entities if degree.get(key, 0) > 0]
    if len(connected) < ENTITY_FLOOR:
        filler = sorted(
            (
                key
                for key, record in entities.items()
                if degree.get(key, 0) == 0
                and record.get("name")
                and mention_count.get(key, 0) > 0
            ),
            key=lambda k: (-mention_count.get(k, 0), (entities[k]["name"] or "").lower()),
        )
        connected.extend(filler[: ENTITY_FLOOR - len(connected)])

    ranked = sorted(
        connected,
        key=lambda k: (
            -degree.get(k, 0),
            -mention_count.get(k, 0),
            (entities[k].get("name") or "").lower(),
        ),
    )
    kept_entities = set(ranked[:OVERVIEW_MAX_ENTITIES])
    ontology_edges = [
        e
        for e in ontology_edges
        if e["source"] in kept_entities and e["target"] in kept_entities
    ]

    mention_pairs = [
        (doc_id, entity_key)
        for doc_id, entity_key in all_mentions
        if entity_key in kept_entities
    ]
    authored_pairs = [
        (entity_key, doc_id)
        for entity_key, doc_id in all_authored_pairs
        if entity_key in kept_entities
    ]

    # Documents earn a place by how much of the entity layer they connect,
    # so the docs on screen are the ones holding the graph together.
    doc_weight: dict[str, int] = {}
    for doc_id, _entity_key in mention_pairs:
        doc_weight[doc_id] = doc_weight.get(doc_id, 0) + 1
    for edge in ontology_edges:
        if edge["doc_id"]:
            doc_weight[edge["doc_id"]] = doc_weight.get(edge["doc_id"], 0) + 2
    for _entity_key, doc_id in authored_pairs:
        doc_weight.setdefault(doc_id, 0)

    candidate_docs = sorted(doc_weight, key=lambda d: -doc_weight[d])
    visible = {
        d.id: d
        for d in hydrate_doc_ids(
            conn, candidate_docs[: OVERVIEW_MAX_DOCS * 4], allowed=allowed, org_id=org_id
        )
        if d.granularity != "burst"
    }
    kept_docs = set(
        sorted(visible, key=lambda d: -doc_weight.get(d, 0))[:OVERVIEW_MAX_DOCS]
    )

    nodes: list[dict[str, Any]] = []
    for key in ranked[:OVERVIEW_MAX_ENTITIES]:
        node = _entity_node(hydra_store, key, hop=0, record=entities[key])
        if node:
            node["degree"] = degree.get(key, 0)
            nodes.append(node)
    for doc_id in kept_docs:
        nodes.append(_doc_node(visible[doc_id], hop=1))

    edges: list[dict[str, Any]] = list(ontology_edges)
    edges.extend(
        {
            "id": f"{doc_id}::{MENTIONS}::{entity_key}",
            "source": doc_id,
            "target": entity_key,
            "predicate": MENTIONS,
            "kind": "mentions",
            "doc_id": doc_id,
            "ctx": None,
            "ts": None,
        }
        for doc_id, entity_key in mention_pairs
        if doc_id in kept_docs
    )
    edges.extend(
        {
            "id": f"{entity_key}::{AUTHORED}::{doc_id}",
            "source": entity_key,
            "target": doc_id,
            "predicate": AUTHORED,
            "kind": "authored",
            "doc_id": doc_id,
            "ctx": None,
            "ts": None,
        }
        for entity_key, doc_id in authored_pairs
        if doc_id in kept_docs
    )

    reversals = [
        _rel(
            str(hit["source_key"]),
            str(hit["target_key"]),
            REVERSED,
            hit,
            kind="reversal",
        )
        for hit in all_reversal_hits
        if str(hit["source_key"]) in kept_docs and str(hit["target_key"]) in kept_docs
    ]
    edges.extend(reversals)

    truncated = len(entities) > OVERVIEW_MAX_ENTITIES or len(visible) > OVERVIEW_MAX_DOCS
    if len(edges) > OVERVIEW_MAX_EDGES:
        truncated = True
        edges = edges[:OVERVIEW_MAX_EDGES]

    return {
        "query": "",
        "focus": None,
        "nodes": nodes,
        "edges": edges,
        "who_knows": [],
        "reversals": reversals,
        "truncated": truncated,
        "hydra": "ok",
    }


def resolve_focus(hydra_store: HydraStore, query: str) -> str | None:
    """Entity key from a typed name or an entity id. Never returns an Alias key."""
    raw = query.strip()
    if not raw:
        return None
    if hydra_store.get_node(ENTITY_LABEL, raw, ["name"]) is not None:
        return raw
    alias = hydra_store.get_node(ALIAS_LABEL, norm(raw), ["entity_key"])
    if alias and alias.get("entity_key"):
        return str(alias["entity_key"])
    return None


def around(
    hydra_store: HydraStore,
    conn: sqlite3.Connection,
    query: str,
    *,
    hops: int = 1,
    allowed: frozenset[str] | None = None,
    org_id: int | None = None,
) -> dict[str, Any]:
    q = query.strip()
    hops = 1 if hops < 1 else 2 if hops > 2 else hops
    if not q:
        return empty_slice()

    focus_key = resolve_focus(hydra_store, q)
    if focus_key is None:
        return empty_slice(q)

    focus = _entity_node(hydra_store, focus_key, hop=0)
    if focus is None:
        return empty_slice(q)

    entity_hop: dict[str, int] = {focus_key: 0}
    rel_rows: list[dict[str, Any]] = []
    frontier = [focus_key]
    truncated = False

    for hop in range(1, hops + 1):
        nxt: list[str] = []
        for ek in frontier:
            for pred in ONTOLOGY_PREDICATES:
                for hit in hydra_store.edges_from(ENTITY_LABEL, ek, pred, ENTITY_LABEL):
                    neighbor = hit.get("target_key")
                    if not neighbor:
                        continue
                    rel_rows.append(
                        _rel(ek, str(neighbor), pred, hit, kind="ontology")
                    )
                    if neighbor not in entity_hop:
                        entity_hop[neighbor] = hop
                        nxt.append(str(neighbor))
                for hit in hydra_store.edges_into(ENTITY_LABEL, ek, pred, ENTITY_LABEL):
                    neighbor = hit.get("source_key")
                    if not neighbor:
                        continue
                    rel_rows.append(
                        _rel(str(neighbor), ek, pred, hit, kind="ontology")
                    )
                    if neighbor not in entity_hop:
                        entity_hop[neighbor] = hop
                        nxt.append(str(neighbor))
        if len(entity_hop) > MAX_NODES:
            truncated = True
            break
        frontier = nxt
        if not frontier:
            break

    mention_pairs: list[tuple[str, str]] = []
    mention_seed = [focus_key] if hops == 1 else list(entity_hop)
    remaining_mentions = MAX_DOCS
    for ek in mention_seed:
        if remaining_mentions <= 0:
            truncated = True
            break
        found = hydra_store.docs_mentioning(ek, limit=remaining_mentions)
        for doc_id in found:
            mention_pairs.append((doc_id, ek))
        remaining_mentions -= len(found)

    authored_ids = [
        str(hit["key"])
        for hit in hydra_store.traverse_any_type(
            ENTITY_LABEL, focus_key, [AUTHORED], to_label="Doc"
        )
        if hit.get("key")
    ]

    # Every ontology edge in this neighborhood cites a document, and that
    # document has to be in the slice for the edge to survive the
    # `allowed_docs` test below. Mentions alone do not guarantee it: an
    # entity can carry a claim sourced from a document that never mentions
    # the entity by the name we resolved. Pulling the cited documents in
    # explicitly is what keeps a focused view from rendering its entities
    # with no edges between them.
    evidence_docs = [row["doc_id"] for row in rel_rows if row.get("doc_id")]
    candidate_docs = list(
        dict.fromkeys([d for d, _ in mention_pairs] + authored_ids + evidence_docs)
    )
    visible = {
        d.id: d
        for d in hydrate_doc_ids(
            conn, candidate_docs, allowed=allowed, org_id=org_id
        )
        if d.granularity != "burst"
    }
    if len(visible) > MAX_DOCS:
        truncated = True
        # Cited documents outrank merely-mentioning ones when the cap bites,
        # so trimming never silently deletes the evidence an edge needs.
        cited = {d for d in evidence_docs if d in visible}
        keep = [*cited, *[k for k in visible if k not in cited]][:MAX_DOCS]
        visible = {k: visible[k] for k in keep}

    reversal_rows: list[dict[str, Any]] = []
    extra_doc_ids: list[str] = []
    for doc_id in list(visible):
        for hit in hydra_store.edges_from("Doc", doc_id, REVERSED, "Doc"):
            target = hit.get("target_key")
            if not target:
                continue
            reversal_rows.append(_rel(doc_id, str(target), REVERSED, hit, kind="reversal"))
            if target not in visible:
                extra_doc_ids.append(str(target))
        for hit in hydra_store.edges_into("Doc", doc_id, REVERSED, "Doc"):
            source = hit.get("source_key")
            if not source:
                continue
            reversal_rows.append(_rel(str(source), doc_id, REVERSED, hit, kind="reversal"))
            if source not in visible:
                extra_doc_ids.append(str(source))

    for extra in hydrate_doc_ids(
        conn, list(dict.fromkeys(extra_doc_ids)), allowed=allowed, org_id=org_id
    ):
        if extra.granularity != "burst":
            visible[extra.id] = extra

    allowed_docs = set(visible)
    reversal_rows = [
        e
        for e in reversal_rows
        if e["source"] in allowed_docs and e["target"] in allowed_docs
    ]

    mention_edges = [
        {
            "id": f"{doc_id}::{MENTIONS}::{ek}",
            "source": doc_id,
            "target": ek,
            "predicate": MENTIONS,
            "kind": "mentions",
            "doc_id": doc_id,
            "ctx": None,
            "ts": None,
        }
        for doc_id, ek in mention_pairs
        if doc_id in allowed_docs
    ]
    authored_edges = [
        {
            "id": f"{focus_key}::{AUTHORED}::{doc_id}",
            "source": focus_key,
            "target": doc_id,
            "predicate": AUTHORED,
            "kind": "authored",
            "doc_id": doc_id,
            "ctx": None,
            "ts": None,
        }
        for doc_id in authored_ids
        if doc_id in allowed_docs
    ]

    # Same currency test the overview applies (see `_edge_is_admissible`):
    # a claim whose evidence has been superseded is history, not the
    # current shape of the graph, and drawing it alongside the claim that
    # replaced it is what made repeat-distilled threads look duplicated.
    evidence_index = _evidence_index(conn, org_id, allowed)
    ontology_edges = []
    seen_rel: set[str] = set()
    for row in rel_rows:
        eid = row["id"]
        if eid in seen_rel:
            continue
        seen_rel.add(eid)
        if not _edge_is_admissible(row.get("doc_id"), evidence_index, quality=False):
            continue
        if row["doc_id"] not in allowed_docs:
            continue
        ontology_edges.append(row)

    nodes: list[dict[str, Any]] = []
    for key, hop in entity_hop.items():
        node = focus if key == focus_key else _entity_node(hydra_store, key, hop=hop)
        if node:
            nodes.append(node)

    doc_hop = hops + 1
    for doc in visible.values():
        nodes.append(_doc_node(doc, hop=doc_hop))

    if len(nodes) > MAX_NODES:
        truncated = True
        nodes = nodes[:MAX_NODES]
        keep_ids = {n["id"] for n in nodes}
    else:
        keep_ids = {n["id"] for n in nodes}

    edges = []
    for group in (ontology_edges, mention_edges, authored_edges, reversal_rows):
        for e in group:
            if e["source"] in keep_ids and e["target"] in keep_ids:
                edges.append(e)
    if len(edges) > MAX_EDGES:
        truncated = True
        edges = edges[:MAX_EDGES]

    who_knows = [
        e
        for e in ontology_edges
        if e["predicate"] in ONTOLOGY_PREDICATES
        and (e["source"] == focus_key or e["target"] == focus_key)
        and e["source"] in keep_ids
        and e["target"] in keep_ids
    ]

    return {
        "query": q,
        "focus": focus,
        "nodes": nodes,
        "edges": edges,
        "who_knows": who_knows,
        "reversals": [
            e for e in reversal_rows if e["source"] in keep_ids and e["target"] in keep_ids
        ],
        "truncated": truncated,
        "hydra": "ok",
    }


def _rel(
    source: str,
    target: str,
    predicate: str,
    hit: dict[str, Any],
    *,
    kind: str,
) -> dict[str, Any]:
    doc_id = hit.get("doc_id") or None
    if doc_id == "":
        doc_id = None
    return {
        "id": f"{source}::{predicate}::{target}::{doc_id or ''}",
        "source": source,
        "target": target,
        "predicate": predicate,
        "kind": kind,
        "doc_id": doc_id,
        "ctx": hit.get("ctx") or None,
        "ts": hit.get("ts") or None,
    }


def _entity_node(
    hydra_store: HydraStore,
    key: str,
    *,
    hop: int,
    record: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """`record` lets the overview reuse one bulk entity read instead of
    paying a round trip per node."""
    props = record if record is not None else hydra_store.get_node(
        ENTITY_LABEL, key, ["name", "etype"]
    )
    if props is None:
        return None
    # Some entities carry no name: `_write_entity_and_aliases` copies
    # `registry.canonical_name`, and a registry record that lost its name
    # (or predates the field) writes an empty string, which `_null_safe`
    # keeps as "". Falling through to the raw key renders "entity_59a916e2"
    # as a node label, so mark it as unnamed and let the caller decide.
    name = (props.get("name") or "").strip()
    return {
        "id": key,
        "kind": "entity",
        "label": name or "Unnamed entity",
        "unnamed": not name,
        "degree": 0,
        "etype": props.get("etype") or None,
        "validity": None,
        "url": None,
        "source_type": None,
        "artifact_class": None,
        "hop": hop,
    }


def _doc_node(doc: Any, *, hop: int) -> dict[str, Any]:
    return {
        "id": doc.id,
        "kind": "doc",
        "label": doc.title or doc.id,
        "unnamed": not doc.title,
        "degree": 0,
        "etype": None,
        "validity": doc.validity,
        "url": doc.url,
        "source_type": doc.source_type,
        "artifact_class": doc.artifact_class,
        # Carried so `world()` can hang this doc off its container without a
        # second lookup. `RetrievedDoc` spells the timestamp `ts`.
        "container": getattr(doc, "container", None),
        "timestamp": getattr(doc, "ts", None),
        "hop": hop,
    }
