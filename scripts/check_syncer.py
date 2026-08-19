"""In-process jobs cannot outlive the worker — leftover `running` rows
must release the same way a user cancel does."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import joel.app as app  # noqa: E402
from joel.syncer import release_running_jobs  # noqa: E402


def _insert_connection(conn, *, cid: str, provider: str, status: str, last_sync_at: str | None) -> None:
    conn.execute(
        """INSERT INTO connections(
             id, provider, mode, status, last_sync_at, checklist_json, created_at)
           VALUES (?,?,?,?,?,'{}',?)""",
        (cid, provider, "composio", status, last_sync_at, "2026-08-19T00:00:00+00:00"),
    )


def _insert_job(conn, *, jid: str, cid: str, status: str) -> None:
    conn.execute(
        """INSERT INTO jobs(id, connection_id, started_at, status,
             new_count, changed_count, unchanged_count)
           VALUES (?,?,?,?,0,0,0)""",
        (jid, cid, "2026-08-19T05:00:00+00:00", status),
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app.DATA_DIR = tmp
        app.DB_PATH = tmp / "index" / "joel.db"
        app.init_db()
        now = "2026-08-19T06:00:00+00:00"
        with app.db() as conn:
            _insert_connection(
                conn,
                cid="conn_gh",
                provider="github",
                status="backfilling",
                last_sync_at=None,
            )
            _insert_connection(
                conn,
                cid="conn_slack",
                provider="slack",
                status="syncing",
                last_sync_at="2026-08-19T04:00:00+00:00",
            )
            _insert_connection(
                conn,
                cid="conn_ok",
                provider="notion",
                status="ready",
                last_sync_at="2026-08-19T04:00:00+00:00",
            )
            _insert_job(conn, jid="job_gh", cid="conn_gh", status="running")
            _insert_job(conn, jid="job_slack", cid="conn_slack", status="running")
            conn.execute(
                """INSERT INTO jobs(id, connection_id, started_at, finished_at, status,
                     new_count, changed_count, unchanged_count)
                   VALUES (?,?,?,?, 'ok', 1, 0, 0)""",
                (
                    "job_old",
                    "conn_ok",
                    "2026-08-19T03:00:00+00:00",
                    "2026-08-19T03:01:00+00:00",
                ),
            )

            n = release_running_jobs(conn, now=now, job_error="worker restarted")
            assert n == 2, n

            gh = conn.execute("SELECT status FROM connections WHERE id='conn_gh'").fetchone()
            slack = conn.execute("SELECT status FROM connections WHERE id='conn_slack'").fetchone()
            notion = conn.execute("SELECT status FROM connections WHERE id='conn_ok'").fetchone()
            assert gh["status"] == "pending_setup", gh["status"]
            assert slack["status"] == "ready", slack["status"]
            assert notion["status"] == "ready", notion["status"]

            gh_job = conn.execute("SELECT status, error, finished_at FROM jobs WHERE id='job_gh'").fetchone()
            old_job = conn.execute("SELECT status FROM jobs WHERE id='job_old'").fetchone()
            assert gh_job["status"] == "cancelled"
            assert gh_job["error"] == "worker restarted"
            assert gh_job["finished_at"] == now
            assert old_job["status"] == "ok"

            n2 = release_running_jobs(conn, now=now, connection_id="conn_gh")
            assert n2 == 0

    print("ok  syncer: leftover running jobs release on worker restart")


if __name__ == "__main__":
    main()
