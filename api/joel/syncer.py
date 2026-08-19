"""Background ingest scheduler — per-connector interval, not a human click."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone

# §11.2's ladder: 1m -> 5m -> 15m -> 1h -> 6h, capped. Index 0 is the delay
# after the FIRST failure (consecutive_failures==1); every failure past the
# ladder's length repeats the last (longest) rung rather than growing
# unbounded.
BACKOFF_LADDER_SECONDS = (60, 300, 900, 3600, 21600)


def backoff_seconds(consecutive_failures: int) -> int:
    """Seconds to wait before the next retry after `consecutive_failures`
    failures in a row. `consecutive_failures` is expected to already
    include the failure that just happened (i.e. call this AFTER
    incrementing the counter, not before)."""
    if consecutive_failures <= 0:
        return 0
    index = min(consecutive_failures - 1, len(BACKOFF_LADDER_SECONDS) - 1)
    return BACKOFF_LADDER_SECONDS[index]


def next_retry_at(now: datetime, consecutive_failures: int) -> str:
    return (now + timedelta(seconds=backoff_seconds(consecutive_failures))).isoformat()


def ingest_is_schedulable(
    provider: str, channel_ids: Sequence[str] | None = None
) -> bool:
    """Slack stays connected but must not sync until channels are picked."""
    if provider == "slack" and not channel_ids:
        return False
    return True


def start_scheduler(
    tick: Callable[[], None],
    *,
    interval_sec: float = 30,
) -> threading.Event:
    """Run `tick` every interval_sec until the returned event is set."""
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(interval_sec):
            try:
                tick()
            except Exception:
                continue

    thread = threading.Thread(target=loop, name="joel-ingest-scheduler", daemon=True)
    thread.start()
    return stop


def release_running_jobs(
    conn: sqlite3.Connection,
    *,
    now: str,
    connection_id: str | None = None,
    job_error: str | None = None,
) -> int:
    """Finish leftover in-process ingest jobs.

    Jobs are daemon threads in this process. SQLite rows outlive `--reload`
    and crash; a `running` row then 409s Sync Now and hides the connector
    from the scheduler. Same connection mapping as a user cancel: ready if
    a sync has finished before, otherwise pending_setup.
    """
    if connection_id is None:
        rows = conn.execute(
            """SELECT j.id AS job_id, j.connection_id, c.last_sync_at
               FROM jobs j JOIN connections c ON c.id = j.connection_id
               WHERE j.status='running'"""
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT j.id AS job_id, j.connection_id, c.last_sync_at
               FROM jobs j JOIN connections c ON c.id = j.connection_id
               WHERE j.status='running' AND j.connection_id=?""",
            (connection_id,),
        ).fetchall()
    for row in rows:
        conn.execute(
            """UPDATE jobs SET finished_at=?, status='cancelled', error=?
               WHERE id=?""",
            (now, job_error, row["job_id"]),
        )
        conn.execute(
            """UPDATE connections SET status=?, error=NULL, backfill_progress=NULL
               WHERE id=?""",
            (
                "ready" if row["last_sync_at"] else "pending_setup",
                row["connection_id"],
            ),
        )
    return len(rows)


__all__ = [
    "ingest_is_schedulable",
    "release_running_jobs",
    "start_scheduler",
    "backoff_seconds",
    "next_retry_at",
    "BACKOFF_LADDER_SECONDS",
]
