"""The ingest → distill → store integration pass (`pipeline.py`) — the seam
CP3 (adapters), CP4 (distillation), and CP5 (store) each verified in
isolation but never called into each other until now. Not its own numbered
phase (CP 6 is Ontology, §9); this is the connective tissue CP4 and CP5's
own status notes called out as still missing.

Runs against a real, disposable SQLite database (through the actual
migrations in `app.py`, same as CP5) and the real local HydraDB node used by
CP0/CP1/CP5. The LLM is a fake, queued-response `LLMCallFn` (no network, no
cost) so re-distillation scenarios — a burst dropping out, a thread flipping
to noise — are deterministic; `check_pending_adapters.py` already covers a
real end-to-end sync against real connector data with a real LLM key.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402

import joel.app as app  # noqa: E402
from joel.config import Settings  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.live_index import LiveIndex  # noqa: E402
from joel.models import CanonicalDoc, compute_content_hash  # noqa: E402
from joel.pipeline import load_thread_messages, run_store_pipeline  # noqa: E402
from joel.store import HydraStore  # noqa: E402

RUN_ID = uuid.uuid4().hex[:8]
T0 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

_FAKE_EMBED_DIM = 64


def _fake_embed(texts: list[str]):
    import numpy as np

    matrix = np.zeros((len(texts), _FAKE_EMBED_DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in text.lower().split():
            idx = hash(word) % _FAKE_EMBED_DIM
            matrix[i, idx] += 1.0
    return matrix


def _queued_llm(responses: list[dict]):
    """Fake LLMCallFn that returns one queued response per call, in order,
    and records every user prompt it was given (so tests can assert on
    exactly which messages made it into the distill call)."""
    state = {"n": 0, "prompts": []}

    def _call(stage: str, system_prompt: str, user_prompt: str) -> str:
        assert stage == "distill"
        state["prompts"].append(user_prompt)
        resp = responses[min(state["n"], len(responses) - 1)]
        state["n"] += 1
        return json.dumps(resp)

    _call.state = state  # type: ignore[attr-defined]
    return _call


def _msg(thread_id: str, i: int, author: str, body: str, *, minutes: float, source_type: str = "slack") -> CanonicalDoc:
    return CanonicalDoc(
        doc_id=f"chk6_{RUN_ID}_{thread_id}_{i}",
        source_type=source_type,
        external_id=f"{thread_id}_{i}",
        title="",
        body=body,
        author_raw=author,
        container="C_CHECK6",
        thread_id=f"chk6_{RUN_ID}_{thread_id}",
        timestamp=T0 + timedelta(minutes=minutes),
        content_hash=compute_content_hash("", body),
    )


_RESTORE_RESPONSE = {
    "message_roles": [
        {"index": 0, "role": "question"},
        {"index": 1, "role": "resolution"},
        {"index": 2, "role": "noise"},
    ],
    "question": "Why does restore hang after manifest load?",
    "summary": "Restore stalled after the manifest-load step.",
    "resolution": "Set CKPT_PREFETCH=4.",
    "resolved": True,
    "systems": ["restore"],
    "code_refs": ["ERR_MANIFEST_TIMEOUT", "CKPT_PREFETCH"],
    "actors": [{"name": "@soham", "role": "asker"}],
    "artifact_class": "qa",
    "supersedes": None,
    "confidence": 0.9,
}

_NOISE_RESPONSE = {
    "message_roles": [],
    "question": "n/a",
    "summary": "chit-chat",
    "resolution": None,
    "resolved": False,
    "systems": [],
    "code_refs": [],
    "actors": [],
    "artifact_class": "noise",
    "supersedes": None,
    "confidence": 0.9,
}


def check_raw_docs_stored_no_distill(conn, index, hydra_store) -> None:
    """A non-threaded doc (jira/confluence/gdrive-shaped) is stored as-is;
    the LLM must never be called since there's no thread_id to group."""
    doc = CanonicalDoc(
        doc_id=f"chk6_{RUN_ID}_singleton_0",
        source_type="jira",
        external_id="PROJ-1",
        title="Fix the thing",
        body="Ticket body with no thread_id at all.",
        content_hash=compute_content_hash("Fix the thing", "body"),
    )

    def _boom(stage, system, user):
        raise AssertionError("LLM must not be called for a doc with no thread_id")

    report = run_store_pipeline(conn, index, hydra_store, _fake_embed, _boom, [doc])
    assert report.docs_stored == 1
    assert report.threads_seen == 0
    row = conn.execute("SELECT title FROM docs WHERE id=?", (doc.doc_id,)).fetchone()
    assert row is not None and row["title"] == "Fix the thing"
    print("ok  6.1: a non-threaded doc is stored raw and never reaches the LLM")


