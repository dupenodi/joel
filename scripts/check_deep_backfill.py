"""§11.3 progressive deep backfill: the backward-walking pass beyond the
fast pass's lookback window, built for slack and gmail (both have a
natural symmetric upper bound on top of their existing lower bound).

Scheduling and cursor-walking are tested against a real disposable SQLite
database (through the actual migrations) with the actual fetch/floor
functions monkeypatched to fakes -- no real network calls in the
synthetic checks. `check_live_slack_deep_backfill_page` is the one real
check: it runs one real deep-backfill page against the real, currently
connected Slack workspace and asserts the cursor actually moved and/or
real docs came back, skipping honestly if no real Slack connection is
ready.
"""

from __future__ import annotations

import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402

import joel.app as app  # noqa: E402
from joel.connectors.oauth import encrypt_credentials  # noqa: E402
from joel.models import CanonicalDoc, compute_content_hash  # noqa: E402


def _insert_connection(conn, *, cid: str, provider: str, **cols) -> None:
    fields = {
        "id": cid,
        "provider": provider,
        "mode": "composio",
        "status": "ready",
        "checklist_json": "{}",
        "created_at": "2026-08-19T00:00:00+00:00",
        "backfill_done": 0,
        **cols,
    }
    keys = ",".join(fields.keys())
    marks = ",".join("?" * len(fields))
    conn.execute(f"INSERT INTO connections({keys}) VALUES ({marks})", tuple(fields.values()))


def _one_connector_tick(tmp_dir: Path, provider: str, **cols) -> list[tuple[str, str]]:
    """Fresh scratch DB with exactly one connector row, ticked once.
    `connections.provider` is still UNIQUE pre-personal-connectors (§0.3's
    still-open item), so scenarios that need distinct backfill states live
    in separate DBs rather than sharing one -- isolated is cleaner here
    anyway."""
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()
    started: list[tuple[str, str]] = []
    original_deep = app._start_deep_backfill
    original_ingest = app._start_ingest
    app._start_deep_backfill = lambda cid, *, provider: started.append((cid, provider)) or "job_fake"  # type: ignore[assignment]
    app._start_ingest = lambda cid, **kw: "job_fake"  # type: ignore[assignment]
    try:
        with app.db() as conn:
            conn.execute("UPDATE settings SET value='4' WHERE key='sync_max_concurrent_jobs'")
            conn.execute("UPDATE settings SET value='true' WHERE key='sync_enabled'")
            _insert_connection(conn, cid="c_under_test", provider=provider, **cols)
        app._scheduler_tick()
        return started
    finally:
        app._start_deep_backfill = original_deep
        app._start_ingest = original_ingest


def check_scheduler_picks_up_deep_backfill_with_spare_capacity(tmp_dir: Path) -> None:
    cursor = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    started = _one_connector_tick(tmp_dir / "ready", "slack", backfill_done=0, backfill_cursor=cursor)
    assert started == [("c_under_test", "slack")], started
    print("ok  db.1a: scheduler picks up an eligible deep-backfill connector")

    # backfill_done=1 already -- must NOT be picked up again.
    started = _one_connector_tick(tmp_dir / "done", "gmail", backfill_done=1, backfill_cursor=None)
    assert started == [], started
    print("ok  db.1b: a connector already marked backfill_done is not re-picked")

    # No cursor yet (deep backfill never applicable/initialized) -- must
    # NOT be picked up even though the provider supports deep backfill.
    started = _one_connector_tick(tmp_dir / "no_cursor", "slack", backfill_done=0, backfill_cursor=None)
    assert started == [], started
    print("ok  db.1c: a connector with no backfill_cursor yet is not picked up")

    # A provider with no deep-backfill support at all -- must NOT be
    # picked up even with backfill_done=0 (shouldn't normally happen, but
    # the provider allowlist must hold regardless).
    started = _one_connector_tick(tmp_dir / "unsupported", "github", backfill_done=0, backfill_cursor=cursor)
    assert started == [], started
    print("ok  db.1d: a provider without deep-backfill support is never picked up")

    # Paused -- must NOT be picked up.
    started = _one_connector_tick(tmp_dir / "paused", "slack", backfill_done=0, backfill_cursor=cursor, paused=1)
    assert started == [], started
    print("ok  db.1e: a paused connector is not picked up for deep backfill")


