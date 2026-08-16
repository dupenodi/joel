"""Checkpoint 1: verify the Phase 1 graph data model against a live node.

Probes §4.1's Doc/Entity/Alias nodes and the DECIDED ontology edge, every
property-filtered MATCH for a Doc, the SET-based supersession flip, a
Doc-Entity-Doc traversal, algo.MSpaths, and every §4.4 assumption -- including
two the plan didn't anticipate (node ids must be integers; WHERE...IN and
multi-type relationship patterns are both rejected) that surfaced while
building `joel/store.py`. Each of those gaps is asserted here as a rejection
plus a working fallback, per PLAN.md's own guidance that a guardrail is only
real once it is encoded as a checkpoint assertion.
"""

from __future__ import annotations

from pathlib import Path
import sys
import uuid

from dotenv import load_dotenv
import neo4j

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from joel.config import Settings  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.store import HydraStore, to_vertex_id  # noqa: E402

DOC_PROPS = {
    "title": "Q3 pricing decision",
    "source_type": "slack",
    "container": "channel_pricing",
    "granularity": "artifact",
    "artifact_class": "decision",
    "validity": "current",
    "resolved": "true",
    "ts": "2026-08-16t00:00:00z",
    "period": "2026q3",
    "url": "https://example.com/doc",
}


def _probe_key(label: str) -> str:
    return f"{label.lower()}_{uuid.uuid4().hex[:12]}"


def check_doc_entities_alias_edge(store: HydraStore) -> dict[str, str]:
    doc_key = _probe_key("doc")
    entity1_key = _probe_key("entity")
    entity2_key = _probe_key("entity")
    alias_key = _probe_key("alias")

    store.create_node("Doc", doc_key, **DOC_PROPS)
    store.create_node("Entity", entity1_key, etype="PERSON", identifier="e1@example.com")
    store.create_node("Entity", entity2_key, etype="PERSON", identifier="e2@example.com")

    # :Alias per §4.1 carries `entity_id` as a plain property, but HydraDB
    # rejects an edge-less node write (see store.py's WRITES OUTSIDE A
    # BATCH). An ALIAS_OF edge to the Entity satisfies that constraint and
    # is more idiomatic besides, so that's the model used here. create_edge's
    # keyword props land on the relationship, not an endpoint, so the
    # Alias's own `name` property is set separately.
    store.create_node("Alias", alias_key, name="alice")
    store.create_edge("Alias", alias_key, "ALIAS_OF", "Entity", entity1_key)
    store.create_edge(
        "Entity",
        entity1_key,
        "DECIDED",
        "Entity",
        entity2_key,
        doc_id=doc_key,
        ctx="raised prices 8% for enterprise tier",
        ts="2026-08-16t00:00:00z",
    )

    doc = store.get_node_strong("Doc", doc_key, ["key", *DOC_PROPS.keys()])
    if doc is None or doc["key"] != doc_key:
        raise AssertionError(f"Doc strong-read failed: {doc!r}")
    for prop, expected in DOC_PROPS.items():
        if doc[prop] != expected:
            raise AssertionError(f"Doc.{prop} = {doc[prop]!r}, expected {expected!r}")

    alias = store.get_node_strong("Alias", alias_key, ["name"])
    if alias is None or alias["name"] != "alice":
        raise AssertionError(f"Alias strong-read failed: {alias!r}")

    edge_rows = store.hydra.bolt(
        "MATCH (a:Entity {id: $a})-[r:DECIDED]->(b:Entity {id: $b}) "
        "RETURN r.doc_id AS doc_id, r.ctx AS ctx, r.ts AS ts",
        a=to_vertex_id(entity1_key),
        b=to_vertex_id(entity2_key),
    )
    if len(edge_rows) != 1 or edge_rows[0]["doc_id"] != doc_key:
        raise AssertionError(f"DECIDED edge read failed: {edge_rows!r}")

    return {
        "doc_key": doc_key,
        "entity1_key": entity1_key,
        "entity2_key": entity2_key,
    }


def check_property_filters(store: HydraStore, doc_key: str) -> None:
    vid = to_vertex_id(doc_key)
    for prop, correct in {"key": doc_key, **DOC_PROPS}.items():
        hits = store.match_property("Doc", prop, correct)
        if vid not in hits:
            raise AssertionError(f"filter {prop}={correct!r} missed the probe doc")

        wrong = f"{correct}__wrong"
        misses = store.match_property("Doc", prop, wrong)
        if vid in misses:
            raise AssertionError(f"filter {prop}={wrong!r} matched the probe doc")


def check_supersession(store: HydraStore, doc_key: str) -> None:
    store.set_property("Doc", doc_key, "validity", "superseded")
    doc = store.get_node_strong("Doc", doc_key, ["validity"])
    if doc is None or doc["validity"] != "superseded":
        raise AssertionError(f"SET validity did not round-trip: {doc!r}")


def check_doc_entity_doc_traversal(store: HydraStore, doc_key: str, entity_key: str) -> None:
    doc2_key = _probe_key("doc")
    store.create_edge("Doc", doc_key, "MENTIONS", "Entity", entity_key)
    store.create_edge("Entity", entity_key, "AUTHORED", "Doc", doc2_key)

    rows = store.hydra.bolt(
        "MATCH (d1:Doc {id: $d1})-[:MENTIONS]->(e:Entity), "
        "(e)-[:AUTHORED]->(d2:Doc) "
        "RETURN d2.key AS key",
        d1=to_vertex_id(doc_key),
    )
    keys = [row["key"] for row in rows]
    if doc2_key not in keys:
        raise AssertionError(f"Doc->Entity->Doc traversal missed {doc2_key}: {keys!r}")


