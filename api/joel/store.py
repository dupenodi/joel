"""Graph storage conventions for HydraDB's OpenCypher subset (Phase 1).

Everything below is verified against a live local node, not assumed from
docs -- the checked-out `hydradb/cypher-compat.md` describes a different
build in several load-bearing ways (its own AGENTS.md warns that `main`
rebases constantly), so treat this docstring as the source of truth over
that file for this project. Every claim here has a corresponding assertion
in `scripts/check_1_graph_model.py`.

NODE IDENTITY
    The `id` property is not an arbitrary property: it is the vertex's
    storage identity, and the server rejects anything but a non-negative
    integer for it ("node id property must be an integer"). External string
    keys (doc_id, entity_id, ...) never go into `id` directly. `to_vertex_id`
    derives a stable non-negative integer from the external key (top 62 bits
    of a blake2b digest); the original string is kept as the `key` property,
    so property-filtered matches and joins with SQLite/vectors use `key`,
    never the internal `id`.

TENANCY
    A workspace's graph is a HydraDB *scope*, not a convention this layer
    enforces. Bolt names it through the database (`{base}.scope1.{tenant}._`)
    and HTTP through the `X-Graph-Namespace` path (`{root}/{tenant}`), where
    `tenant` is URL-safe unpadded base64; `Settings` derives both from one
    org id so they cannot drift. Nothing below this line is org-aware, and
    nothing needs to be: `to_vertex_id` hashes external keys with no org in
    them, so two workspaces holding the same key hold the same vertex id, and
    it is the scope -- not the id -- that keeps them apart. The corollary is
    that a transport which forgets the scope silently merges every tenant
    into one graph without a single query looking wrong.

TRANSPORT
    The HTTP query endpoint does not bind `$param` at all on this build --
    every attempt fails with "missing OpenCypher query parameter", HTTP body
    notwithstanding. Bolt binds scalars and, for UNWIND only, a parameter
    holding a list of maps. Consequently every write and every query that
    touches document text goes through `Hydra.bolt`; `Hydra.q` (HTTP) is
    reserved for the strong-consistency read-after-write checks in the
    checkpoints, using literal values this codebase controls.

WRITES OUTSIDE A BATCH
    A single ad-hoc CREATE or MERGE has to be a one-hop edge pattern --
    there is no statement that creates an isolated node ("only one-hop edge
    patterns are executable"). Both endpoints can be brand new, both can
    already exist, or one of each; MERGE dedupes by (label, id) for nodes
    and by (from, type, to) for relationships, and re-running the same MERGE
    with different property values updates them in place:
        MERGE (a:Label {id: $a})-[:TYPE {..props..}]->(b:Label {id: $b})
    A brand-new node with no natural edge yet (e.g. the very first ingested
    doc) is attached to a fixed bootstrap anchor instead of being created
    bare -- `create_node` does this via a `:Root {id: 0}` vertex that MERGE
    creates on first use and reuses forever after.

BATCH WRITES (UNWIND)
    UNWIND only accepts a parameter holding a list of maps, and only over
    Bolt (see TRANSPORT). Unlike the ad-hoc form above, UNWIND permits a
    bare, edge-less vertex upsert -- but the MERGE pattern may carry `id`
    only; labels and every other property go through a following SET:
        UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Label, n.p = row.p
    Edges between already-upserted vertices are a separate batch, MATCH
    first (trying to create-and-link brand-new nodes in one UNWIND is
    rejected as an ambiguous vertex upsert):
        UNWIND $rows AS row
          MATCH (s:Label {id: row.src}), (d:Label {id: row.dst})
          MERGE (s)-[r:TYPE {id: row.rel_id}]->(d)
          SET r.p = row.p
    The relationship needs its own `id` for MERGE to dedupe it in batch mode
    (the ad-hoc single-statement form above dedupes on from/type/to without
    one). `link_nodes` derives it from a caller-supplied `rel_key`, which
    should encode whatever makes the edge instance unique -- e.g. include
    doc_id so re-ingesting the same doc is a no-op while two different docs
    asserting the same fact between the same two entities still produce two
    edges (that is provenance, not noise, for the ontology layer in §9).

QUERY LANGUAGE GAPS (§4.4 assumptions, verified against the live node)
    MERGE                    present, as above.
    SET                      present, requires a preceding MATCH.
    DELETE / DETACH DELETE   present, both forms -- no deleted='true'
                              fallback needed. `delete_edge`/`delete_node`
                              below use it directly for §7.5's de-kept
                              bursts and the owner's explicit forget.
    relationship properties  present, inline on CREATE/MERGE and via SET.
    WHERE ... IN $list       absent ("WHERE currently supports boolean
                              combinations of property comparisons"); same
                              for ENDS WITH / CONTAINS / IS NULL. Fallback:
                              `in_or` builds `col = $p0 OR col = $p1 ...`
                              with one scalar bind per value.
    multi-type relationship  `[r:A|B]` is rejected ("relationship pattern
    patterns                 must have exactly one type"). Fallback:
                              `traverse_any_type` issues one query per type
                              and merges client-side.
    null in UNWIND rows        rejected ("only boolean, signed integer, finite
                              float, and string parameters are supported") --
                              a bare scalar Bolt param accepts `None` fine,
                              but a `None` *inside* the list-of-maps UNWIND
                              takes down the whole batch. Fallback: `_null_safe`
                              coerces `None` -> `""` for every batched property
                              in `upsert_nodes`/`link_nodes`.
    UNWIND batch size        capped at 1024 items by admission control
                              ("client_query_batch_items rejected by admission
                              control: actual 1881 exceeds limit 1024"), and
                              the rejection discards the whole batch rather
                              than the overflow. `upsert_nodes`/`link_nodes`
                              chunk at `BATCH_LIMIT` so callers never see it.
    SET on a props-less        rejected ("UNWIND relationship SET cannot update
    UNWIND-batched edge        relationship id") -- `link_nodes` used to paper
                              over an empty property list with `r.id = r.id`,
                              which trips exactly this. Fallback: omit the SET
                              clause entirely when there are no relationship
                              properties (e.g. :DISTILLED_FROM, §4.2); the
                              MERGE pattern already binds `id`.
    algo.MSpaths              present, but `sourceValues`/`targetValues` are
                              matched against a *string* property (`key`
                              here, not the integer `id`) and must be passed
                              as literal list values in the query text --
                              list-typed `$params` are rejected outside
                              UNWIND ("composite parameter is only supported
                              as an UNWIND input"). Safe here because the
                              literal values are hashed keys and our own
                              constant type names, never raw user text.
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable, Sequence

from .hydra import Hydra

ROOT_LABEL = "Root"
ROOT_ID = 0
ENTITY_LABEL = "Entity"
ALIAS_LABEL = "Alias"

_VERTEX_ID_BITS = 62
_VERTEX_ID_MASK = (1 << _VERTEX_ID_BITS) - 1

# HydraDB's admission control rejects an UNWIND batch carrying more than 1024
# items outright -- "client_query_batch_items rejected by admission control:
# actual 1881 exceeds limit 1024" -- and the rejection takes the whole batch,
# so a caller with 1100 rows writes nothing rather than 1024 of them. Ordinary
# incremental syncs stay well under it, which is why this never surfaced until
# a whole-corpus write; chunk here so no caller has to know the number.
BATCH_LIMIT = 1000


def _chunked(rows: list[Any], size: int = BATCH_LIMIT) -> Iterable[list[Any]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def to_vertex_id(key: str) -> int:
    """Derive HydraDB's required non-negative-integer vertex id from an
    external string key. Not collision-checked: at this project's scale
    (thousands to low millions of keys against a 62-bit space) a hash
    collision is not the dominant risk."""
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & _VERTEX_ID_MASK


def _null_safe(value: Any) -> Any:
    """UNWIND's list-of-maps parameter rejects `null` outright ("only
    boolean, signed integer, finite float, and string parameters are
    supported") even though a bare scalar Bolt param happily binds `None` --
    a batch-write-only gap the ad-hoc single-statement helpers above never
    hit. Every optional property this codebase batch-writes is a string
    (§4.1's Doc/Entity properties, ontology edge props), so the empty
    string is an unambiguous "absent" for them; reconsider if a batched
    numeric-or-null property ever shows up."""
    return "" if value is None else value


def _unwrap(value: Any) -> Any:
    """HydraDB's HTTP/Bolt read results wrap scalars as {"type","value"};
    Bolt's driver already unwraps most of these, but stay defensive."""
    if isinstance(value, dict) and "value" in value and "type" in value:
        return value["value"]
    return value


def _inline_props(props: dict[str, Any], *, prefix: str) -> tuple[str, dict[str, Any]]:
    parts: list[str] = []
    params: dict[str, Any] = {}
    for name, value in props.items():
        pname = f"{prefix}{name}"
        parts.append(f"{name}: ${pname}")
        params[pname] = value
    return ", ".join(parts), params


class HydraStore:
    """Node/edge primitives for the conventions above. Callers pass external
    string keys; this class owns the hashed-id <-> key mapping so nothing
    above this layer needs to know HydraDB's integer-id restriction."""

    def __init__(self, hydra: Hydra) -> None:
        self.hydra = hydra

    # ---- ad-hoc, non-batched writes ---------------------------------

    def create_node(self, label: str, key: str, **props: Any) -> int:
        """Single node with no natural edge yet, anchored to the bootstrap
        Root vertex (see WRITES OUTSIDE A BATCH). Returns the vertex id."""
        vid = to_vertex_id(key)
        prop_clause, params = _inline_props({"key": key, **props}, prefix="np_")
        self.hydra.bolt(
            f"MERGE (root:{ROOT_LABEL} {{id: {ROOT_ID}}})-[:HAS]->"
            f"(n:{label} {{id: $vid, {prop_clause}}})",
            vid=vid,
            **params,
        )
        return vid

    def create_edge(
        self,
        from_label: str,
        from_key: str,
        edge_type: str,
        to_label: str,
        to_key: str,
        **rel_props: Any,
    ) -> None:
        """Single edge; both endpoints matched-or-created by id. `key` is
        always carried inline on both endpoints too -- if MERGE has to
        create one because it didn't exist yet, it still gets its identity
        stamped rather than surfacing later as a node with no `key` (MERGE
        matches an existing endpoint on `id` alone, so this is a no-op for
        endpoints that already exist). MERGE dedupes on (from, type, to) and
        updates relationship properties in place on repeat calls -- fine for
        structural edges, but see the module docstring's note on `rel_key`
        before using this for ontology facts that must stay distinct per
        source doc."""
        src = to_vertex_id(from_key)
        dst = to_vertex_id(to_key)
        prop_clause, params = _inline_props(rel_props, prefix="rp_")
        rel = f" {{{prop_clause}}}" if prop_clause else ""
        self.hydra.bolt(
            f"MERGE (a:{from_label} {{id: $src, key: $src_key}})-[:{edge_type}{rel}]->"
            f"(b:{to_label} {{id: $dst, key: $dst_key}})",
            src=src,
            src_key=from_key,
            dst=dst,
            dst_key=to_key,
            **params,
        )

    def set_property(self, label: str, key: str, prop: str, value: Any) -> None:
        vid = to_vertex_id(key)
        self.hydra.bolt(
            f"MATCH (n:{label} {{id: $vid}}) SET n.{prop} = $value",
            vid=vid,
            value=value,
        )

    def get_node(
        self, label: str, key: str, props: Sequence[str]
    ) -> dict[str, Any] | None:
        vid = to_vertex_id(key)
        projection = ", ".join(f"n.{p} AS {p}" for p in props)
        rows = self.hydra.bolt(
            f"MATCH (n:{label} {{id: $vid}}) RETURN {projection}", vid=vid
        )
        if not rows:
            return None
        return {name: _unwrap(rows[0][name]) for name in props}

    def get_node_strong(
        self, label: str, key: str, props: Sequence[str]
    ) -> dict[str, Any] | None:
        """Same as `get_node` but over the HTTP transport with
        `consistency: strong`, for checkpoint read-after-write assertions.
        `key` must be a value this codebase generated (see TRANSPORT)."""
        vid = to_vertex_id(key)
        projection = ", ".join(f"n.{p} AS {p}" for p in props)
        result = self.hydra.q(
            f"MATCH (n:{label} {{id: {vid}}}) RETURN {projection}", strong=True
        )
        rows = result.get("rows", [])
        if not rows:
            return None
        return {name: _unwrap(value) for name, value in zip(props, rows[0])}

    def delete_edge(
        self,
        from_label: str,
        from_key: str,
        edge_type: str,
        to_label: str,
        to_key: str,
    ) -> None:
        """Remove a single edge instance, leaving both endpoints in place.
        For §7.5's re-distillation diff (a burst that stops being kept) and
        anything else that must stop asserting a fact rather than merely
        being superseded."""
        src = to_vertex_id(from_key)
        dst = to_vertex_id(to_key)
        self.hydra.bolt(
            f"MATCH (a:{from_label} {{id: $src}})-[r:{edge_type}]->(b:{to_label} {{id: $dst}}) "
            "DELETE r",
            src=src,
            dst=dst,
        )

    def delete_node(self, label: str, key: str) -> None:
        """DETACH DELETE a node and every edge touching it -- the owner's
        explicit forget (§4.4). No `deleted='true'` fallback is needed on
        this build; DETACH DELETE is supported directly."""
        vid = to_vertex_id(key)
        self.hydra.bolt(f"MATCH (n:{label} {{id: $vid}}) DETACH DELETE n", vid=vid)

    def match_property(self, label: str, prop: str, value: Any) -> list[int]:
        """Property-filtered MATCH, for verifying that filters hit the right
        rows and miss the wrong ones (§4.4 guardrail)."""
        rows = self.hydra.bolt(
            f"MATCH (n:{label} {{{prop}: $value}}) RETURN n.id AS id", value=value
        )
        return [_unwrap(row["id"]) for row in rows]

    # ---- batched writes (UNWIND, Bolt only) -------------------------

    def upsert_nodes(
        self, label: str, rows: Iterable[dict[str, Any]], *, key_field: str = "key"
    ) -> None:
        """rows: dicts with `key_field` (external string id) plus arbitrary
        properties, batched in one UNWIND over Bolt."""
        rows = list(rows)
        if not rows:
            return
        prop_names = sorted({k for row in rows for k in row if k != key_field})
        payload = [
            {
                "vid": to_vertex_id(row[key_field]),
                "key": row[key_field],
                **{p: _null_safe(row.get(p)) for p in prop_names},
            }
            for row in rows
        ]
        set_clause = ", ".join(
            ["n.key = row.key"] + [f"n.{p} = row.{p}" for p in prop_names]
        )
        query = (
            f"UNWIND $rows AS row MERGE (n {{id: row.vid}}) SET n:{label}, {set_clause}"
        )
        for batch in _chunked(payload):
            self.hydra.bolt(query, rows=batch)

    def link_nodes(
        self,
        edge_type: str,
        from_label: str,
        to_label: str,
        rows: Iterable[dict[str, Any]],
    ) -> None:
        """rows: dicts with from_key/to_key/rel_key (rel_key must uniquely
        identify this edge *instance* for idempotent re-ingest, e.g. a hash
        of (from_key, to_key, doc_id)) plus arbitrary relationship
        properties, batched in one UNWIND over Bolt."""
        rows = list(rows)
        if not rows:
            return
        reserved = {"from_key", "to_key", "rel_key"}
        prop_names = sorted({k for row in rows for k in row if k not in reserved})
        payload = [
            {
                "src": to_vertex_id(row["from_key"]),
                "dst": to_vertex_id(row["to_key"]),
                "rel_id": to_vertex_id(row["rel_key"]),
                **{p: _null_safe(row.get(p)) for p in prop_names},
            }
            for row in rows
        ]
        # Props-less edges (e.g. :DISTILLED_FROM, §4.2) have nothing to SET
        # after the MERGE -- `id` is already bound in the MERGE pattern
        # itself, and re-SETting it ("r.id = r.id") is rejected outright
        # ("UNWIND relationship SET cannot update relationship id").
        set_clause = ", ".join(f"r.{p} = row.{p}" for p in prop_names)
        query = (
            f"UNWIND $rows AS row "
            f"MATCH (s:{from_label} {{id: row.src}}), (d:{to_label} {{id: row.dst}}) "
            f"MERGE (s)-[r:{edge_type} {{id: row.rel_id}}]->(d)"
        )
        if set_clause:
            query += f" SET {set_clause}"
        for batch in _chunked(payload):
            self.hydra.bolt(query, rows=batch)

    # ---- §4.4 fallbacks ----------------------------------------------

    def in_or(
        self, binding_property: str, values: Sequence[Any]
    ) -> tuple[str, dict[str, Any]]:
        """WHERE ... IN $list is rejected by HydraDB. Build an OR-chain of
        equality comparisons with one scalar bind per value instead, e.g.
        `in_or("al.name", ["alice", "bob"])` returns
        `("al.name = $v0 OR al.name = $v1", {"v0": "alice", "v1": "bob"})`
        for the caller to splice into their own WHERE clause."""
        params = {f"v{i}": value for i, value in enumerate(values)}
        clause = " OR ".join(
            f"{binding_property} = $v{i}" for i in range(len(values))
        )
        return clause, params

    def traverse_any_type(
        self,
        from_label: str,
        from_key: str,
        edge_types: Sequence[str],
        to_label: str = "",
    ) -> list[dict[str, Any]]:
        """Multi-type relationship patterns ([r:A|B]) are rejected
        ("relationship pattern must have exactly one type"). Issue one query
        per type and merge client-side."""
        vid = to_vertex_id(from_key)
        label_clause = f":{to_label}" if to_label else ""
        results: list[dict[str, Any]] = []
        for edge_type in edge_types:
            rows = self.hydra.bolt(
                f"MATCH (a {{id: $vid}})-[:{edge_type}]->(b{label_clause}) "
                f"RETURN b.id AS id, b.key AS key",
                vid=vid,
            )
            for row in rows:
                results.append(
                    {
                        "id": _unwrap(row["id"]),
                        "key": _unwrap(row["key"]),
                        "edge_type": edge_type,
                    }
                )
        return results

    def count_nodes(self, label: str) -> int:
        """§14.1's index-triple health check: a real, live count of one
        node label -- never a proxy like `graph_written`'s row count, which
        would miss anything that changed the graph out from under it.
        `count(n)`/`count(*)` (lowercase, or with an alias) are rejected by
        this build ("property values support integer, float, boolean, and
        string literals" -- an unhelpful message for what's actually an
        unsupported aggregate spelling); bare uppercase `COUNT(*)` with no
        alias is the form that actually works, verified live."""
        rows = self.hydra.bolt(f"MATCH (n:{label}) RETURN COUNT(*)")
        if not rows:
            return 0
        row = rows[0]
        value = row["COUNT(*)"] if "COUNT(*)" in row.keys() else list(row.values())[0]
        return int(_unwrap(value))

    # ---- §9/§10 ontology + GRAPH/WHO_KNOWS lane support ----------------

    def edges_from(
        self, from_label: str, from_key: str, edge_type: str, to_label: str
    ) -> list[dict[str, Any]]:
        """All outgoing edges of one fixed type from one node, with their
        properties and the target's external key -- used by §9.4's
        incremental reconciliation to load every CURRENT claim on a touched
        (entity, predicate) pair before deciding a winner. One predicate is
        always known up front here, so this never needs the multi-type
        `[r:A|B]` pattern the module docstring says HydraDB rejects."""
        vid = to_vertex_id(from_key)
        rows = self.hydra.bolt(
            f"MATCH (a:{from_label} {{id: $vid}})-[r:{edge_type}]->(b:{to_label}) "
            "RETURN r.doc_id AS doc_id, r.ctx AS ctx, r.ts AS ts, "
            "r.confidence AS confidence, b.key AS target_key",
            vid=vid,
        )
        return [
            {
                "doc_id": _unwrap(row["doc_id"]),
                "ctx": _unwrap(row["ctx"]),
                "ts": _unwrap(row["ts"]) or None,
                "confidence": _unwrap(row["confidence"]),
                "target_key": _unwrap(row["target_key"]),
            }
            for row in rows
        ]

    def edges_into(
        self, from_label: str, to_key: str, edge_type: str, to_label: str
    ) -> list[dict[str, Any]]:
        """Incoming counterpart of `edges_from` — neighbors that point at
        `to_key`. Same property projection; the other endpoint is
        `source_key`."""
        vid = to_vertex_id(to_key)
        rows = self.hydra.bolt(
            f"MATCH (a:{from_label})-[r:{edge_type}]->(b:{to_label} {{id: $vid}}) "
            "RETURN r.doc_id AS doc_id, r.ctx AS ctx, r.ts AS ts, "
            "r.confidence AS confidence, a.key AS source_key",
            vid=vid,
        )
        return [
            {
                "doc_id": _unwrap(row["doc_id"]),
                "ctx": _unwrap(row["ctx"]),
                "ts": _unwrap(row["ts"]) or None,
                "confidence": _unwrap(row["confidence"]),
                "source_key": _unwrap(row["source_key"]),
            }
            for row in rows
        ]

    def docs_mentioning(self, entity_key: str, *, limit: int = 200) -> list[str]:
        """Doc→Entity :MENTIONS, reversed -- every doc that mentions this
        entity, by external doc id (never the internal integer id)."""
        vid = to_vertex_id(entity_key)
        rows = self.hydra.bolt(
            "MATCH (d:Doc)-[:MENTIONS]->(e:Entity {id: $vid}) "
            "RETURN d.key AS key LIMIT $limit",
            vid=vid,
            limit=limit,
        )
        return [_unwrap(row["key"]) for row in rows]

    def who_knows(
        self, alias_names: Sequence[str], edge_types: Sequence[str]
    ) -> list[dict[str, Any]]:
        """§4.3's WHO_KNOWS: alias surface forms -> resolved entities ->
        outgoing ontology edges, with each edge's evidence doc_id/ctx/ts.
        One query per (alias, edge_type) pair, merged client-side -- same
        multi-type-pattern-rejected reasoning as `traverse_any_type`."""
        results: list[dict[str, Any]] = []
        seen_entities: set[str] = set()
        for name in alias_names:
            alias = self.get_node(ALIAS_LABEL, name, ["entity_key"])
            if alias is None or not alias.get("entity_key"):
                continue
            entity_key = alias["entity_key"]
            if entity_key in seen_entities:
                continue
            seen_entities.add(entity_key)
            vid = to_vertex_id(entity_key)
            for edge_type in edge_types:
                rows = self.hydra.bolt(
                    f"MATCH (p:{ENTITY_LABEL} {{id: $vid}})-[r:{edge_type}]->(x:{ENTITY_LABEL}) "
                    "RETURN p.name AS person, x.name AS target, r.doc_id AS doc_id, "
                    "r.ctx AS ctx, r.ts AS ts",
                    vid=vid,
                )
                for row in rows:
                    results.append(
                        {
                            "person": _unwrap(row["person"]),
                            "predicate": edge_type,
                            "target": _unwrap(row["target"]),
                            "doc_id": _unwrap(row["doc_id"]),
                            "ctx": _unwrap(row["ctx"]),
                            "ts": _unwrap(row["ts"]) or None,
                        }
                    )
        return results

    def graph_expand(
        self,
        alias_names: Sequence[str],
        edge_types: Sequence[str],
        *,
        max_hops: int = 2,
        result_limit: int = 200,
    ) -> list[tuple[str, int]]:
        """§10.2's GRAPH lane: aliases -> entities -> ontology+MENTIONS
        expansion, bounded to `max_hops` (§4.4's traversal-bound rule).
        Returns `(doc_id, hop_distance)` pairs, closest hop wins on
        duplicates, capped at `result_limit`."""
        seeds: list[str] = []
        for name in alias_names:
            alias = self.get_node(ALIAS_LABEL, name, ["entity_key"])
            if alias and alias.get("entity_key"):
                seeds.append(alias["entity_key"])
        if not seeds:
            return []

        doc_hop: dict[str, int] = {}
        frontier: set[str] = set(seeds)
        visited: set[str] = set(seeds)
        for hop in range(1, max_hops + 1):
            for entity_key in frontier:
                for doc_key in self.docs_mentioning(entity_key, limit=result_limit):
                    if doc_key not in doc_hop:
                        doc_hop[doc_key] = hop
            if hop == max_hops:
                break
            next_frontier: set[str] = set()
            for entity_key in frontier:
                for edge_type in edge_types:
                    for hit in self.traverse_any_type(
                        ENTITY_LABEL, entity_key, [edge_type], to_label=ENTITY_LABEL
                    ):
                        if hit["key"] not in visited:
                            next_frontier.add(hit["key"])
            visited |= next_frontier
            frontier = next_frontier
            if not frontier:
                break
        return sorted(doc_hop.items(), key=lambda kv: kv[1])[:result_limit]

    # ---- whole-graph reads for the §graph overview -------------------

    def all_entities(self, *, limit: int = 2000) -> list[dict[str, Any]]:
        """Every Entity node with its display properties. The overview view
        needs the whole entity set at once; per-node `get_node` calls would
        be one round trip each. Alias/Root/Doc are deliberately excluded --
        they are not part of the entity layer callers reason about."""
        rows = self.hydra.bolt(
            f"MATCH (n:{ENTITY_LABEL}) "
            "RETURN n.key AS key, n.name AS name, n.etype AS etype, "
            "n.identifier AS identifier LIMIT $limit",
            limit=limit,
        )
        return [
            {
                "key": _unwrap(row["key"]),
                "name": _unwrap(row["name"]) or None,
                "etype": _unwrap(row["etype"]) or None,
                "identifier": _unwrap(row["identifier"]) or None,
            }
            for row in rows
            if _unwrap(row["key"])
        ]

    def all_edges_of_type(
        self, edge_type: str, *, limit: int = 2000
    ) -> list[dict[str, Any]]:
        """Every Entity->Entity edge of one predicate, with provenance. One
        query per predicate (the multi-type `[r:A|B]` pattern is rejected on
        this build -- see the module docstring), which is still 12 round
        trips for the whole ontology rather than thousands of per-node ones."""
        rows = self.hydra.bolt(
            f"MATCH (a:{ENTITY_LABEL})-[r:{edge_type}]->(b:{ENTITY_LABEL}) "
            "RETURN a.key AS source_key, b.key AS target_key, "
            "r.doc_id AS doc_id, r.ctx AS ctx, r.ts AS ts, "
            "r.confidence AS confidence LIMIT $limit",
            limit=limit,
        )
        return [
            {
                "source_key": _unwrap(row["source_key"]),
                "target_key": _unwrap(row["target_key"]),
                "doc_id": _unwrap(row["doc_id"]) or None,
                "ctx": _unwrap(row["ctx"]) or None,
                "ts": _unwrap(row["ts"]) or None,
                "confidence": _unwrap(row["confidence"]),
            }
            for row in rows
            if _unwrap(row["source_key"]) and _unwrap(row["target_key"])
        ]

    def all_ontology_edges(
        self, predicates: Sequence[str], *, limit: int = 2000, workers: int = 8
    ) -> dict[str, list[dict[str, Any]]]:
        """Every Entity->Entity edge for each predicate, fetched in parallel.

        HydraDB rejects the multi-type `[r:A|B]` pattern, so the whole
        ontology needs one query per predicate. Those cost roughly two
        seconds each almost regardless of how many rows come back — the
        expense is per round trip, not per edge — so running the set
        serially made the graph page's load scale with the size of the
        vocabulary rather than the size of the graph: expanding from 12
        predicates to 23 took the sweep from ~26s to ~50s while the data
        barely grew.

        `Hydra.bolt` opens its own session per call and the neo4j driver is
        thread-safe at the driver level, so these fan out safely.
        """
        predicates = list(predicates)
        if not predicates:
            return {}
        out: dict[str, list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=min(workers, len(predicates))) as pool:
            futures = {
                pool.submit(self.all_edges_of_type, p, limit=limit): p
                for p in predicates
            }
            for future in futures:
                predicate = futures[future]
                try:
                    out[predicate] = future.result()
                except Exception:
                    # One predicate failing must not lose the whole
                    # ontology; the graph degrades by that edge type only.
                    out[predicate] = []
        return out

    def all_mentions(self, *, limit: int = 4000) -> list[tuple[str, str]]:
        """Every Doc->Entity :MENTIONS pair as (doc_key, entity_key)."""
        rows = self.hydra.bolt(
            f"MATCH (d:Doc)-[:{'MENTIONS'}]->(e:{ENTITY_LABEL}) "
            "RETURN d.key AS doc_key, e.key AS entity_key LIMIT $limit",
            limit=limit,
        )
        pairs = []
        for row in rows:
            doc_key = _unwrap(row["doc_key"])
            entity_key = _unwrap(row["entity_key"])
            if doc_key and entity_key:
                pairs.append((str(doc_key), str(entity_key)))
        return pairs

    def all_reversals(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """Every Doc->Doc :REVERSED edge in one query. The per-document
        `edges_from` walk this replaces cost one round trip per document on
        screen, for an edge type that is rare corpus-wide."""
        rows = self.hydra.bolt(
            "MATCH (a:Doc)-[r:REVERSED]->(b:Doc) "
            "RETURN a.key AS source_key, b.key AS target_key, "
            "r.doc_id AS doc_id, r.ctx AS ctx, r.ts AS ts, "
            "r.confidence AS confidence LIMIT $limit",
            limit=limit,
        )
        return [
            {
                "source_key": _unwrap(row["source_key"]),
                "target_key": _unwrap(row["target_key"]),
                "doc_id": _unwrap(row["doc_id"]) or None,
                "ctx": _unwrap(row["ctx"]) or None,
                "ts": _unwrap(row["ts"]) or None,
                "confidence": _unwrap(row["confidence"]),
            }
            for row in rows
            if _unwrap(row["source_key"]) and _unwrap(row["target_key"])
        ]

    def all_authored(self, *, limit: int = 4000) -> list[tuple[str, str]]:
        """Every Entity->Doc :AUTHORED pair as (entity_key, doc_key)."""
        rows = self.hydra.bolt(
            f"MATCH (e:{ENTITY_LABEL})-[:{'AUTHORED'}]->(d:Doc) "
            "RETURN e.key AS entity_key, d.key AS doc_key LIMIT $limit",
            limit=limit,
        )
        pairs = []
        for row in rows:
            entity_key = _unwrap(row["entity_key"])
            doc_key = _unwrap(row["doc_key"])
            if entity_key and doc_key:
                pairs.append((str(entity_key), str(doc_key)))
        return pairs

    def ms_paths(
        self,
        source_label: str,
        source_keys: Sequence[str],
        target_label: str,
        target_keys: Sequence[str],
        rel_types: Sequence[str],
        *,
        max_len: int = 3,
        path_count: int = 5,
        result_limit: int = 100,
        direction: str = "both",
    ) -> list[Any]:
        """`sourceValues`/`targetValues`/`relTypes` must be literal lists in
        the query text (list-typed params are rejected outside UNWIND) and
        are matched by the string `key` property, not the integer `id`. Safe
        to interpolate: every value here is either a hashed key this
        codebase produced or one of our own constant relationship-type
        names, never raw document text."""

        def literal_list(values: Sequence[str]) -> str:
            escaped = [v.replace("'", "\\'") for v in values]
            return "[" + ", ".join(f"'{v}'" for v in escaped) + "]"

        rows = self.hydra.bolt(
            "CALL algo.MSpaths({"
            f"sourceLabel: '{source_label}', sourceProperty: 'key', "
            f"sourceValues: {literal_list(source_keys)}, "
            f"targetLabel: '{target_label}', targetProperty: 'key', "
            f"targetValues: {literal_list(target_keys)}, "
            f"relTypes: {literal_list(rel_types)}, "
            f"relDirection: '{direction}', maxLen: $maxLen, "
            "pathCount: $pathCount, resultLimit: $resultLimit}) "
            "YIELD path RETURN path",
            maxLen=max_len,
            pathCount=path_count,
            resultLimit=result_limit,
        )
        return [row["path"] for row in rows]
