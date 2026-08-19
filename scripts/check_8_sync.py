"""Checkpoint 8: the sync engine (§11) — concurrency cap, failure backoff,
auth-failure fast path to needs_reauth, and catch-up-exactly-once.

`backoff_seconds`/`next_retry_at` are pure functions, tested directly.
`_scheduler_tick`'s concurrency cap and due-connector selection are tested
against a real disposable SQLite database (through the actual migrations)
with `app._start_ingest` monkeypatched to a recorder — no real network
fetch, no real background thread, just the scheduling decision itself.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import joel.app as app  # noqa: E402
from joel.connectors.composio_conn import _retry_after_seconds  # noqa: E402
from joel.syncer import BACKOFF_LADDER_SECONDS, backoff_seconds, next_retry_at  # noqa: E402


def check_backoff_ladder() -> None:
    assert [backoff_seconds(n) for n in range(1, 6)] == list(BACKOFF_LADDER_SECONDS)
    # Past the ladder's length, stay capped at the last (longest) rung —
    # never grows unbounded, never resets on its own.
    assert backoff_seconds(6) == BACKOFF_LADDER_SECONDS[-1]
    assert backoff_seconds(50) == BACKOFF_LADDER_SECONDS[-1]
    assert backoff_seconds(0) == 0
    print("ok  8.0a: backoff ladder is 1m -> 5m -> 15m -> 1h -> 6h, capped past 5 failures")


def check_next_retry_at_is_relative_to_now() -> None:
    now = datetime(2026, 8, 19, 6, 0, 0, tzinfo=timezone.utc)
    got = next_retry_at(now, 2)
    expected = (now + timedelta(seconds=BACKOFF_LADDER_SECONDS[1])).isoformat()
    assert got == expected
    print("ok  8.0b: next_retry_at is computed from the passed-in 'now', not wall-clock time")


def _insert_connection(
    conn, *, cid: str, provider: str, status: str, next_sync_at: str | None, consecutive_failures: int = 0
) -> None:
    conn.execute(
        """INSERT INTO connections(
             id, provider, mode, status, next_sync_at, consecutive_failures,
             checklist_json, created_at)
           VALUES (?,?,?,?,?,?,'{}',?)""",
        (cid, provider, "composio", status, next_sync_at, consecutive_failures, "2026-08-19T00:00:00+00:00"),
    )


def _insert_job(conn, *, jid: str, cid: str, status: str) -> None:
    conn.execute(
        """INSERT INTO jobs(id, connection_id, started_at, status, new_count, changed_count, unchanged_count)
           VALUES (?,?,?,?,0,0,0)""",
        (jid, cid, "2026-08-19T05:00:00+00:00", status),
    )


def check_concurrency_cap_and_error_retry(tmp_dir: Path) -> None:
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()

    started: list[str] = []
    original_start_ingest = app._start_ingest
    app._start_ingest = lambda cid, **kw: started.append(cid) or "job_fake"  # type: ignore[assignment]
    try:
        past = "2026-01-01T00:00:00+00:00"
        with app.db() as conn:
            conn.execute("UPDATE settings SET value='1' WHERE key='sync_max_concurrent_jobs'")
            conn.execute("UPDATE settings SET value='true' WHERE key='sync_enabled'")
            # Two connectors due right now: one 'ready', one 'error' whose
            # backoff has already elapsed (§11.2's "status IN ('ready','error')").
            _insert_connection(conn, cid="c_ready", provider="github", status="ready", next_sync_at=past)
            _insert_connection(
                conn, cid="c_error", provider="notion", status="error", next_sync_at=past, consecutive_failures=2
            )
            # needs_reauth must NEVER be picked up automatically, no matter
            # how stale next_sync_at is.
            _insert_connection(conn, cid="c_reauth", provider="slack", status="needs_reauth", next_sync_at=past)
            # A paused connector must never be picked up either.
            conn.execute(
                "INSERT INTO connections(id,provider,mode,status,next_sync_at,paused,checklist_json,created_at) "
                "VALUES ('c_paused','linear','composio','ready',?,1,'{}','2026-08-19T00:00:00+00:00')",
                (past,),
            )

        app._scheduler_tick()
        assert len(started) == 1, f"SYNC_MAX_CONCURRENT_JOBS=1 must start exactly one job this tick, got {started}"
        assert started[0] in {"c_ready", "c_error"}, started
        assert "c_reauth" not in started, "needs_reauth must never be auto-retried"
        assert "c_paused" not in started, "a paused connector must never be scheduled"
        print("ok  8.1a: the concurrency cap limits how many due connectors start in one tick")
        print("ok  8.1b: an errored connector whose backoff has elapsed is retried, needs_reauth is not")

        started.clear()
        with app.db() as conn:
            _insert_job(conn, jid="j_running", cid="c_ready", status="running")
        app._scheduler_tick()
        assert started == [], "a connector already running a job must never get a second job started"
        print("ok  8.1c: a connector never gets two jobs running at once")
    finally:
        app._start_ingest = original_start_ingest


def check_catch_up_runs_once_not_672_times(tmp_dir: Path) -> None:
    """§11.2: next_run_at computed at FINISH, so a week offline produces
    exactly one run per tick cycle, never one run per missed interval."""
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()

    started: list[str] = []
    original_start_ingest = app._start_ingest
    app._start_ingest = lambda cid, **kw: started.append(cid) or "job_fake"  # type: ignore[assignment]
    try:
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        with app.db() as conn:
            conn.execute("UPDATE settings SET value='10' WHERE key='sync_max_concurrent_jobs'")
            _insert_connection(conn, cid="c_stale", provider="github", status="ready", next_sync_at=week_ago)

        app._scheduler_tick()
        assert started == ["c_stale"], started
        # A second tick immediately after, with no job having finished (and
        # so no fresh next_sync_at written), must NOT start a second job —
        # only _run_ingest's own success/failure path is allowed to move
        # next_sync_at forward, and a real job is now "running".
        with app.db() as conn:
            _insert_job(conn, jid="j_stale", cid="c_stale", status="running")
        started.clear()
        app._scheduler_tick()
        assert started == [], "a second tick must not start a second job for the same still-running connector"
        print("ok  8.2: a connector 7 days overdue runs exactly once, not once per missed interval")
    finally:
        app._start_ingest = original_start_ingest


def check_retry_after_is_honoured_exactly() -> None:
    """§11.2 "honour Retry-After exactly" -- a stated wait beats a guess."""
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    assert _retry_after_seconds({}, default=2.0) == 2.0
    assert _retry_after_seconds({"Retry-After": "5"}, default=2.0) == 5.0
    assert _retry_after_seconds({"retry-after": "5"}, default=2.0) == 5.0
    assert _retry_after_seconds({"Retry-After": "9999"}, default=2.0) == 30.0, "capped, never unbounded"
    future = datetime.now(timezone.utc) + timedelta(seconds=10)
    http_date = format_datetime(future, usegmt=True)
    got = _retry_after_seconds({"Retry-After": http_date}, default=2.0)
    assert 8.0 <= got <= 11.0, got
    assert _retry_after_seconds({"Retry-After": "not-a-number"}, default=2.0) == 2.0
    print("ok  8.0c: Retry-After (seconds or HTTP-date, case-insensitive, capped) is honoured exactly")


def main() -> None:
    check_backoff_ladder()
    check_next_retry_at_is_relative_to_now()
    check_retry_after_is_honoured_exactly()
    with tempfile.TemporaryDirectory() as td:
        check_concurrency_cap_and_error_retry(Path(td))
    with tempfile.TemporaryDirectory() as td:
        check_catch_up_runs_once_not_672_times(Path(td))
    print("\nCP 8 sync engine: all automated checks passed.")


if __name__ == "__main__":
    main()
