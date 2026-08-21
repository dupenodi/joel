"""§9's four-stage pipeline wired together: extract -> resolve -> reconcile
-> Cypher edges. Called once per artifact/singleton-doc target from
`joel/pipeline.py`, mirroring exactly how distillation is wired into ingest
(one call per dirty thread there; one call per extraction target here).

Registry (`data/entities/registry.json`) and the LLM resolve-verdict cache
(`data/entities/resolve_cache.json`) are loaded once per pipeline run and
saved once at the end — not per-document — so a sync touching many threads
resolves against a consistently-growing in-memory registry rather than
re-reading/re-writing the file on every doc.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from joel.llm import LLMCallFn
from joel.ontology.extract import ExtractFailure, ExtractInput, ExtractionResult, extract_ontology
from joel.ontology.reconcile import Claim, apply_decisions, reconcile_claim
from joel.ontology.resolve import EntityRegistry, Mention, load_cache, resolve_mention, save_cache
from joel.store import ALIAS_LABEL, ENTITY_LABEL, HydraStore
from joel.store_sql import refresh_validity
from joel.live_index import LiveIndex

MENTIONS = "MENTIONS"
AUTHORED = "AUTHORED"
_MIN_CONFIDENCE = 0.3


@dataclass
class OntologyReport:
    docs_extracted: int = 0
    docs_skipped_noise: int = 0
    entities_touched: int = 0
    relations_written: int = 0
    docs_superseded: int = 0
    extract_errors: list[str] = field(default_factory=list)
    _flipped_doc_ids: list[str] = field(default_factory=list)


def registry_paths(data_dir: Path) -> tuple[Path, Path, Path]:
    entities_dir = data_dir / "entities"
    return (
        entities_dir / "registry.json",
        entities_dir / "resolve_cache.json",
        data_dir / "graphs" / "conflicts.json",
    )


def _doc_meta(conn: sqlite3.Connection, doc_id: str) -> tuple[str | None, str | None]:
    """(source_type, doc_type) for an already-upserted doc, for the
    authority-ladder/formal-doc rules (§9.3) — `doc_type` comes from
    `extra_json` (Confluence/Drive's runbook|spec|policy|notes inference,
    §6.1) and is `None` for every source that never sets it."""
    import json as _json

    row = conn.execute(
        "SELECT source_type, extra_json FROM docs WHERE id=?", (doc_id,)
    ).fetchone()
    if row is None:
        return None, None
    try:
        extra = _json.loads(row["extra_json"] or "{}")
    except _json.JSONDecodeError:
        extra = {}
    return row["source_type"], extra.get("doc_type")


def _write_entity_and_aliases(hydra_store: HydraStore, registry: EntityRegistry, entity_id: str) -> None:
    rec = registry.entities[entity_id]
    hydra_store.upsert_nodes(
        ENTITY_LABEL,
        [{"key": entity_id, "name": rec.canonical_name, "etype": rec.etype, "identifier": rec.identifier or ""}],
    )
    if rec.aliases:
        hydra_store.upsert_nodes(
            ALIAS_LABEL,
            [{"key": alias, "name": alias, "entity_key": entity_id} for alias in rec.aliases],
        )


def _extract_one(
    conn: sqlite3.Connection,
    hydra_store: HydraStore,
    llm_call: LLMCallFn,
    target: ExtractInput,
    registry: EntityRegistry,
    cache: dict,
    conflicts_path: Path,
    report: OntologyReport,
) -> None:
    try:
        result = extract_ontology(llm_call, target)
    except ExtractFailure as exc:
        report.extract_errors.append(str(exc))
        return
    apply_extraction(
        conn, hydra_store, llm_call, target, result, registry, cache, conflicts_path, report
    )


def apply_extraction(
    conn: sqlite3.Connection,
    hydra_store: HydraStore,
    llm_call: LLMCallFn,
    target: ExtractInput,
    result: ExtractionResult,
    registry: EntityRegistry,
    cache: dict,
    conflicts_path: Path,
    report: OntologyReport,
) -> None:
    """Everything after the extraction call: resolve mentions to registry
    entities, write nodes and edges, reconcile against existing claims.

    Split out from `_extract_one` so a bulk rebuild can run the extraction
    calls concurrently (they are independent, network-bound, and the slow
    part) and then apply the results one at a time. Applying has to stay
    serial: `registry` and `cache` are plain mutable objects, and entity
    resolution is order-dependent — two documents naming the same person
    must see each other's registry writes to resolve to one entity rather
    than two."""
    report.docs_extracted += 1
    if result.artifact_class == "noise" or result.confidence < _MIN_CONFIDENCE:
        report.docs_skipped_noise += 1
        return

    local_to_global: dict[str, str] = {}
    for entity in result.entities:
        context = next(
            (r.context for r in result.relations if entity.key in (r.source, r.target)),
            target.title,
        )
        mention = Mention(
            name=entity.name,
            etype=entity.etype,
            identifier=entity.identifier,
            context=context,
            container=target.container,
        )
        entity_id = resolve_mention(registry, mention, llm_call=llm_call, cache=cache)
        local_to_global[entity.key] = entity_id
        _write_entity_and_aliases(hydra_store, registry, entity_id)
        report.entities_touched += 1

    author_entity_id: str | None = None
    if target.author_raw:
        author_mention = Mention(
            name=target.author_raw,
            etype="PERSON",
            identifier=None,
            context=f"authored {target.title}"[:200],
            container=target.container,
        )
        author_entity_id = resolve_mention(registry, author_mention, llm_call=llm_call, cache=cache)
        _write_entity_and_aliases(hydra_store, registry, author_entity_id)
        report.entities_touched += 1

    mentioned_ids = set(local_to_global.values())
    if author_entity_id:
        mentioned_ids.add(author_entity_id)
    if mentioned_ids:
        hydra_store.link_nodes(
            MENTIONS,
            "Doc",
            ENTITY_LABEL,
            [
                {"from_key": target.doc_id, "to_key": eid, "rel_key": f"{target.doc_id}::{eid}"}
                for eid in mentioned_ids
            ],
        )
    if author_entity_id:
        hydra_store.link_nodes(
            AUTHORED,
            ENTITY_LABEL,
            "Doc",
            [
                {
                    "from_key": author_entity_id,
                    "to_key": target.doc_id,
                    "rel_key": f"{author_entity_id}::{target.doc_id}",
                }
            ],
        )

    by_predicate: dict[str, list[dict]] = {}
    # One doc can state the same fact twice ("PPFAS announced X" … "PPFAS
    # notified unitholders of X"), and two local entity keys can resolve to
    # the same global entity, so distinct extracted relations collapse onto
    # one `rel_key`. HydraDB rejects a batch carrying the same relationship
    # id twice outright ("idempotency key conflict for relationship-import
    # request"), which loses every edge in that batch, not just the
    # duplicate — so dedupe before the write rather than after.
    seen_rel_keys: set[str] = set()
    for relation in result.relations:
        src = local_to_global.get(relation.source)
        dst = local_to_global.get(relation.target)
        if src is None or dst is None:
            continue
        if src == dst:
            continue  # self-edge: two surface forms resolved to one entity
        rel_key = f"{target.doc_id}::{src}::{relation.predicate}::{dst}"
        if rel_key in seen_rel_keys:
            continue
        seen_rel_keys.add(rel_key)
        by_predicate.setdefault(relation.predicate, []).append(
            {
                "from_key": src,
                "to_key": dst,
                "rel_key": rel_key,
                "doc_id": target.doc_id,
                "ctx": relation.context,
                "ts": target.timestamp or "",
                "confidence": result.confidence,
            }
        )
    touched_pairs: set[tuple[str, str]] = set()
    for predicate, rows in by_predicate.items():
        hydra_store.link_nodes(predicate, ENTITY_LABEL, ENTITY_LABEL, rows)
        report.relations_written += len(rows)
        for row in rows:
            touched_pairs.add((row["from_key"], predicate))

    # §9.4 incremental reconciliation: only the (entity, predicate) pairs
    # this doc actually touched, each reconciled against EVERY current
    # claim on that pair (not just this sync's), not a full corpus re-run.
    source_type, doc_type = _doc_meta(conn, target.doc_id)
    candidate = Claim(
        doc_id=target.doc_id,
        source_type=source_type or target.source_type,
        doc_type=doc_type,
        ts=target.timestamp,
        confidence=result.confidence,
    )
    all_flipped: list[str] = []
    for entity_key, predicate in touched_pairs:
        existing_edges = hydra_store.edges_from(ENTITY_LABEL, entity_key, predicate, ENTITY_LABEL)
        existing_claims: list[Claim] = []
        for edge in existing_edges:
            doc_id = edge["doc_id"]
            if not doc_id or doc_id == target.doc_id:
                continue
            row = conn.execute(
                "SELECT validity FROM docs WHERE id=?", (doc_id,)
            ).fetchone()
            if row is None or row["validity"] != "current":
                continue
            e_source_type, e_doc_type = _doc_meta(conn, doc_id)
            existing_claims.append(
                Claim(
                    doc_id=doc_id,
                    source_type=e_source_type or "",
                    doc_type=e_doc_type,
                    ts=edge["ts"],
                    confidence=float(edge["confidence"]) if edge["confidence"] not in (None, "") else 1.0,
                )
            )
        if not existing_claims:
            continue
        decisions = reconcile_claim(
            candidate,
            existing_claims,
            explicit_supersedes=result.supersedes is not None,
            entity_key=entity_key,
            predicate=predicate,
        )
        flipped = apply_decisions(conn, hydra_store, decisions, now=target.timestamp or "", conflicts_path=conflicts_path)
        all_flipped.extend(flipped)

    if all_flipped:
        report.docs_superseded += len(all_flipped)
        # LiveIndex refresh happens once for the whole target list in
        # run_ontology_pipeline (one index.snapshot() per call is cheaper
        # than one per doc) -- stash the ids on the report for that.
        report._flipped_doc_ids.extend(all_flipped)  # type: ignore[attr-defined]


def run_ontology_pipeline(
    conn: sqlite3.Connection,
    index: LiveIndex,
    hydra_store: HydraStore,
    llm_call: LLMCallFn,
    targets: list[ExtractInput],
    *,
    data_dir: Path,
) -> OntologyReport:
    """One call per sync's extraction targets (artifacts from dirty threads
    + singleton non-threaded docs, built by the caller — this module
    doesn't know CanonicalDoc/ThreadArtifact field names any more than
    `store_sql.py` does)."""
    report = OntologyReport()
    if not targets:
        return report

    registry_path, cache_path, conflicts_path = registry_paths(data_dir)
    registry = EntityRegistry.load(registry_path)
    cache = load_cache(cache_path)

    for target in targets:
        _extract_one(conn, hydra_store, llm_call, target, registry, cache, conflicts_path, report)

    registry.save(registry_path)
    save_cache(cache_path, cache)

    if report._flipped_doc_ids:
        refresh_validity(index, report._flipped_doc_ids, "superseded")

    return report


__all__ = ["OntologyReport", "apply_extraction", "run_ontology_pipeline", "registry_paths"]
