"""SQLite persistence for §7.5's re-distillation diff — remembers the last
kept burst-id → text map per thread, so `diff_kept_set()` (artifact.py) has
something to compare a re-distilled thread against. Deliberately dumb: one
row per thread, last-write-wins, no history.
"""

from __future__ import annotations

import json
import sqlite3


def load_prior_kept(conn: sqlite3.Connection, thread_id: str) -> tuple[set[str], dict[str, str]]:
    """Returns `(prior_kept_ids, prior_text_by_id)` for `diff_kept_set()`.
    Empty for a thread distilled for the first time."""
    row = conn.execute(
        "SELECT kept_bursts_json FROM thread_state WHERE thread_id=?", (thread_id,)
    ).fetchone()
    if row is None:
        return set(), {}
    kept_bursts: dict[str, str] = json.loads(row[0])
    return set(kept_bursts), kept_bursts


def save_thread_state(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    source_type: str,
    artifact_id: str,
    kept_bursts: dict[str, str],
    distilled_at: str,
) -> None:
    """Overwrite this thread's state with the just-computed kept-set. Call
    only after the corresponding store writes (§7.4) have succeeded — this
    row is the "what we last told the store" ledger, not a queue."""
    conn.execute(
        """
        INSERT INTO thread_state(thread_id, source_type, artifact_id, kept_bursts_json, last_distilled_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET
          artifact_id=excluded.artifact_id,
          kept_bursts_json=excluded.kept_bursts_json,
          last_distilled_at=excluded.last_distilled_at
        """,
        (thread_id, source_type, artifact_id, json.dumps(kept_bursts), distilled_at),
    )


__all__ = ["load_prior_kept", "save_thread_state"]