def check_threaded_docs_trigger_distillation(conn, index, hydra_store) -> None:
    thread = "restore"
    msgs = [
        _msg(thread, 0, "@soham", "Restore hangs after manifest load, ERR_MANIFEST_TIMEOUT.", minutes=0),
        _msg(thread, 1, "@bob", "Setting CKPT_PREFETCH=4 fixed it.", minutes=1),
        _msg(thread, 2, "@soham", "thanks!", minutes=2),
    ]
    counts, dirty = app._persist_canonical_docs(conn, msgs)
    assert counts["new"] == 3

    llm = _queued_llm([_RESTORE_RESPONSE])
    report = run_store_pipeline(conn, index, hydra_store, _fake_embed, llm, dirty)

    assert report.docs_stored == 3
    assert report.threads_seen == 1
    assert report.threads_distilled == 1
    assert report.artifacts_written == 1
    assert "ERR_MANIFEST_TIMEOUT" in llm.state["prompts"][0]

    thread_id = f"chk6_{RUN_ID}_{thread}"
    artifact_row = conn.execute(
        "SELECT id, title, granularity FROM docs WHERE granularity='artifact' AND id LIKE ?",
        (f"art__slack__{thread_id}",),
    ).fetchone()
    assert artifact_row is not None, "distilled artifact must land in SQLite"

    state_row = conn.execute(
        "SELECT kept_bursts_json FROM thread_state WHERE thread_id=?", (thread_id,)
    ).fetchone()
    assert state_row is not None
    kept_bursts = json.loads(state_row["kept_bursts_json"])
    assert len(kept_bursts) == report.bursts_kept

    node = hydra_store.get_node_strong("Doc", artifact_row["id"], ["title", "granularity"])
    assert node is not None, "artifact must also have a :Doc graph node"

    print(f"ok  6.2: a dirty thread gets distilled end-to-end ({report.bursts_kept} bursts kept, 1 artifact)")


def check_dirty_thread_reloads_whole_thread(conn, index, hydra_store) -> None:
    """§7.5: re-distillation must send the WHOLE thread to the LLM, not just
    the newly-arrived message — even though only one new message is "dirty"
    this sync."""
    thread = "restore"
    thread_id = f"chk6_{RUN_ID}_{thread}"
    new_msg = _msg(thread, 3, "@carol", "Also confirmed on staging.", minutes=3)
    counts, dirty = app._persist_canonical_docs(conn, [new_msg])
    assert counts["new"] == 1
    assert len(dirty) == 1, "only the new message should be reported dirty"

    whole_thread = load_thread_messages(conn, thread_id)
    assert len(whole_thread) == 4, f"expected the full 4-message thread, got {len(whole_thread)}"

    llm = _queued_llm([_RESTORE_RESPONSE])
    report = run_store_pipeline(conn, index, hydra_store, _fake_embed, llm, dirty)
    assert report.threads_distilled == 1
    sent_prompt = llm.state["prompts"][0]
    assert "Also confirmed on staging" in sent_prompt
    assert "ERR_MANIFEST_TIMEOUT" in sent_prompt, "the OLD messages must still be in the re-distill prompt"
    print("ok  6.3: one new message re-distills the WHOLE thread, not just the delta")