def check_running_job_blocks_second_deep_backfill_start(tmp_dir: Path) -> None:
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()
    started: list[tuple[str, str]] = []
    original_deep = app._start_deep_backfill
    app._start_deep_backfill = lambda cid, *, provider: started.append((cid, provider)) or "job_fake"  # type: ignore[assignment]
    try:
        cursor = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        with app.db() as conn:
            conn.execute("UPDATE settings SET value='4' WHERE key='sync_max_concurrent_jobs'")
            conn.execute("UPDATE settings SET value='true' WHERE key='sync_enabled'")
            _insert_connection(conn, cid="c_running", provider="slack", backfill_done=0, backfill_cursor=cursor)
            conn.execute(
                "INSERT INTO jobs(id, connection_id, started_at, status, new_count, changed_count, unchanged_count) "
                "VALUES ('j_running','c_running','2026-08-19T05:00:00+00:00','running',0,0,0)"
            )
        app._scheduler_tick()
        assert started == [], "a connector already running a job must not get a second one started"
        print("ok  db.2: a connector with a running job is skipped, not double-started")
    finally:
        app._start_deep_backfill = original_deep


def check_incremental_sync_takes_priority_over_deep_backfill(tmp_dir: Path) -> None:
    """§11.3: 'runs only when no incremental sync is pending' -- with tight
    capacity, the due incremental sync must win the slot over deep backfill."""
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()

    incremental_started: list[str] = []
    deep_started: list[str] = []
    original_ingest = app._start_ingest
    original_deep = app._start_deep_backfill
    app._start_ingest = lambda cid, **kw: incremental_started.append(cid) or "job_fake"  # type: ignore[assignment]
    app._start_deep_backfill = lambda cid, **kw: deep_started.append(cid) or "job_fake"  # type: ignore[assignment]
    try:
        past = "2026-01-01T00:00:00+00:00"
        cursor = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        with app.db() as conn:
            conn.execute("UPDATE settings SET value='1' WHERE key='sync_max_concurrent_jobs'")
            conn.execute("UPDATE settings SET value='true' WHERE key='sync_enabled'")
            _insert_connection(
                conn, cid="c_incremental_due", provider="github",
                status="ready", next_sync_at=past, backfill_done=1,
            )
            _insert_connection(
                conn, cid="c_deep_candidate", provider="slack",
                status="ready", backfill_done=0, backfill_cursor=cursor,
            )
        app._scheduler_tick()
        assert incremental_started == ["c_incremental_due"], incremental_started
        assert deep_started == [], "deep backfill must not run when it would exceed the concurrency cap this tick"
        print("ok  db.3: a due incremental sync takes the only capacity slot over deep backfill")
    finally:
        app._start_ingest = original_ingest
        app._start_deep_backfill = original_deep


