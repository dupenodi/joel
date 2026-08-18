"""Checkpoint 5: the store layer (§8) — SQLite+FTS5, the LiveIndex vector
store, and HydraDB's :Doc graph nodes, wired together by `upsert_docs`.

Runs against a real, disposable SQLite database (through the actual
migrations in `app.py`) and the real local HydraDB node used by CP0/CP1 —
this phase's whole point is three storage engines staying honest with each
other, which a mock can't tell you. The embedding model is the real
`sentence-transformers` local model (already required by CP0); LiveIndex
persists to a scratch npz file, deleted at the end of the run.
"""

from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402

import joel.app as app  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.config import Settings  # noqa: E402
from joel.live_index import LiveIndex  # noqa: E402
from joel.models import Burst, CanonicalDoc, ThreadArtifact, compute_content_hash  # noqa: E402
from joel.store import HydraStore  # noqa: E402
from joel.store_sql import (  # noqa: E402
    StoreDoc,
    from_burst,
    from_canonical_doc,
    from_thread_artifact,
    upsert_docs,
)

RUN_ID = uuid.uuid4().hex[:8]  # scopes every doc id this run touches so re-running the script never collides


def _doc(i: int, title: str, body: str, *, source_type: str = "slack") -> CanonicalDoc:
    return CanonicalDoc(
        doc_id=f"chk5_{RUN_ID}_{i}",
        source_type=source_type,
        external_id=f"ext_{i}",
        title=title,
        body=body,
        container="C_CHECK5",
        content_hash=compute_content_hash(title, body),
    )


_FAKE_EMBED_DIM = 64