def check_redistill_drops_stale_burst(conn, index, hydra_store) -> None:
    """Simulate the LLM changing its mind on a re-distill: a burst that was
    kept before now rolls up as pure noise and must disappear from all three
    stores, while the artifact and the resolution burst remain."""
    thread = "restore"
    thread_id = f"chk6_{RUN_ID}_{thread}"

    prior_kept_ids, _ = _load_prior_kept_public(conn, thread_id)
    assert prior_kept_ids, "prior test must have left a kept-burst set to drop from"

    shrink_response = dict(_RESTORE_RESPONSE)
    shrink_response["message_roles"] = [{"index": i, "role": "noise"} for i in range(4)]
    # Force exactly one message (the resolution) to stay a keeper so the
    # artifact is still emitted, everything else rolls off.
    shrink_response["message_roles"][1] = {"index": 1, "role": "resolution"}

    llm = _queued_llm([shrink_response])
    whole_thread = load_thread_messages(conn, thread_id)
    report = run_store_pipeline(conn, index, hydra_store, _fake_embed, llm, whole_thread)
    assert report.threads_distilled == 1
    assert report.bursts_dropped >= 1, "at least one previously-kept burst must be dropped"

    new_kept_ids, _ = _load_prior_kept_public(conn, thread_id)
    dropped = prior_kept_ids - new_kept_ids
    assert dropped, "expected at least one burst id to leave the kept set"
    for burst_id in dropped:
        row = conn.execute("SELECT 1 FROM docs WHERE id=?", (burst_id,)).fetchone()
        assert row is None, f"dropped burst {burst_id} must be gone from SQLite"
        node = hydra_store.get_node_strong("Doc", burst_id, ["title"])
        assert node is None, f"dropped burst {burst_id} must be gone from the graph"
        snap = index.snapshot()
        assert snap.forgotten[snap.row_of[burst_id]], f"dropped burst {burst_id} must be tombstoned in vectors"
    print(f"ok  6.4: re-distillation removes {len(dropped)} stale burst(s) from SQLite+graph+vectors")


def check_thread_flips_to_noise_removes_artifact(conn, index, hydra_store) -> None:
    thread = "chitchat"
    msgs = [
        _msg(thread, 0, "@x", "hey", minutes=0),
        _msg(thread, 1, "@y", "hey how's it going", minutes=1),
    ]
    _, dirty = app._persist_canonical_docs(conn, msgs)
    thread_id = f"chk6_{RUN_ID}_{thread}"

    real_response = dict(_RESTORE_RESPONSE)
    real_response["message_roles"] = [{"index": 0, "role": "question"}, {"index": 1, "role": "resolution"}]
    llm = _queued_llm([real_response])
    report1 = run_store_pipeline(conn, index, hydra_store, _fake_embed, llm, dirty)
    assert report1.artifacts_written == 1
    artifact_row = conn.execute(
        "SELECT id FROM docs WHERE granularity='artifact' AND id LIKE ?", (f"art__slack__{thread_id}",)
    ).fetchone()
    assert artifact_row is not None
    artifact_id = artifact_row["id"]
    prior_kept_ids, _ = _load_prior_kept_public(conn, thread_id)
    assert prior_kept_ids

    # Re-distill: this time the LLM calls it noise entirely.
    llm2 = _queued_llm([_NOISE_RESPONSE])
    whole_thread = load_thread_messages(conn, thread_id)
    report2 = run_store_pipeline(conn, index, hydra_store, _fake_embed, llm2, whole_thread)
    assert report2.threads_distilled == 1
    assert report2.artifacts_written == 0

    for burst_id in prior_kept_ids:
        assert conn.execute("SELECT 1 FROM docs WHERE id=?", (burst_id,)).fetchone() is None
    assert conn.execute("SELECT 1 FROM docs WHERE id=?", (artifact_id,)).fetchone() is None, (
        "an artifact whose thread flips to noise must be removed too"
    )
    new_kept_ids, _ = _load_prior_kept_public(conn, thread_id)
    assert new_kept_ids == set()
    print("ok  6.5: a thread flipping to noise on re-distill removes its prior artifact + kept bursts")


def _load_prior_kept_public(conn, thread_id):
    from joel.distill.state import load_prior_kept

    return load_prior_kept(conn, thread_id)


