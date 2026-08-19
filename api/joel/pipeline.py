"""Wires ingest → distill → store together — the seam CP3, CP4, and CP5 each
verified independently but never called into each other. `_run_ingest`
(`app.py`) calls `run_store_pipeline` once per sync, after new/changed docs
are already committed to the plain `docs` row §6 always wrote:

    fetch (§6, CP3) → docs table  →  run_store_pipeline (this module)
                                        ├─ upsert every new/changed doc as-is (§8, CP5)
                                        └─ for each thread touched this sync (dirty, §7.5):
                                             re-group bursts, one distill call (§7, CP4),
                                             diff against thread_state, upsert kept
                                             bursts + artifact, remove dropped bursts

Ontology (CP6) is not built yet, so that's as far as this goes — a dirty
thread's artifact lands in all three stores with no entities/edges beyond
the structural :DISTILLED_FROM ones `upsert_docs` already writes.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from joel.distill.artifact import DistillFailure, diff_kept_set, distill_thread
from joel.distill.bursts import group_bursts
from joel.distill.df_index import DocFrequencyIndex
from joel.distill.state import load_prior_kept, save_thread_state
from joel.live_index import LiveIndex
from joel.llm import LLMCallFn
from joel.models import CanonicalDoc
from joel.store import HydraStore
from joel.store_sql import EmbedFn, from_burst, from_canonical_doc, from_thread_artifact, remove_docs, upsert_docs


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineReport:
    docs_stored: int = 0
    threads_seen: int = 0
    threads_distilled: int = 0
    artifacts_written: int = 0
    bursts_kept: int = 0
    bursts_dropped: int = 0
    distill_errors: list[str] = field(default_factory=list)


def _row_to_canonical_doc(row: sqlite3.Row) -> CanonicalDoc:
    ts = datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None
    return CanonicalDoc(
        doc_id=row["id"],
        source_type=row["source_type"],
        external_id=row["external_id"],
        title=row["title"],
        body=row["body"],
        extra=json.loads(row["extra_json"] or "{}"),
        author_raw=row["author_raw"],
        container=row["container"],
        url=row["url"],
        timestamp=ts,
        thread_id=row["thread_id"],
        parent_id=row["parent_id"],
        content_hash=row["content_hash"],
        visibility=row["visibility"],
    )


def load_thread_messages(conn: sqlite3.Connection, thread_id: str) -> list[CanonicalDoc]:
    """The WHOLE thread, not just this sync's new/changed messages — §7.5's
    own rule ("re-distill the whole thread, not the delta") means every
    dirty thread needs its full history reconstructed from `docs`, which
    already has everything `group_bursts`/`distill_thread` need."""
    rows = conn.execute(
        "SELECT * FROM docs WHERE thread_id=? AND forgotten=0 ORDER BY timestamp",
        (thread_id,),
    ).fetchall()
    return [_row_to_canonical_doc(r) for r in rows]


def _prior_artifact_id(conn: sqlite3.Connection, thread_id: str) -> str | None:
    row = conn.execute(
        "SELECT artifact_id FROM thread_state WHERE thread_id=?", (thread_id,)
    ).fetchone()
    return row["artifact_id"] if row and row["artifact_id"] else None


def _distill_and_store_thread(
    conn: sqlite3.Connection,
    index: LiveIndex,
    hydra_store: HydraStore,
    embed_fn: EmbedFn,
    llm_call: LLMCallFn,
    thread_id: str,
    df: DocFrequencyIndex,
    report: PipelineReport,
) -> None:
    messages = load_thread_messages(conn, thread_id)
    if not messages:
        return
    bursts = group_bursts(messages)
    prior_ids, prior_text = load_prior_kept(conn, thread_id)

    try:
        artifact, resolved_bursts = distill_thread(messages, bursts, llm_call=llm_call, df=df)
    except DistillFailure as exc:
        # §7.5's own rule: one repair retry already happened inside
        # distill_thread; a second failure leaves the PREVIOUS artifact (if
        # any) in place rather than deleting good state over a bad call.
        report.distill_errors.append(str(exc))
        return

    if artifact is None:
        # Thread now classifies as noise/low-confidence (it may not have
        # started that way — an edit can turn a real thread into chit-chat).
        # Drop whatever was previously kept, INCLUDING the prior artifact
        # itself (kept_bursts_json alone doesn't cover it), and record empty
        # state so the next re-distill's diff starts clean.
        prior_artifact_id = _prior_artifact_id(conn, thread_id)
        remove_docs(conn, index, hydra_store, [*prior_ids, *([prior_artifact_id] if prior_artifact_id else [])])
        save_thread_state(
            conn,
            thread_id=thread_id,
            source_type=messages[0].source_type,
            artifact_id="",
            kept_bursts={},
            distilled_at=_now_iso(),
        )
        report.threads_distilled += 1
        return

    kept = [b for b in resolved_bursts if b.kept]
    diff = diff_kept_set(kept, prior_ids, prior_text)

    inherited = messages[0].visibility
    burst_docs = [
        from_burst(
            b,
            source_type=messages[0].source_type,
            container=messages[0].container,
            thread_question=artifact.question,
            visibility=inherited,
        )
        for b in kept
    ]
    artifact_doc = from_thread_artifact(
        artifact,
        kept_burst_ids=[bd.id for bd in burst_docs],
        visibility=inherited,
    )

    to_upsert_ids = set(diff.to_upsert)
    changed_burst_docs = [bd for bd in burst_docs if bd.id in to_upsert_ids]
    # The artifact's own content_hash covers "did anything about this thread
    # change" -- upsert_docs skips it in the graph lane for free if not, and
    # SQLite/FTS/vectors are cheap enough to just re-write every dirty-thread
    # pass rather than diffing per-field.
    upsert_docs(conn, index, hydra_store, [*changed_burst_docs, artifact_doc], embed_fn=embed_fn, now=_now_iso())
    remove_docs(conn, index, hydra_store, diff.to_delete)

    save_thread_state(
        conn,
        thread_id=thread_id,
        source_type=messages[0].source_type,
        artifact_id=artifact.artifact_id,
        kept_bursts={bd.id: bd.body for bd in burst_docs},
        distilled_at=_now_iso(),
    )
    report.threads_distilled += 1
    report.artifacts_written += 1
    report.bursts_kept += len(kept)
    report.bursts_dropped += len(diff.to_delete)


def run_store_pipeline(
    conn: sqlite3.Connection,
    index: LiveIndex,
    hydra_store: HydraStore,
    embed_fn: EmbedFn,
    llm_call: LLMCallFn | None,
    docs: list[CanonicalDoc],
) -> PipelineReport:
    """Called once per sync with this job's new/changed docs (not the whole
    corpus). `llm_call=None` skips distillation entirely (no LLM key
    configured yet) but still stores every raw doc -- matching §14.6's
    "ingestion pauses [the LLM-dependent part] rather than burning retries."
    """
    report = PipelineReport()
    if not docs:
        return report

    store_docs = [from_canonical_doc(d) for d in docs]
    upsert_docs(conn, index, hydra_store, store_docs, embed_fn=embed_fn, now=_now_iso())
    report.docs_stored = len(store_docs)

    thread_ids = sorted({d.thread_id for d in docs if d.thread_id})
    report.threads_seen = len(thread_ids)
    if thread_ids and llm_call is not None:
        # Freshly built per pipeline run rather than persisted+incremental --
        # correct (no double-counting across syncs) at the cost of a full
        # corpus scan every run, which is fine at hundreds-to-thousands of
        # docs. Revisit (§7.3's df.json) if that scan ever shows up as slow.
        df = DocFrequencyIndex()
        for row in conn.execute("SELECT body FROM docs WHERE forgotten=0"):
            df.add_document(row["body"])
        for thread_id in thread_ids:
            _distill_and_store_thread(conn, index, hydra_store, embed_fn, llm_call, thread_id, df, report)

    return report


__all__ = ["PipelineReport", "run_store_pipeline", "load_thread_messages"]