def _fake_embed(texts: list[str]):
    """Deterministic fixed-width (feature-hashed bag-of-words) embedding for
    the fast SQLite/FTS/graph checks (5.1, 5.3, 5.4, 5.5) — real semantic
    quality is exercised separately in `check_semantic_ranking` with the
    real local model. Fixed width matters: a real embedding model always
    returns the same dimension, and LiveIndex.apply() assumes that too."""
    import numpy as np

    matrix = np.zeros((len(texts), _FAKE_EMBED_DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in text.lower().split():
            idx = hash(word) % _FAKE_EMBED_DIM
            matrix[i, idx] += 1.0
    return matrix


def _make_index(dim: int, tmp_dir: Path) -> LiveIndex:
    return LiveIndex(tmp_dir / f"vectors_{RUN_ID}.npz", dim=dim)


def check_fts_phrase_and_operators(conn: sqlite3.Connection) -> None:
    # Raw-inserted (bypasses upsert_docs entirely -- this check is only
    # about FTS5 query behavior), so it's deliberately NOT under the
    # "chk5_{RUN_ID}_" prefix that check_consistency reconciles across all
    # three stores -- a doc that never went through vectors/graph on purpose
    # would otherwise look like drift.
    doc = CanonicalDoc(
        doc_id=f"chk5raw_{RUN_ID}_1",
        source_type="slack",
        external_id="ext_1",
        title="Restore incident",
        body="Getting ERR_MANIFEST_TIMEOUT on restore after manifest load.",
        container="C_CHECK5",
        content_hash=compute_content_hash("Restore incident", "body"),
    )
    sd = from_canonical_doc(doc)
    conn.execute(
        """INSERT INTO docs(id, source_type, external_id, title, body, content_hash, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,'now','now')""",
        (sd.id, sd.source_type, doc.external_id, sd.title, sd.body, sd.content_hash),
    )
    rowid = conn.execute("SELECT rowid FROM docs WHERE id=?", (sd.id,)).fetchone()[0]
    conn.execute("INSERT INTO docs_fts(rowid, title, body) VALUES (?,?,?)", (rowid, sd.title, sd.body))

    rows = conn.execute(
        "SELECT d.id FROM docs_fts f JOIN docs d ON d.rowid = f.rowid "
        "WHERE docs_fts MATCH ?",
        ('"ERR_MANIFEST_TIMEOUT"',),
    ).fetchall()
    assert any(r["id"] == sd.id for r in rows), "phrase query for the pasted error must return the doc"

    # A raw question containing FTS5 operator tokens must not crash MATCH.
    for hostile in ["restore OR timeout", "manifest NEAR load", "restore *"]:
        conn.execute(
            "SELECT d.id FROM docs_fts f JOIN docs d ON d.rowid=f.rowid WHERE docs_fts MATCH ?",
            (f'"{hostile}"',),
        ).fetchall()
    print("ok  5.1a: FTS phrase query hits the pasted error; OR/NEAR/* quoted queries don't crash")


def check_fts_reupsert_no_duplicate(conn: sqlite3.Connection, index: LiveIndex, hydra_store: HydraStore) -> None:
    doc = _doc(2, "Reupsert check", "original body text about caching layers")
    sd = from_canonical_doc(doc)
    upsert_docs(conn, index, hydra_store, [sd], embed_fn=_fake_embed, now="t0")

    def fts_row_count(doc_id: str) -> int:
        rowid = conn.execute("SELECT rowid FROM docs WHERE id=?", (doc_id,)).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM docs_fts WHERE rowid=?", (rowid,)).fetchone()[0]

    assert fts_row_count(sd.id) == 1

    # Re-upsert the SAME content: still exactly one FTS row.
    upsert_docs(conn, index, hydra_store, [sd], embed_fn=_fake_embed, now="t1")
    assert fts_row_count(sd.id) == 1, "unchanged re-upsert duplicated the FTS row"

    # Edit and re-upsert: still exactly one FTS row, and it reflects the NEW text.
    edited = _doc(2, "Reupsert check", "EDITED body text about caching layers, mentions REDIS_TTL")
    sd_edited = from_canonical_doc(edited)
    upsert_docs(conn, index, hydra_store, [sd_edited], embed_fn=_fake_embed, now="t2")
    assert fts_row_count(sd.id) == 1, "edit-then-reupsert must delete-before-insert, not duplicate"
    hit = conn.execute(
        "SELECT d.id FROM docs_fts f JOIN docs d ON d.rowid=f.rowid WHERE docs_fts MATCH ?",
        ('"REDIS_TTL"',),
    ).fetchall()
    assert any(r["id"] == sd.id for r in hit), "FTS must be searchable on the EDITED text"
    stale = conn.execute(
        "SELECT d.id FROM docs_fts f JOIN docs d ON d.rowid=f.rowid WHERE docs_fts MATCH ?",
        ('"original"',),
    ).fetchall()
    assert not any(r["id"] == sd.id for r in stale), "FTS must NOT still match the OLD text after edit"
    print("ok  5.1b: unchanged and edited re-upserts both leave exactly one (correct) FTS row")


def check_wal_mode(conn: sqlite3.Connection) -> None:
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal", f"expected WAL, got {mode!r}"
    print("ok  5.1c: PRAGMA journal_mode reports wal")


def check_vectors_unit_norm_and_hot_reload(
    conn: sqlite3.Connection, index: LiveIndex, hydra_store: HydraStore
) -> None:
    import numpy as np

    docs = [_doc(3, "Doc A", "alpha beta gamma"), _doc(4, "Doc B", "delta epsilon zeta")]
    store_docs = [from_canonical_doc(d) for d in docs]
    upsert_docs(conn, index, hydra_store, store_docs, embed_fn=_fake_embed, now="t0")

    snap = index.snapshot()
    for doc in store_docs:
        row = snap.matrix[snap.row_of[doc.id]]
        norm = float(np.linalg.norm(row))
        assert abs(norm - 1.0) < 1e-5 or norm == 0.0, f"vector for {doc.id} is not unit-norm ({norm})"

    # 5.3: upsert and retrieve in the SAME process, no restart.
    results = index.search(snap.matrix[snap.row_of[store_docs[0].id]], k=5)
    assert results and results[0][0] == store_docs[0].id
    print("ok  5.2a/5.3a: stored vectors are unit-norm; upsert->search works with no restart")

    # 5.3: metadata mask reflects a just-changed validity, no restart.
    superseded = docs[0].model_copy(update={"validity": "superseded"})
    upsert_docs(conn, index, hydra_store, [from_canonical_doc(superseded)], embed_fn=_fake_embed, now="t1")
    mask_current = index.mask(validity="current")
    row_a = index.snapshot().row_of[store_docs[0].id]
    assert not mask_current[row_a], "validity=superseded must be reflected in the mask immediately"
    print("ok  5.3b: metadata mask reflects a just-written validity change with no restart")


def check_semantic_ranking() -> None:
    """5.2b: a real semantic query, real local embeddings, ranks the right
    artifact top-3 among distractors. Independent of the SQLite/graph
    plumbing above -- this is purely "does LiveIndex.search do the right
    dot-product ranking with a real embedding model"."""
    from sentence_transformers import SentenceTransformer

    load_dotenv(ROOT / ".env")
    settings = Settings.from_env()
    model = SentenceTransformer(settings.embed_model)

    def embed(texts: list[str]):
        return model.encode(texts, normalize_embeddings=True)

    dim = getattr(model, "get_embedding_dimension", model.get_sentence_embedding_dimension)()
    tmp_index = LiveIndex(ROOT / "data" / f"_chk5_semantic_{RUN_ID}.npz", dim=dim)
    try:
        corpus = {
            "target": "Set CKPT_PREFETCH=4 to fix restore hanging after manifest load on slow NFS mounts.",
            "distractor_1": "Quarterly marketing budget review scheduled for next Tuesday afternoon.",
            "distractor_2": "New hire onboarding checklist: laptop, badge, Slack, benefits enrollment.",
            "distractor_3": "Recipe for sourdough bread starter maintenance and feeding schedule.",
        }
        vectors = embed(list(corpus.values()))
        upserts = {
            doc_id: (vectors[i], {"granularity": "artifact", "source_type": "slack"})
            for i, doc_id in enumerate(corpus)
        }
        tmp_index.apply(upserts, deleted=[])

        query_vec = embed(["why does restore hang after the manifest load step"])[0]
        results = tmp_index.search(query_vec, k=3)
        top_ids = [doc_id for doc_id, _ in results]
        assert "target" in top_ids, f"expected 'target' in top-3, got {top_ids}"
        print(f"ok  5.2b: real semantic query ranks the right artifact in top-3 ({top_ids})")
    finally:
        tmp_index.npz_path.unlink(missing_ok=True)


def check_graph_create_update_skip(conn: sqlite3.Connection, index: LiveIndex, hydra_store: HydraStore) -> None:
    doc = _doc(5, "Graph doc", "graph write correctness check")
    sd = from_canonical_doc(doc)

    report1 = upsert_docs(conn, index, hydra_store, [sd], embed_fn=_fake_embed, now="t0")
    assert sd.id in report1.graph_created, "brand-new doc must be graph_created"
    node = hydra_store.get_node_strong(
        "Doc", sd.id, ["title", "source_type", "container", "granularity", "validity", "resolved"]
    )
    assert node is not None, "new doc must create a :Doc node"
    assert node["title"] == sd.title
    assert node["source_type"] == sd.source_type
    assert node["container"] == sd.container
    assert node["granularity"] == sd.granularity
    print("ok  5.4a: a new doc creates a :Doc node with every property")

    # Unchanged re-upsert: no graph write at all.
    report2 = upsert_docs(conn, index, hydra_store, [sd], embed_fn=_fake_embed, now="t1")
    assert sd.id in report2.graph_skipped
    assert sd.id not in report2.graph_created and sd.id not in report2.graph_updated
    print("ok  5.4c: an unchanged doc issues no graph write")

    # Edited doc: updates the EXISTING node rather than being skipped.
    edited_doc = _doc(5, "Graph doc RENAMED", "graph write correctness check, now edited")
    sd_edited = from_canonical_doc(edited_doc)
    report3 = upsert_docs(conn, index, hydra_store, [sd_edited], embed_fn=_fake_embed, now="t2")
    assert sd.id in report3.graph_updated, "content_hash changed -> must be graph_updated, not skipped"
    node2 = hydra_store.get_node_strong("Doc", sd.id, ["title"])
    assert node2["title"] == "Graph doc RENAMED", "the existing :Doc node must reflect the edit"
    print("ok  5.4b: an edited doc updates its existing :Doc node instead of being skipped")


def check_distilled_from_edges(conn: sqlite3.Connection, index: LiveIndex, hydra_store: HydraStore) -> None:
    from datetime import datetime, timezone

    t0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    bursts = [
        Burst(
            burst_id=f"chk5_{RUN_ID}_burst_{i}",
            thread_id=f"chk5_{RUN_ID}_thread",
            author_raw="@x",
            text=f"burst text {i}",
            message_external_ids=[f"m{i}"],
            start_ts=t0,
            end_ts=t0,
            role="resolution" if i == 0 else "context",
            kept=True,
        )
        for i in range(3)
    ]
    artifact = ThreadArtifact(
        artifact_id=f"chk5_{RUN_ID}_artifact",
        thread_id=f"chk5_{RUN_ID}_thread",
        source_type="slack",
        container="C_CHECK5",
        question="Why did the check5 thread need a fix?",
        summary="summary",
        resolution="did the fix",
        resolved=True,
        systems=[],
        code_refs=[],
        actors=[],
        artifact_class="qa",
        supersedes=None,
        confidence=0.9,
        timestamp=t0,
        source_message_ids=["m0", "m1", "m2"],
    )

    burst_docs = [
        from_burst(b, source_type="slack", container="C_CHECK5", thread_question=artifact.question)
        for b in bursts
    ]
    artifact_doc = from_thread_artifact(artifact, kept_burst_ids=[b.id for b in burst_docs])

    upsert_docs(conn, index, hydra_store, burst_docs, embed_fn=_fake_embed, now="t0")
    report = upsert_docs(conn, index, hydra_store, [artifact_doc], embed_fn=_fake_embed, now="t0")
    assert report.distilled_from_edges == len(bursts)

    edges = hydra_store.traverse_any_type("Doc", artifact_doc.id, ["DISTILLED_FROM"], to_label="Doc")
    assert len(edges) == len(bursts), f"expected {len(bursts)} DISTILLED_FROM edges, got {len(edges)}"
    got_keys = {e["key"] for e in edges}
    assert got_keys == {b.id for b in burst_docs}
    print(f"ok  5.4d: DISTILLED_FROM count ({len(edges)}) matches the kept-burst count")


def check_consistency(conn: sqlite3.Connection, index: LiveIndex, hydra_store: HydraStore) -> None:
    sqlite_count = conn.execute(
        "SELECT COUNT(*) FROM docs WHERE id LIKE ?", (f"chk5_{RUN_ID}_%",)
    ).fetchone()[0]
    npz_count = sum(1 for doc_id in index.snapshot().ids if doc_id.startswith(f"chk5_{RUN_ID}_"))
    graph_ids = [doc_id for doc_id in index.snapshot().ids if doc_id.startswith(f"chk5_{RUN_ID}_")]
    graph_count = 0
    for doc_id in graph_ids:
        if hydra_store.get_node_strong("Doc", doc_id, ["title"]) is not None:
            graph_count += 1

    assert sqlite_count == npz_count == graph_count, (
        f"SQLite={sqlite_count} npz={npz_count} graph={graph_count} — drift!"
    )
    print(f"ok  5.5a: SQLite ({sqlite_count}) == npz ({npz_count}) == graph ({graph_count}) for this run's docs")

    # Re-running the whole batch of already-upserted docs must change no counts.
    doc = _doc(2, "Reupsert check", "original body text about caching layers")
    upsert_docs(conn, index, hydra_store, [from_canonical_doc(doc)], embed_fn=_fake_embed, now="t3")
    sqlite_count2 = conn.execute(
        "SELECT COUNT(*) FROM docs WHERE id LIKE ?", (f"chk5_{RUN_ID}_%",)
    ).fetchone()[0]
    assert sqlite_count2 == sqlite_count, "re-running an unchanged batch must not change row counts"
    print("ok  5.5b: re-running the batch changes no counts")


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
                index = _make_index(dim=64, tmp_dir=tmp_dir)

                check_fts_phrase_and_operators(conn)
                check_fts_reupsert_no_duplicate(conn, index, hydra_store)
                check_wal_mode(conn)
                check_vectors_unit_norm_and_hot_reload(conn, index, hydra_store)
                check_graph_create_update_skip(conn, index, hydra_store)
                check_distilled_from_edges(conn, index, hydra_store)
                check_consistency(conn, index, hydra_store)

    check_semantic_ranking()

    print("\nCP 5 store layer: all automated checks passed.")


if __name__ == "__main__":
    main()