def check_ms_paths(store: HydraStore, entity1_key: str, entity2_key: str) -> None:
    paths = store.ms_paths(
        "Entity", [entity1_key], "Entity", [entity2_key], ["DECIDED"]
    )
    if not paths:
        raise AssertionError("algo.MSpaths returned no path for a known edge")


def check_where_in_rejected_and_fallback(store: HydraStore) -> None:
    a, b = _probe_key("entity"), _probe_key("entity")
    store.create_node("Entity", a, marker="in_probe")
    store.create_node("Entity", b, marker="in_probe")

    try:
        store.hydra.bolt(
            "MATCH (n:Entity) WHERE n.key IN $keys RETURN n.id AS id", keys=[a, b]
        )
    except neo4j.exceptions.Neo4jError:
        pass
    else:
        raise AssertionError(
            "WHERE ... IN unexpectedly succeeded -- store.py's fallback "
            "note is stale, revisit in_or()"
        )

    clause, params = store.in_or("n.key", [a, b])
    rows = store.hydra.bolt(f"MATCH (n:Entity) WHERE {clause} RETURN n.id AS id", **params)
    ids = {row["id"] for row in rows}
    if ids != {to_vertex_id(a), to_vertex_id(b)}:
        raise AssertionError(f"in_or fallback returned {ids!r}, expected both probes")


def check_multi_type_rejected_and_fallback(store: HydraStore) -> None:
    src = _probe_key("entity")
    owns_target = _probe_key("entity")
    decided_target = _probe_key("entity")
    store.create_edge("Entity", src, "OWNS", "Entity", owns_target)
    store.create_edge("Entity", src, "DECIDED", "Entity", decided_target)

    try:
        store.hydra.bolt(
            "MATCH (a:Entity {id: $a})-[r:OWNS|DECIDED]->(b) RETURN b.id AS id",
            a=to_vertex_id(src),
        )
    except neo4j.exceptions.Neo4jError:
        pass
    else:
        raise AssertionError(
            "multi-type relationship pattern unexpectedly succeeded -- "
            "store.py's fallback note is stale, revisit traverse_any_type()"
        )

    results = store.traverse_any_type(
        "Entity", src, ["OWNS", "DECIDED"], to_label="Entity"
    )
    seen = {r["key"] for r in results}
    if seen != {owns_target, decided_target}:
        raise AssertionError(f"traverse_any_type returned {seen!r}, expected both targets")


def check_node_id_must_be_integer(store: HydraStore) -> None:
    try:
        store.hydra.bolt("MERGE (a {id: 'not-an-integer'})-[:X]->(b {id: 999999999})")
    except neo4j.exceptions.Neo4jError:
        pass
    else:
        raise AssertionError(
            "string node id unexpectedly accepted -- store.py's to_vertex_id "
            "hashing may no longer be necessary, revisit"
        )


def check_batch_upsert_idempotent(store: HydraStore) -> None:
    doc_key = _probe_key("doc")
    other_key = _probe_key("doc")
    rel_key = f"{doc_key}->{other_key}"

    for _ in range(2):
        store.upsert_nodes("Doc", [{"key": doc_key, "title": "batch"}])
        store.upsert_nodes("Doc", [{"key": other_key, "title": "batch-other"}])
        store.link_nodes(
            "LINKED_TO",
            "Doc",
            "Doc",
            [{"from_key": doc_key, "to_key": other_key, "rel_key": rel_key, "note": "n"}],
        )

    node_hits = store.match_property("Doc", "key", doc_key)
    if len(node_hits) != 1:
        raise AssertionError(f"batched upsert duplicated a node: {node_hits!r}")

    edge_rows = store.hydra.bolt(
        "MATCH (a:Doc {id: $a})-[:LINKED_TO]->(b:Doc {id: $b}) RETURN b.id AS id",
        a=to_vertex_id(doc_key),
        b=to_vertex_id(other_key),
    )
    if len(edge_rows) != 1:
        raise AssertionError(f"batched link duplicated an edge: {edge_rows!r}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    settings = Settings.from_env()

    with Hydra(settings) as hydra:
        store = HydraStore(hydra)

        print("checking Doc + 2 Entities + Alias + DECIDED edge...", flush=True)
        probe = check_doc_entities_alias_edge(store)
        print("ok", flush=True)

        print("checking property-filtered MATCH hits/misses...", flush=True)
        check_property_filters(store, probe["doc_key"])
        print("ok", flush=True)

        print("checking SET validity supersession round-trip...", flush=True)
        check_supersession(store, probe["doc_key"])
        print("ok", flush=True)

        print("checking Doc->Entity->Doc traversal...", flush=True)
        check_doc_entity_doc_traversal(store, probe["doc_key"], probe["entity1_key"])
        print("ok", flush=True)

        print("checking algo.MSpaths...", flush=True)
        check_ms_paths(store, probe["entity1_key"], probe["entity2_key"])
        print("ok", flush=True)

        print("checking WHERE...IN is rejected and in_or() fallback works...", flush=True)
        check_where_in_rejected_and_fallback(store)
        print("ok", flush=True)

        print(
            "checking multi-type relationship patterns are rejected and "
            "traverse_any_type() fallback works...",
            flush=True,
        )
        check_multi_type_rejected_and_fallback(store)
        print("ok", flush=True)

        print("checking non-integer node ids are rejected...", flush=True)
        check_node_id_must_be_integer(store)
        print("ok", flush=True)

        print("checking batched UNWIND upsert/link idempotency...", flush=True)
        check_batch_upsert_idempotent(store)
        print("ok", flush=True)

    print("Checkpoint 1 passed.")


if __name__ == "__main__":
    main()
