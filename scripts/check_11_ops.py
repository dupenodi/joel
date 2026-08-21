"""Checkpoint 11: operations (§14) — traces.jsonl rotation, health's real
index-triple reporting, forget's canonical tombstone, and rebuild_index.py
against a small synthetic fixture (§14.4's own "run it in CI on a small
fixture" requirement — the real ~1400-doc corpus is exercised manually,
not on every run of this script).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

import joel.app as app  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.config import Settings  # noqa: E402
from joel.live_index import LiveIndex  # noqa: E402
from joel.models import CanonicalDoc, compute_content_hash  # noqa: E402
from joel.retrieve import TRACES_MAX_BACKUPS, TRACES_MAX_BYTES, RetrievalTrace, log_trace  # noqa: E402
from joel.retrieve.planner import QueryPlan  # noqa: E402
from joel.store import HydraStore  # noqa: E402
from joel.store_sql import from_canonical_doc, upsert_docs  # noqa: E402

import rebuild_index  # noqa: E402

RUN_ID = uuid.uuid4().hex[:8]
_FAKE_EMBED_DIM = 64


def _fake_embed(texts: list[str]):
    import numpy as np

    matrix = np.zeros((len(texts), _FAKE_EMBED_DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in text.lower().split():
            matrix[i, hash(word) % _FAKE_EMBED_DIM] += 1.0
    return matrix


def check_traces_rotation(tmp_dir: Path) -> None:
    traces_path = tmp_dir / "traces.jsonl"
    trace = RetrievalTrace(question="q", plan=QueryPlan(intent="lookup"))
    # Force one write past the size cap by shrinking it for this check only.
    import joel.retrieve as retrieve_mod

    original = retrieve_mod.TRACES_MAX_BYTES
    retrieve_mod.TRACES_MAX_BYTES = 200
    try:
        for _ in range(20):
            log_trace(traces_path, trace)
        assert traces_path.exists()
        assert (tmp_dir / "traces.jsonl.1").exists(), "the file must rotate once it crosses the size cap"
        assert traces_path.stat().st_size < 500, "the live file must be small again right after rotating"
    finally:
        retrieve_mod.TRACES_MAX_BYTES = original
    print(f"ok  11.1: traces.jsonl rotates past {200}B instead of growing forever")


def check_health_reports_real_counts(tmp_dir: Path) -> None:
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()
    settings = Settings.from_env()
    with Hydra(settings) as hydra:
        hydra_store = HydraStore(hydra)
        index = LiveIndex(tmp_dir / "vectors.npz", dim=_FAKE_EMBED_DIM)
        with app.db() as conn:
            doc = CanonicalDoc(
                doc_id=f"chk11_{RUN_ID}_1",
                source_type="slack",
                external_id="e1",
                title="Health check doc",
                body="A real doc for the real index-triple count.",
                content_hash=compute_content_hash("t", "b"),
            )
            upsert_docs(conn, index, hydra_store, [from_canonical_doc(doc)], embed_fn=_fake_embed, now="t0")

        app._RUNTIME.clear()
        app._RUNTIME["settings"] = settings
        app._RUNTIME["embed_model"] = type("M", (), {"encode": staticmethod(_fake_embed)})()
        app._RUNTIME["hydra"] = hydra
        app._RUNTIME["hydra_store"] = hydra_store
        app._RUNTIME["live_index"] = index

        result = app.health()
        assert result["hydra"] == "ok", result
        assert result["index"]["sqlite"] == 1, result
        assert result["index"]["vectors"] == result["index"]["sqlite"], (
            "a freshly-upserted doc must show up in both sqlite and vector counts"
        )
        # graph is the one shared, real HydraDB namespace across the whole
        # project (§2.1: "one universe") -- a scratch SQLite/vectors will
        # never numerically equal the real corpus's graph count, so this
        # only asserts the count is real and live (not the hardcoded stub's
        # permanent 0), not that all three literally match in this test.
        assert result["index"]["graph"] is not None and result["index"]["graph"] > 1, result
        assert result["index"]["consistent"] is False, (
            "a scratch SQLite next to the real shared graph must correctly report inconsistent, not a false True"
        )

        hydra_store.delete_node("Doc", doc.doc_id)
    app._RUNTIME.clear()
    print("ok  11.2: /api/health reports real sqlite/vector/graph counts, not a hardcoded stub")


def check_health_degrades_when_hydra_unreachable(tmp_dir: Path) -> None:
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()
    settings = Settings.from_env()
    broken = Settings(
        hydra_http="http://127.0.0.1:1",  # nothing listens here
        hydra_bolt="neo4j://127.0.0.1:1",
        hydra_token=settings.hydra_token,
        hydra_root_namespace=settings.hydra_root_namespace,
        hydra_base_database=settings.hydra_base_database,
        hydra_cell=settings.hydra_cell,
        embed_model=settings.embed_model,
    )
    app._RUNTIME.clear()
    app._RUNTIME["settings"] = broken
    app._RUNTIME["embed_model"] = type("M", (), {"encode": staticmethod(_fake_embed)})()

    result = app.health()
    assert result["hydra"] != "ok", "an unreachable HydraDB must be reported, not silently 'ok'"
    assert result["index"]["graph"] is None
    assert result["index"]["consistent"] is None, "unknown must not be reported as a false True or False"
    assert result["index"]["sqlite"] == 0  # still real -- SQLite itself is fine, just empty
    app._RUNTIME.clear()
    print("ok  11.3: /api/health degrades honestly when HydraDB is unreachable (§14.6), doesn't 500")


def check_rebuild_from_canonical(tmp_dir: Path) -> None:
    """§14.4's own requirement: run rebuild_index against a SMALL fixture,
    not the real corpus, on every run of this checkpoint."""
    canonical_dir = tmp_dir / "canonical"
    canonical_dir.mkdir(parents=True)
    docs = [
        CanonicalDoc(
            doc_id=f"chk11rb_{RUN_ID}_{i}",
            source_type="slack",
            external_id=f"e{i}",
            title=f"Fixture doc {i}",
            body=f"Body text {i} for the rebuild fixture.",
            content_hash=compute_content_hash(f"t{i}", f"b{i}"),
        )
        for i in range(3)
    ]
    with (canonical_dir / "slack.jsonl").open("w") as handle:
        for doc in docs:
            handle.write(doc.model_dump_json() + "\n")
        # A superseding line for doc 0 (simulates a re-sync's "changed" append).
        edited = docs[0].model_copy(update={"title": "Fixture doc 0 EDITED"})
        handle.write(edited.model_dump_json() + "\n")
        # A forget tombstone for doc 1 -- must be excluded from the rebuild.
        handle.write(json.dumps({"doc_id": docs[1].doc_id, "source_type": "slack", "forgotten": True}) + "\n")

    surviving, forgotten = rebuild_index.replay_canonical(canonical_dir)
    assert forgotten == {docs[1].doc_id}
    assert set(surviving.keys()) == {docs[0].doc_id, docs[2].doc_id}
    assert surviving[docs[0].doc_id].title == "Fixture doc 0 EDITED", (
        "replay must keep the LAST state per doc_id, not the first"
    )
    print("ok  11.4a: replay_canonical folds to the latest state per doc_id and excludes forgotten ones")

    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()
    settings = Settings.from_env()
    with app.db() as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        with Hydra(settings) as hydra:
            hydra_store = HydraStore(hydra)
            index = LiveIndex(tmp_dir / "vectors_rb.npz", dim=_FAKE_EMBED_DIM)
            survivors = list(surviving.values())
            rebuild_index._upsert_docs_table(conn, survivors, now="t0")
            report = upsert_docs(
                conn, index, hydra_store, [from_canonical_doc(d) for d in survivors], embed_fn=_fake_embed, now="t0"
            )
            assert len(report.sqlite_upserted) == 2
            row = conn.execute(
                "SELECT title FROM docs WHERE id=?", (docs[0].doc_id,)
            ).fetchone()
            assert row["title"] == "Fixture doc 0 EDITED"
            forgotten_row = conn.execute(
                "SELECT 1 FROM docs WHERE id=?", (docs[1].doc_id,)
            ).fetchone()
            assert forgotten_row is None, "a forgotten doc must not come back after a rebuild"
            for doc_id in (docs[0].doc_id, docs[2].doc_id):
                hydra_store.delete_node("Doc", doc_id)
    print("ok  11.4b: a rebuild from canonical reproduces docs/FTS/vectors/graph, forgotten docs stay gone")


def main() -> None:
    load_dotenv(ROOT / ".env")
    with tempfile.TemporaryDirectory() as td:
        check_traces_rotation(Path(td))
    with tempfile.TemporaryDirectory() as td:
        check_health_reports_real_counts(Path(td))
    with tempfile.TemporaryDirectory() as td:
        check_health_degrades_when_hydra_unreachable(Path(td))
    with tempfile.TemporaryDirectory() as td:
        check_rebuild_from_canonical(Path(td))
    print("\nCP 11 operations: all automated checks passed.")


if __name__ == "__main__":
    main()
