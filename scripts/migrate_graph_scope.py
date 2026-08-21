"""Move the pre-tenancy graph out of the install root into a workspace scope.

Before HydraDB's scoped databases were wired up, every workspace read and
wrote the install's root graph: `Hydra.bolt` hardcoded `database="default"`
while only the HTTP header carried a per-org namespace, and essentially
everything goes over Bolt. So one graph accumulated under the root scope, and
that is where an existing install's Docs, Entities and ontology still live.

This copies that graph into one workspace's scope. It is a copy, not a move —
the root graph is left untouched so a failed run costs nothing and can simply
be re-run. Every write is idempotent (MERGE on a derived id), so re-running
after a partial failure converges rather than duplicating.

Relationship ids are derived from `rel_key`, which is deterministic for every
edge type this codebase writes, so the copied edges land on the same ids they
would have had if they had been ingested into the scope directly:

    MENTIONS         {doc_id}::{entity_id}
    AUTHORED         {entity_id}::{doc_id}
    DISTILLED_FROM   {doc_id}::{burst_id}
    ontology         {doc_id}::{src}::{predicate}::{dst}   (doc_id is on the edge)
    REVERSED         no rel_key — written ad hoc, deduped on (from, type, to)

Usage:
    python scripts/migrate_graph_scope.py --org 1            # dry run
    python scripts/migrate_graph_scope.py --org 1 --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from joel.config import Settings  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.ontology.predicates import ONTOLOGY_PREDICATES  # noqa: E402
from joel.store import ALIAS_LABEL, ENTITY_LABEL, HydraStore, _unwrap  # noqa: E402

DOC_LABEL = "Doc"
# Mirrors store_sql._GRAPH_PROPS: the Doc properties the graph actually holds.
DOC_PROPS = (
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
# Large enough to be "everything" at this corpus's scale, small enough that a
# runaway graph fails loudly instead of silently truncating.
SWEEP_LIMIT = 100_000


def _rows(hydra: Hydra, cypher: str, **params: object) -> list[dict]:
    return [
        {k: _unwrap(v) for k, v in row.items()}
        for row in hydra.bolt(cypher, **params)
    ]


def read_source(hydra: Hydra) -> dict:
    """Everything in one scope, keyed by external string key throughout —
    never by the internal integer id, which the copy re-derives anyway."""
    store = HydraStore(hydra)
    doc_projection = ", ".join(f"d.{p} AS {p}" for p in DOC_PROPS)

    docs = [
        row
        for row in _rows(
            hydra,
            f"MATCH (d:{DOC_LABEL}) RETURN d.key AS key, {doc_projection} LIMIT $limit",
            limit=SWEEP_LIMIT,
        )
        if row.get("key")
    ]
    aliases = [
        row
        for row in _rows(
            hydra,
            f"MATCH (a:{ALIAS_LABEL}) "
            "RETURN a.key AS key, a.name AS name, a.entity_key AS entity_key "
            "LIMIT $limit",
            limit=SWEEP_LIMIT,
        )
        if row.get("key")
    ]
    distilled = [
        (row["source_key"], row["target_key"])
        for row in _rows(
            hydra,
            f"MATCH (a:{DOC_LABEL})-[:DISTILLED_FROM]->(b:{DOC_LABEL}) "
            "RETURN a.key AS source_key, b.key AS target_key LIMIT $limit",
            limit=SWEEP_LIMIT,
        )
        if row.get("source_key") and row.get("target_key")
    ]
    return {
        "docs": docs,
        "entities": store.all_entities(limit=SWEEP_LIMIT),
        "aliases": aliases,
        "mentions": store.all_mentions(limit=SWEEP_LIMIT),
        "authored": store.all_authored(limit=SWEEP_LIMIT),
        "distilled_from": distilled,
        "reversals": store.all_reversals(limit=SWEEP_LIMIT),
        "ontology": store.all_ontology_edges(ONTOLOGY_PREDICATES, limit=SWEEP_LIMIT),
    }


def summarize(graph: dict) -> list[str]:
    ontology_total = sum(len(rows) for rows in graph["ontology"].values())
    return [
        f"{len(graph['docs']):>6}  Doc nodes",
        f"{len(graph['entities']):>6}  Entity nodes",
        f"{len(graph['aliases']):>6}  Alias nodes",
        f"{len(graph['mentions']):>6}  MENTIONS edges",
        f"{len(graph['authored']):>6}  AUTHORED edges",
        f"{len(graph['distilled_from']):>6}  DISTILLED_FROM edges",
        f"{len(graph['reversals']):>6}  REVERSED edges",
        f"{ontology_total:>6}  ontology edges "
        f"({sum(1 for v in graph['ontology'].values() if v)} predicates)",
    ]


def write_target(store: HydraStore, graph: dict) -> None:
    """Nodes first, then edges: `link_nodes` MATCHes both endpoints rather
    than creating them (an UNWIND that both creates and links is rejected as
    an ambiguous vertex upsert), so an edge whose endpoints are not in place
    yet is silently dropped rather than erroring."""
    store.upsert_nodes(DOC_LABEL, graph["docs"])
    store.upsert_nodes(ENTITY_LABEL, graph["entities"])
    store.upsert_nodes(ALIAS_LABEL, graph["aliases"])

    store.link_nodes(
        "MENTIONS",
        DOC_LABEL,
        ENTITY_LABEL,
        [
            {"from_key": doc, "to_key": entity, "rel_key": f"{doc}::{entity}"}
            for doc, entity in graph["mentions"]
        ],
    )
    store.link_nodes(
        "AUTHORED",
        ENTITY_LABEL,
        DOC_LABEL,
        [
            {"from_key": entity, "to_key": doc, "rel_key": f"{entity}::{doc}"}
            for entity, doc in graph["authored"]
        ],
    )
    store.link_nodes(
        "DISTILLED_FROM",
        DOC_LABEL,
        DOC_LABEL,
        [
            {"from_key": src, "to_key": dst, "rel_key": f"{src}::{dst}"}
            for src, dst in graph["distilled_from"]
        ],
    )

    for predicate, rows in graph["ontology"].items():
        payload = []
        seen: set[str] = set()
        for row in rows:
            src, dst = row["source_key"], row["target_key"]
            doc_id = row.get("doc_id") or ""
            rel_key = f"{doc_id}::{src}::{predicate}::{dst}"
            # A batch carrying one relationship id twice is rejected whole
            # ("idempotency key conflict"), losing every edge in it.
            if rel_key in seen:
                continue
            seen.add(rel_key)
            payload.append(
                {
                    "from_key": src,
                    "to_key": dst,
                    "rel_key": rel_key,
                    "doc_id": doc_id,
                    "ctx": row.get("ctx") or "",
                    "ts": row.get("ts") or "",
                    "confidence": row.get("confidence") or "",
                }
            )
        store.link_nodes(predicate, ENTITY_LABEL, ENTITY_LABEL, payload)

    # REVERSED is written ad hoc by reconcile.py, deduped on (from, type, to)
    # with no rel_key of its own, so it is replayed the same way.
    for row in graph["reversals"]:
        store.create_edge(
            DOC_LABEL,
            row["source_key"],
            "REVERSED",
            DOC_LABEL,
            row["target_key"],
            ts=row.get("ts") or "",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--org", type=int, default=1, help="workspace to copy the root graph into"
    )
    parser.add_argument(
        "--apply", action="store_true", help="write; otherwise only report what would move"
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    print(f"source  root namespace {settings.hydra_namespace!r} / db {settings.hydra_database!r}")
    target_settings = settings.for_org(args.org)
    print(
        f"target  org {args.org} namespace {target_settings.hydra_namespace!r} "
        f"/ db {target_settings.hydra_database!r}"
    )

    with Hydra(settings) as source:
        graph = read_source(source)
        print("\nin the root graph:")
        for line in summarize(graph):
            print("  " + line)

        if not graph["docs"] and not graph["entities"]:
            print("\nroot graph is empty — nothing to migrate.")
            return

        if not args.apply:
            print("\ndry run; re-run with --apply to copy.")
            return

        with Hydra(target_settings) as target:
            store = HydraStore(target)
            print("\ncopying…")
            write_target(store, graph)
            after = read_source(target)
            print("\nin the org graph now:")
            for line in summarize(after):
                print("  " + line)


if __name__ == "__main__":
    main()