def check_pre_existing_raw_doc_gets_indexed(conn, index, hydra_store) -> None:
    """The real-data gap this whole pass was for: a doc that landed in
    `docs` via plain ingest (§6, `_persist_canonical_docs`) long before this
    pipeline ever ran must be indexable by `upsert_docs` on its FIRST pass
    through it — `docs` already having a row for that id must NOT be
    confused with `docs_fts` already having one (they didn't, historically,
    for anything ingested before CP5 existed)."""
    doc = CanonicalDoc(
        doc_id=f"chk6_{RUN_ID}_preexisting_0",
        source_type="jira",
        external_id="PROJ-2",
        title="Pre-CP5 ticket",
        body="This doc was ingested before the store pipeline existed.",
        content_hash=compute_content_hash("Pre-CP5 ticket", "old body"),
    )
    # Simulate the historical gap directly: a `docs` row with NO matching
    # `docs_fts` row, exactly what every real doc ingested before this
    # wiring pass looks like.
    conn.execute(
        """INSERT INTO docs(id, source_type, external_id, title, body, content_hash, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,'t0','t0')""",
        (doc.doc_id, doc.source_type, doc.external_id, doc.title, "old body", doc.content_hash),
    )

    def _boom(stage, system, user):
        raise AssertionError("no thread_id on this doc -- LLM must not be called")

    report = run_store_pipeline(conn, index, hydra_store, _fake_embed, _boom, [doc])
    assert report.docs_stored == 1
    rowid = conn.execute("SELECT rowid FROM docs WHERE id=?", (doc.doc_id,)).fetchone()[0]
    fts_row = conn.execute("SELECT 1 FROM docs_fts WHERE rowid=?", (rowid,)).fetchone()
    assert fts_row is not None, "the doc's first-ever upsert must create its FTS row"
    hit = conn.execute(
        "SELECT d.id FROM docs_fts f JOIN docs d ON d.rowid=f.rowid WHERE docs_fts MATCH ?",
        ('"store pipeline"',),
    ).fetchall()
    assert any(r["id"] == doc.doc_id for r in hit), "the new body text must be searchable"
    # And the index must still be healthy for a second upsert right after.
    conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('integrity-check')")
    print("ok  6.8: a doc pre-dating the store pipeline gets its first FTS row without corrupting the index")


def check_llm_none_skips_distillation(conn, index, hydra_store) -> None:
    thread = "nokey"
    msgs = [_msg(thread, 0, "@x", "some message in a thread", minutes=0)]
    _, dirty = app._persist_canonical_docs(conn, msgs)
    thread_id = f"chk6_{RUN_ID}_{thread}"

    report = run_store_pipeline(conn, index, hydra_store, _fake_embed, None, dirty)
    assert report.docs_stored == 1
    assert report.threads_seen == 1
    assert report.threads_distilled == 0, "llm_call=None must skip distillation, not fail"
    state_row = conn.execute("SELECT 1 FROM thread_state WHERE thread_id=?", (thread_id,)).fetchone()
    assert state_row is None
    print("ok  6.6: llm_call=None stores raw docs but skips distillation entirely")


def check_distill_error_recorded_not_raised(conn, index, hydra_store) -> None:
    from joel.llm import LLMError

    thread = "boom"
    msgs = [
        _msg(thread, 0, "@x", "message one", minutes=0),
        _msg(thread, 1, "@y", "message two", minutes=1),
    ]
    _, dirty = app._persist_canonical_docs(conn, msgs)

    def raises(stage, system, user):
        raise LLMError("simulated 500")

    report = run_store_pipeline(conn, index, hydra_store, _fake_embed, raises, dirty)
    assert report.docs_stored == 2, "raw docs must still be stored even if distillation fails"
    assert report.threads_distilled == 0
    assert len(report.distill_errors) == 1
    print("ok  6.7: a distill failure is recorded in the report, not raised")


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

                check_raw_docs_stored_no_distill(conn, index, hydra_store)
                check_threaded_docs_trigger_distillation(conn, index, hydra_store)
                check_dirty_thread_reloads_whole_thread(conn, index, hydra_store)
                check_redistill_drops_stale_burst(conn, index, hydra_store)
                check_thread_flips_to_noise_removes_artifact(conn, index, hydra_store)
                check_pre_existing_raw_doc_gets_indexed(conn, index, hydra_store)
                check_llm_none_skips_distillation(conn, index, hydra_store)
                check_distill_error_recorded_not_raised(conn, index, hydra_store)

    print("\nIngest -> distill -> store wiring: all automated checks passed.")


if __name__ == "__main__":
    main()