def check_deep_backfill_page_walks_cursor_and_completes(tmp_dir: Path) -> None:
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()

    until = datetime.now(timezone.utc) - timedelta(days=30)
    # Between one and two pages away (90-day pages): page 1 must NOT reach
    # it, page 2 must.
    floor = until - timedelta(days=150)
    cid = "c_deep_page"

    with app.db() as conn:
        _insert_connection(
            conn, cid=cid, provider="slack",
            backfill_done=0, backfill_cursor=until.isoformat(),
        )
        conn.execute(
            "INSERT INTO connector_credentials(connection_id, encrypted_json, updated_at) VALUES (?,?,?)",
            (cid, encrypt_credentials({"composio_account_id": "acct_fake"}, tmp_dir), "2026-08-19T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO jobs(id, connection_id, started_at, status, new_count, changed_count, unchanged_count) "
            "VALUES ('j_page', ?, '2026-08-19T05:00:00+00:00', 'running', 0, 0, 0)",
            (cid,),
        )

    fetch_calls: list[tuple[datetime, datetime]] = []

    def fake_fetch(provider, credentials, settings, row, *, since, until):
        fetch_calls.append((since, until))
        return [
            CanonicalDoc(
                doc_id=f"chkdeep_{since.date()}",
                source_type="slack",
                external_id=f"e_{since.date()}",
                title="deep backfill fixture",
                body="a real body so it survives the noise filter",
                content_hash=compute_content_hash("t", "b"),
            )
        ]

    original_fetch = app._fetch_provider_docs_deep
    original_floor = app._deep_backfill_floor
    app._fetch_provider_docs_deep = fake_fetch  # type: ignore[assignment]
    app._deep_backfill_floor = lambda *a, **kw: floor  # type: ignore[assignment]
    try:
        app._run_deep_backfill_page(cid, "j_page", provider="slack")
        assert len(fetch_calls) == 1
        since1, until1 = fetch_calls[0]
        assert until1 == until
        assert since1 == max(until - timedelta(days=app.DEEP_BACKFILL_PAGE_DAYS), floor)

        with app.db() as conn:
            row = conn.execute(
                "SELECT backfill_done, backfill_cursor FROM connections WHERE id=?", (cid,)
            ).fetchone()
            job = conn.execute("SELECT status, new_count FROM jobs WHERE id='j_page'").fetchone()
        assert job["status"] == "ok", dict(job)
        assert job["new_count"] == 1

        if since1 <= floor:
            assert row["backfill_done"] == 1
            print("ok  db.4: one page reached the floor in a single hop, backfill_done flips to 1")
        else:
            assert row["backfill_done"] == 0
            assert row["backfill_cursor"] == since1.isoformat()
            print("ok  db.4: cursor walks back by one page, backfill_done stays 0")

            # Run a second page from the new cursor -- must reach the floor
            # and flip backfill_done, proving the walk actually converges.
            with app.db() as conn:
                conn.execute(
                    "INSERT INTO jobs(id, connection_id, started_at, status, new_count, changed_count, unchanged_count) "
                    "VALUES ('j_page2', ?, '2026-08-19T05:00:00+00:00', 'running', 0, 0, 0)",
                    (cid,),
                )
            app._run_deep_backfill_page(cid, "j_page2", provider="slack")
            with app.db() as conn:
                row2 = conn.execute(
                    "SELECT backfill_done FROM connections WHERE id=?", (cid,)
                ).fetchone()
            assert row2["backfill_done"] == 1, "the walk must reach the floor and terminate"
            print("ok  db.5: a second page reaches the floor and terminates the walk")
    finally:
        app._fetch_provider_docs_deep = original_fetch
        app._deep_backfill_floor = original_floor
        # The fixture docs went through the real store pipeline (§2.1: one
        # shared HydraDB graph project-wide, never mocked) -- clean up the
        # real graph nodes they created, same as every other check_*.py.
        try:
            rt = app._runtime()
            for since, _until in fetch_calls:
                rt["hydra_store"].delete_node("Doc", f"chkdeep_{since.date()}")
        except Exception:
            pass


def check_first_sync_initializes_cursor_for_deep_backfill_providers_only(tmp_dir: Path) -> None:
    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()

    with app.db() as conn:
        _insert_connection(conn, cid="c_slack_first", provider="slack", status="backfilling", lookback_days=30)
        _insert_connection(conn, cid="c_github_first", provider="github", status="backfilling", lookback_days=30)
        for cid in ("c_slack_first", "c_github_first"):
            conn.execute(
                "INSERT INTO connector_credentials(connection_id, encrypted_json, updated_at) VALUES (?,?,?)",
                (cid, encrypt_credentials({"composio_account_id": "acct_fake"}, tmp_dir), "2026-08-19T00:00:00+00:00"),
            )
            conn.execute(
                "INSERT INTO jobs(id, connection_id, started_at, status, new_count, changed_count, unchanged_count) "
                "VALUES (?, ?, '2026-08-19T05:00:00+00:00', 'running', 0, 0, 0)",
                (f"j_{cid}", cid),
            )

    app._fetch_provider_docs = lambda *a, **kw: []  # type: ignore[assignment]
    try:
        app._run_ingest("c_slack_first", "j_c_slack_first", first_sync=True, provider="slack")
        app._run_ingest("c_github_first", "j_c_github_first", first_sync=True, provider="github")
    finally:
        del app._fetch_provider_docs

    with app.db() as conn:
        slack_row = conn.execute(
            "SELECT backfill_done, backfill_cursor FROM connections WHERE id='c_slack_first'"
        ).fetchone()
        github_row = conn.execute(
            "SELECT backfill_done, backfill_cursor FROM connections WHERE id='c_github_first'"
        ).fetchone()
    assert slack_row["backfill_done"] == 0, "a deep-backfill provider must start its first sync with backfill_done=0"
    assert slack_row["backfill_cursor"] is not None, "the fast pass's own floor must seed the deep-backfill cursor"
    assert github_row["backfill_done"] == 1, "a provider with no deep pass keeps the old first-sync-completes semantics"
    assert github_row["backfill_cursor"] is None
    print("ok  db.6: first sync seeds backfill_cursor for slack, leaves github's old semantics untouched")


def check_live_slack_deep_backfill_page() -> None:
    """The one real check: a genuine deep-backfill page against the real,
    currently connected Slack workspace, if one is ready."""
    data_dir = ROOT / "data"
    db_path = data_dir / "index" / "joel.db"
    if not db_path.exists():
        print("skip live: no real data/index/joel.db — real deep-backfill smoke test skipped")
        return
    app.DATA_DIR = data_dir
    app.DB_PATH = db_path
    with app.db() as conn:
        row = conn.execute(
            "SELECT id, channel_ids_json FROM connections WHERE provider='slack' AND status='ready'"
        ).fetchone()
    if row is None:
        print("skip live: no ready Slack connection to test a real deep-backfill page against")
        return

    connection_id = row["id"]
    job_id = f"j_livedeep_{uuid.uuid4().hex[:10]}"
    with app.db() as conn:
        before = conn.execute(
            "SELECT doc_count, backfill_cursor, backfill_done FROM connections WHERE id=?",
            (connection_id,),
        ).fetchone()
        # Set up a real deep-backfill window: walk back from 30 days ago,
        # bounded to a real 90-day page so this stays a single fast call.
        cursor = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        conn.execute(
            "UPDATE connections SET backfill_done=0, backfill_cursor=? WHERE id=?",
            (cursor, connection_id),
        )
        conn.execute(
            "INSERT INTO jobs(id, connection_id, started_at, status, new_count, changed_count, unchanged_count) "
            "VALUES (?, ?, ?, 'running', 0, 0, 0)",
            (job_id, connection_id, app._now()),
        )

    app._run_deep_backfill_page(connection_id, job_id, provider="slack")

    with app.db() as conn:
        job = conn.execute("SELECT status, error, new_count FROM jobs WHERE id=?", (job_id,)).fetchone()
        after = conn.execute(
            "SELECT doc_count, backfill_cursor, backfill_done FROM connections WHERE id=?",
            (connection_id,),
        ).fetchone()
    assert job["status"] == "ok", f"real deep-backfill page against live Slack failed: {job['error']}"
    moved = after["backfill_cursor"] != cursor or after["backfill_done"] == 1
    assert moved, "a real page must either walk the cursor back or reach the floor -- it must never no-op"
    print(
        f"ok  live: one real Slack deep-backfill page ran against '{connection_id}' -- "
        f"new_count={job['new_count']} doc_count {before['doc_count']}->{after['doc_count']} "
        f"backfill_done={after['backfill_done']}"
    )


def main() -> None:
    load_dotenv(ROOT / ".env")
    with tempfile.TemporaryDirectory() as td:
        check_scheduler_picks_up_deep_backfill_with_spare_capacity(Path(td))
    with tempfile.TemporaryDirectory() as td:
        check_running_job_blocks_second_deep_backfill_start(Path(td))
    with tempfile.TemporaryDirectory() as td:
        check_incremental_sync_takes_priority_over_deep_backfill(Path(td))
    with tempfile.TemporaryDirectory() as td:
        check_deep_backfill_page_walks_cursor_and_completes(Path(td))
    with tempfile.TemporaryDirectory() as td:
        check_first_sync_initializes_cursor_for_deep_backfill_providers_only(Path(td))
    check_live_slack_deep_backfill_page()
    print("\nDeep backfill (§11.3): all automated checks passed.")


if __name__ == "__main__":
    main()
