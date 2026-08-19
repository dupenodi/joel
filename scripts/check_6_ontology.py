"""Checkpoint 6: ontology + entity resolution (§9) — extraction, the 3-stage
resolution funnel, conflict/supersession reconciliation, and the GRAPH/
WHO_KNOWS retrieval lanes they unblock.

Runs against a real, disposable SQLite database (through the actual
migrations in `app.py`) and the real local HydraDB node used by every prior
checkpoint — entity/alias nodes and ontology edges are graph state, a mock
can't tell you whether HydraDB's real Cypher subset accepts them. The LLM is
a fake, stage-dispatching `LLMCallFn` for every deterministic assertion
(no network, no cost) except `check_real_llm_smoke`, which is opt-in (only
runs with `LLM_API_KEY` set) and exercises one real extraction call.

Every node/edge this script writes is scoped under a `RUN_ID`-prefixed key
so re-running it never collides with a prior run or the real corpus, and
everything is deleted at the end regardless of pass/fail.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402

import joel.app as app  # noqa: E402
from joel.config import Settings  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.live_index import LiveIndex  # noqa: E402
from joel.models import CanonicalDoc, compute_content_hash  # noqa: E402
from joel.ontology.extract import ExtractFailure, ExtractInput, extract_ontology  # noqa: E402
from joel.ontology.pipeline import registry_paths, run_ontology_pipeline  # noqa: E402
from joel.ontology.reconcile import Claim, apply_decisions, reconcile_claim  # noqa: E402
from joel.ontology.resolve import (  # noqa: E402
    AUTO_MERGE,
    AUTO_REJECT,
    EntityRegistry,
    Mention,
    pair_score,
    resolve_mention,
)
from joel.retrieve.lanes import graph_lane, who_knows_lane  # noqa: E402
from joel.retrieve.planner import QueryPlan  # noqa: E402
from joel.store import HydraStore, to_vertex_id  # noqa: E402
from joel.store_sql import from_canonical_doc, upsert_docs  # noqa: E402
from joel.visibility import AskContext, Visibility  # noqa: E402

RUN_ID = uuid.uuid4().hex[:8]
_FAKE_EMBED_DIM = 64
_created_doc_ids: list[str] = []
_created_entity_keys: list[str] = []
_created_alias_keys: list[str] = []


def _fake_embed(texts: list[str]):
    import numpy as np

    matrix = np.zeros((len(texts), _FAKE_EMBED_DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in text.lower().split():
            idx = hash(word) % _FAKE_EMBED_DIM
            matrix[i, idx] += 1.0
    return matrix


def _doc(i: int, title: str, body: str, *, source_type: str = "confluence", ts: str | None = None, visibility: str = "org") -> CanonicalDoc:
    from datetime import datetime, timezone

    doc_id = f"chk6_{RUN_ID}_{i}"
    _created_doc_ids.append(doc_id)
    return CanonicalDoc(
        doc_id=doc_id,
        source_type=source_type,
        external_id=f"ext_{i}",
        title=title,
        body=body,
        container=f"C_CHECK6_{RUN_ID}",
        content_hash=compute_content_hash(title, body),
        timestamp=datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc),
        visibility=visibility,
    )


def _store(conn: sqlite3.Connection, index: LiveIndex, hydra_store: HydraStore, doc: CanonicalDoc) -> None:
    upsert_docs(conn, index, hydra_store, [from_canonical_doc(doc)], embed_fn=_fake_embed, now="t0")


def _stage_llm(*, extract_responses: list[dict] | None = None, resolve_responses: list[dict] | None = None):
    """Fake LLMCallFn: `extract` stage pops from `extract_responses` in
    order (one call per `extract_ontology` invocation); `resolve` stage
    pops from `resolve_responses` in order. Records every call so tests can
    assert the resolve cache actually prevents a repeat judgment."""
    extract_queue = list(extract_responses or [])
    resolve_queue = list(resolve_responses or [])
    calls: list[str] = []

    def _call(stage: str, system_prompt: str, user_prompt: str) -> str:
        calls.append(stage)
        if stage == "extract":
            if not extract_queue:
                raise AssertionError("extract stage called with no fake response queued")
            return json.dumps(extract_queue.pop(0))
        if stage == "resolve":
            if not resolve_queue:
                raise AssertionError("resolve stage called with no fake response queued")
            return json.dumps(resolve_queue.pop(0))
        raise AssertionError(f"unexpected LLM stage {stage!r}")

    _call.calls = calls  # type: ignore[attr-defined]
    return _call


# ---- 6.1 Extraction -------------------------------------------------------


def check_extraction_grounding(conn: sqlite3.Connection) -> None:
    llm = _stage_llm(
        extract_responses=[
            {
                "entities": [
                    {"key": "e1", "name": "Ada", "type": "PERSON", "identifier": "ada@acme.com"},
                    {"key": "e2", "name": "Runbook Rewrite", "type": "PROJECT", "identifier": None},
                    # Invalid type -- must be dropped, not coerced.
                    {"key": "e3", "name": "Ship Friday", "type": "DECISION", "identifier": None},
                ],
                "relations": [
                    {"source": "e1", "target": "e2", "predicate": "OWNS", "context": "Ada owns the runbook rewrite.", "temporal_details": None},
                    # References a dropped entity -- must be dropped too (grounding).
                    {"source": "e1", "target": "e3", "predicate": "DECIDED", "context": "n/a", "temporal_details": None},
                    # MENTIONS is never a valid extracted predicate.
                    {"source": "e1", "target": "e2", "predicate": "MENTIONS", "context": "n/a", "temporal_details": None},
                ],
                "artifact_class": "reference",
                "supersedes": None,
                "confidence": 0.9,
            }
        ]
    )
    result = extract_ontology(
        llm,
        ExtractInput(
            doc_id="d1", source_type="confluence", container="C", timestamp=None,
            author_raw="Ada", title="Runbook ownership", body="Ada owns the runbook rewrite project.",
        ),
    )
    assert {e.key for e in result.entities} == {"e1", "e2"}, "invalid entity type must be dropped"
    assert len(result.relations) == 1 and result.relations[0].predicate == "OWNS", (
        "relations referencing a dropped entity, or an invalid predicate, must be dropped"
    )
    print("ok  6.1a: extraction drops ungrounded entities/relations and invalid predicates/types")


def check_extraction_noise_gate(conn: sqlite3.Connection) -> None:
    llm = _stage_llm(extract_responses=[{"entities": [], "relations": [], "artifact_class": "noise", "confidence": 0.1}])
    result = extract_ontology(
        llm, ExtractInput(doc_id="d2", source_type="slack", container="C", timestamp=None, author_raw=None, title="chit chat", body="lol nice"),
    )
    assert result.artifact_class == "noise" and result.confidence < 0.3
    print("ok  6.1b: a noise/low-confidence extraction is still returned (caller decides to skip it)")


# ---- 6.2 Resolution --------------------------------------------------------


def check_pair_score_and_blocking() -> None:
    high = pair_score("Ada Lovelace", "ada@acme.com", ["eng"], "Ada Lovelace", "ada@acme.com", ["eng"])
    assert high >= AUTO_MERGE, f"identical name+identifier+container must auto-merge, got {high}"
    low = pair_score("Ada Lovelace", "ada@acme.com", ["eng"], "Ben Franklin", "ben@acme.com", ["sales"])
    assert low < AUTO_REJECT, f"unrelated people must score below the auto-reject floor, got {low}"
    print("ok  6.2a: pair_score auto-merges identical identities and auto-rejects unrelated ones")


def check_matching_identifier_auto_merges() -> None:
    registry = EntityRegistry()
    cache: dict = {}
    first = resolve_mention(
        registry, Mention(name="Ada Lovelace", etype="PERSON", identifier="ada@acme.com", context="c1", container="eng"),
        llm_call=None, cache=cache,
    )
    second = resolve_mention(
        registry, Mention(name="A. Lovelace", etype="PERSON", identifier="ada@acme.com", context="c2", container="eng"),
        llm_call=None, cache=cache,
    )
    assert first == second, "matching identifiers must resolve to the same entity even with no LLM call"
    rec = registry.entities[first]
    assert len(rec.aliases) == 2, f"expected 2 aliases, got {rec.aliases}"
    print("ok  6.2b: a person referenced two ways with a matching identifier resolves to one Entity with 2 aliases")


def check_conflicting_identifiers_stay_separate() -> None:
    registry = EntityRegistry()
    cache: dict = {}
    llm = _stage_llm(resolve_responses=[{"same": False, "confidence": 0.9, "reason": "conflicting identifiers"}])
    first = resolve_mention(
        registry, Mention(name="Sam Rivera", etype="PERSON", identifier="sam@acme.com", context="c1", container="eng"),
        llm_call=llm, cache=cache,
    )
    second = resolve_mention(
        registry, Mention(name="Sam Rivera", etype="PERSON", identifier="sam@other.com", context="c2", container="sales"),
        llm_call=llm, cache=cache,
    )
    assert first != second, "two different people sharing a name with conflicting identifiers must stay separate"
    print("ok  6.2c: two different people sharing a name with conflicting identifiers stay separate")


def check_llm_verdict_cached_by_sorted_pair() -> None:
    registry = EntityRegistry()
    cache: dict = {}
    # "Bob Chen" vs "Robert Chen" (no identifiers) scores ~0.77 -- inside
    # the ambiguous [AUTO_REJECT, AUTO_MERGE) band, so this genuinely
    # exercises the LLM tie-break rather than resolving on fuzzy score alone.
    llm = _stage_llm(resolve_responses=[{"same": True, "confidence": 0.8, "reason": "same nickname, same team"}])
    first = resolve_mention(
        registry, Mention(name="Bob Chen", etype="PERSON", identifier=None, context="c1", container="eng"),
        llm_call=llm, cache=cache,
    )
    second = resolve_mention(
        registry, Mention(name="Robert Chen", etype="PERSON", identifier=None, context="c2", container="eng"),
        llm_call=llm, cache=cache,
    )
    assert llm.calls.count("resolve") == 1, f"same pair must be judged once, got {llm.calls}"
    print("ok  6.2d: an LLM tie-break verdict is cached by sorted pair — never judged twice")


def check_never_merges_across_type() -> None:
    registry = EntityRegistry()
    cache: dict = {}
    person = resolve_mention(
        registry, Mention(name="Nova", etype="PERSON", identifier=None, context="c1", container="eng"),
        llm_call=None, cache=cache,
    )
    team = resolve_mention(
        registry, Mention(name="Nova", etype="TEAM", identifier=None, context="c2", container="eng"),
        llm_call=None, cache=cache,
    )
    assert person != team, "a PERSON and a TEAM must never merge even with an identical name"
    print("ok  6.2e: never merges a PERSON with a TEAM sharing the same name")


# ---- 6.3 Graph nodes/edges + WHO_KNOWS/GRAPH lanes -------------------------


def check_graph_write_and_lanes(conn: sqlite3.Connection, index: LiveIndex, hydra_store: HydraStore) -> None:
    author_doc = _doc(10, "Ada's decision", "Ada decided to rewrite the runbook.", source_type="confluence")
    _store(conn, index, hydra_store, author_doc)

    llm = _stage_llm(
        extract_responses=[
            {
                "entities": [
                    {"key": "e1", "name": "Ada", "type": "PERSON", "identifier": "ada@acme.com"},
                    {"key": "e2", "name": "Runbook Rewrite", "type": "PROJECT", "identifier": None},
                ],
                "relations": [
                    {"source": "e1", "target": "e2", "predicate": "OWNS", "context": "Ada owns the runbook rewrite.", "temporal_details": None},
                ],
                "artifact_class": "decision",
                "supersedes": None,
                "confidence": 0.95,
            }
        ]
    )
    target = ExtractInput(
        doc_id=author_doc.doc_id, source_type="confluence", container=author_doc.container,
        timestamp=author_doc.timestamp.isoformat(), author_raw="Ada", title=author_doc.title, body=author_doc.body,
    )
    report = run_ontology_pipeline(conn, index, hydra_store, llm, [target], data_dir=app.DATA_DIR)
    assert report.docs_extracted == 1 and report.relations_written == 1, report

    registry_path, _, _ = registry_paths(app.DATA_DIR)
    registry = EntityRegistry.load(registry_path)
    ada_id = next(eid for eid, rec in registry.entities.items() if rec.canonical_name == "Ada")
    _created_entity_keys.extend(registry.entities.keys())
    for rec in registry.entities.values():
        _created_alias_keys.extend(rec.aliases)

    node = hydra_store.get_node_strong("Entity", ada_id, ["name", "etype"])
    assert node is not None and node["name"] == "Ada", "Entity node must be written and strong-readable"
    alias_node = hydra_store.get_node_strong("Alias", "ada", ["entity_key"])
    assert alias_node is not None and alias_node["entity_key"] == ada_id, "Alias node must point back at the entity"
    print("ok  6.3a: Entity/Alias nodes strong-read back correctly")

    mentioning = hydra_store.docs_mentioning(ada_id)
    assert author_doc.doc_id in mentioning, "MENTIONS edge must connect the doc to the entity it mentions"
    print("ok  6.3b: MENTIONS edge round-trips (Doc -> Entity)")

    who_hits = hydra_store.who_knows(["ada"], ["OWNS"])
    assert any(h["doc_id"] == author_doc.doc_id for h in who_hits), "WHO_KNOWS must return the evidence doc"
    print("ok  6.3c: WHO_KNOWS for a known relation returns its actual evidence doc")

    ask = AskContext.web("actor_check6", aliases=set())
    plan_who = QueryPlan(intent="who", entities=["ada"])
    lane_hits = who_knows_lane(conn, hydra_store, plan_who, allowed=None)
    assert any(d.id == author_doc.doc_id for d in lane_hits), "who_knows_lane must hydrate the same doc"
    print("ok  6.3d: who_knows_lane hydrates real RetrievedDoc rows for the WHO_KNOWS hit")

    plan_graph = QueryPlan(intent="multihop", entities=["ada"])
    graph_hits = graph_lane(conn, hydra_store, plan_graph, allowed=None)
    assert any(d.id == author_doc.doc_id for d in graph_hits), "graph_lane must find the doc within its hop bound"
    print("ok  6.3e: graph_lane finds the mentioning doc via alias -> entity -> MENTIONS expansion")

    # Visibility: a private doc must not surface to a room that can't see it.
    private_doc = _doc(11, "Private note", "Ada owns a private thing too.", visibility=Visibility.channel("slack", "Cpriv").stamp)
    _store(conn, index, hydra_store, private_doc)
    hydra_store.link_nodes("MENTIONS", "Doc", "Entity", [{"from_key": private_doc.doc_id, "to_key": ada_id, "rel_key": f"{private_doc.doc_id}::{ada_id}"}])
    public_only = frozenset({"org"})
    filtered = graph_lane(conn, hydra_store, plan_graph, allowed=public_only)
    assert not any(d.id == private_doc.doc_id for d in filtered), "graph_lane must respect allowed_stamps like every other lane"
    print("ok  6.3f: graph_lane honours allowed_stamps — a public room never sees a private-channel doc")


# ---- 6.4 Supersession -------------------------------------------------------


def check_supersession_flip_and_reversed_edge(conn: sqlite3.Connection, index: LiveIndex, hydra_store: HydraStore) -> None:
    old_doc = _doc(20, "March decision", "We decided to use Postgres.", source_type="slack", ts="2026-03-01T00:00:00+00:00")
    new_doc = _doc(21, "August reversal", "Actually, we reversed the March decision -- switching to SQLite.", source_type="slack", ts="2026-08-01T00:00:00+00:00")
    _store(conn, index, hydra_store, old_doc)
    _store(conn, index, hydra_store, new_doc)

    entity_key = f"chk6proj_{RUN_ID}"
    _created_entity_keys.append(entity_key)
    hydra_store.upsert_nodes("Entity", [{"key": entity_key, "name": "Data Layer", "etype": "PROJECT", "identifier": ""}])
    hydra_store.link_nodes(
        "DECIDED", "Entity", "Entity",
        [{"from_key": entity_key, "to_key": entity_key, "rel_key": f"{old_doc.doc_id}::decided", "doc_id": old_doc.doc_id, "ctx": "use Postgres", "ts": "2026-03-01T00:00:00+00:00", "confidence": 0.9}],
    )

    existing = hydra_store.edges_from("Entity", entity_key, "DECIDED", "Entity")
    existing_claims = [Claim(doc_id=e["doc_id"], source_type="slack", doc_type=None, ts=e["ts"], confidence=1.0) for e in existing]
    candidate = Claim(doc_id=new_doc.doc_id, source_type="slack", doc_type=None, ts="2026-08-01T00:00:00+00:00", confidence=0.9)
    decisions = reconcile_claim(candidate, existing_claims, explicit_supersedes=True, entity_key=entity_key, predicate="DECIDED")
    conflicts_path = app.DATA_DIR / "graphs" / f"conflicts_{RUN_ID}.json"
    flipped = apply_decisions(conn, hydra_store, decisions, now="2026-08-01T00:00:00+00:00", conflicts_path=conflicts_path)
    assert flipped == [old_doc.doc_id], f"expected old_doc to flip, got {flipped}"

    row = conn.execute("SELECT validity FROM docs WHERE id=?", (old_doc.doc_id,)).fetchone()
    assert row["validity"] == "superseded", "loser must be superseded in SQLite"
    graph_node = hydra_store.get_node_strong("Doc", old_doc.doc_id, ["validity"])
    assert graph_node["validity"] == "superseded", "loser must be superseded in the graph too"
    reversed_hits = hydra_store.hydra.bolt(
        "MATCH (w:Doc {id: $wid})-[r:REVERSED]->(l:Doc {id: $lid}) RETURN r.ts AS ts",
        wid=to_vertex_id(new_doc.doc_id),
        lid=to_vertex_id(old_doc.doc_id),
    )
    assert reversed_hits, "a :REVERSED edge must exist from winner to loser"
    still_there = conn.execute("SELECT 1 FROM docs WHERE id=?", (old_doc.doc_id,)).fetchone()
    assert still_there is not None, "the superseded doc must still be retrievable, never deleted"
    print("ok  6.4a: explicit supersession flips the loser (SQLite + graph), writes REVERSED, keeps it retrievable")

    if conflicts_path.exists():
        conflicts_path.unlink()


def check_unresolved_conflict_logged(conn: sqlite3.Connection, hydra_store: HydraStore) -> None:
    conflicts_path = app.DATA_DIR / "graphs" / f"conflicts_{RUN_ID}_unresolved.json"
    a = Claim(doc_id=f"chk6_{RUN_ID}_a", source_type="slack", doc_type=None, ts=None, confidence=0.9)
    b = Claim(doc_id=f"chk6_{RUN_ID}_b", source_type="slack", doc_type=None, ts=None, confidence=0.9)
    decisions = reconcile_claim(a, [b], explicit_supersedes=False, entity_key="e", predicate="DECIDED")
    assert decisions and decisions[0].rule == "unresolvable"
    with sqlite3.connect(":memory:") as scratch:
        scratch.row_factory = sqlite3.Row
        scratch.execute("CREATE TABLE docs(id TEXT PRIMARY KEY, validity TEXT)")
        scratch.execute("INSERT INTO docs VALUES (?, 'current')", (a.doc_id,))
        scratch.execute("INSERT INTO docs VALUES (?, 'current')", (b.doc_id,))

        class _NoGraph:
            def set_property(self, *a, **k):
                raise AssertionError("a tie must not flip anything in the graph")

            def create_edge(self, *a, **k):
                raise AssertionError("a tie must not write a REVERSED edge")

        flipped = apply_decisions(scratch, _NoGraph(), decisions, now="t0", conflicts_path=conflicts_path)
        assert flipped == [], "an unresolvable tie must flip nothing"
    logged = json.loads(conflicts_path.read_text())
    assert len(logged) == 1 and set(logged[0]["doc_ids"]) == {a.doc_id, b.doc_id}
    conflicts_path.unlink()
    print("ok  6.4b: an unresolvable conflict logs both doc_ids and the rule, flips nothing")


def check_real_llm_smoke() -> None:
    import os

    if not os.getenv("LLM_API_KEY"):
        print("skip 6.5: LLM_API_KEY not set — real-LLM smoke test skipped")
        return
    from joel.llm import make_openrouter_caller

    settings_map = {
        "llm_base_url": os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        "llm_api_key": os.environ["LLM_API_KEY"],
        "llm_model_extract": os.getenv("LLM_MODEL_EXTRACT", "anthropic/claude-sonnet-4.5"),
    }
    llm_call = make_openrouter_caller(settings_map)
    result = extract_ontology(
        llm_call,
        ExtractInput(
            doc_id="real_smoke", source_type="confluence", container="eng-docs", timestamp="2026-08-01T00:00:00+00:00",
            author_raw="Priya", title="Migration decision",
            body="Priya decided the team will migrate the auth service to the new session store by end of Q3. "
                 "Sam objected, citing the unresolved token-refresh bug, but the migration proceeded anyway.",
        ),
    )
    assert result.entities, "a real extraction over a document with a clear decision must find at least one entity"
    names = {e.name for e in result.entities}
    assert any("priya" in n.lower() for n in names), f"expected Priya among extracted entities, got {names}"
    print(f"ok  6.5: real LLM extraction found {len(result.entities)} entities, {len(result.relations)} relations")


def main() -> None:
    load_dotenv(ROOT / ".env")
    settings = Settings.from_env()

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        app.DATA_DIR = tmp_dir
        app.DB_PATH = tmp_dir / "index" / "joel.db"
        app.init_db()

        with app.db() as conn:
            with Hydra(settings) as hydra:
                hydra_store = HydraStore(hydra)
                index = LiveIndex(tmp_dir / f"vectors_{RUN_ID}.npz", dim=_FAKE_EMBED_DIM)

                try:
                    check_extraction_grounding(conn)
                    check_extraction_noise_gate(conn)
                    check_pair_score_and_blocking()
                    check_matching_identifier_auto_merges()
                    check_conflicting_identifiers_stay_separate()
                    check_llm_verdict_cached_by_sorted_pair()
                    check_never_merges_across_type()
                    check_graph_write_and_lanes(conn, index, hydra_store)
                    check_supersession_flip_and_reversed_edge(conn, index, hydra_store)
                    check_unresolved_conflict_logged(conn, hydra_store)
                finally:
                    for doc_id in _created_doc_ids:
                        hydra_store.delete_node("Doc", doc_id)
                    for entity_key in _created_entity_keys:
                        hydra_store.delete_node("Entity", entity_key)
                    for alias_key in _created_alias_keys:
                        hydra_store.delete_node("Alias", alias_key)

    check_real_llm_smoke()

    print("\nCP 6 ontology: all automated checks passed.")


if __name__ == "__main__":
    main()
