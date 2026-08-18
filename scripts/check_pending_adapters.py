"""Check pending adapter connections and optionally trigger real syncs.

Usage:
  python3 scripts/check_pending_adapters.py
  python3 scripts/check_pending_adapters.py --sync
  python3 scripts/check_pending_adapters.py --providers linear confluence hubspot

This script is meant for the "connect in UI, verify in terminal" loop.
It reports which allowlisted adapters are still unconnected, which ones need
reauth, and for connected ones can trigger `/sync` and wait for the job result.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "index" / "joel.db"
API_BASE = "http://localhost:8000"
ALLOWLIST = [
    "slack",
    "github",
    "gmail",
    "linear",
    "jira",
    "notion",
    "confluence",
    "googledrive",
    "hubspot",
    "fireflies",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--providers",
        nargs="*",
        default=[],
        help="Provider ids to check. Omit with --all to check every allowlisted adapter.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all allowlisted providers (default without --all: likely-pending subset).",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Trigger sync-now for connected adapters that are ready or in error.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Seconds to wait for each sync job (default 600; GitHub/Gmail can take several minutes).",
    )
    parser.add_argument(
        "--api-base",
        default=API_BASE,
        help="Joel API base URL.",
    )
    return parser.parse_args()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def latest_job(conn: sqlite3.Connection, connection_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """select id, status, started_at, finished_at, new_count, changed_count,
                  unchanged_count, error
           from jobs where connection_id=?
           order by started_at desc limit 1""",
        (connection_id,),
    ).fetchone()


def docs_count(conn: sqlite3.Connection, provider: str) -> int:
    row = conn.execute(
        "select count(*) as c from docs where source_type=?", (provider,)
    ).fetchone()
    return int(row["c"]) if row else 0


def trigger_sync(api_base: str, connection_id: str) -> str:
    url = f"{api_base.rstrip('/')}/api/connectors/{connection_id}/sync"
    req = urllib.request.Request(
        url,
        method="POST",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode())
    return str(payload["job_id"])


def wait_job(conn: sqlite3.Connection, job_id: str, timeout_sec: int = 120) -> sqlite3.Row | None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        row = conn.execute(
            """select id, status, started_at, finished_at, new_count, changed_count,
                      unchanged_count, error
               from jobs where id=?""",
            (job_id,),
        ).fetchone()
        if row and row["status"] != "running":
            return row
        time.sleep(1)
    return None


def main() -> int:
    args = parse_args()
    if args.all:
        providers = list(ALLOWLIST)
    elif args.providers:
        providers = args.providers
    else:
        providers = [
            p
            for p in ALLOWLIST
            if p not in {"slack", "github", "gmail", "notion", "googledrive", "jira"}
        ]
    conn = db()
    rows = {
        row["provider"]: row
        for row in conn.execute(
            """select id, provider, status, error, last_sync_at, next_sync_at
               from connections"""
        ).fetchall()
    }
    print("providers:", ", ".join(providers))
    for provider in providers:
        row = rows.get(provider)
        print(f"\n== {provider} ==")
        if row is None:
            print("state: not connected")
            print("next: connect this provider in the UI, then rerun this script.")
            continue
        print(
            "connection:",
            {
                "id": row["id"],
                "status": row["status"],
                "error": row["error"],
                "last_sync_at": row["last_sync_at"],
                "next_sync_at": row["next_sync_at"],
            },
        )
        print("docs:", docs_count(conn, provider))
        prev = latest_job(conn, row["id"])
        if prev is not None:
            print("latest_job:", dict(prev))
        if not args.sync:
            continue
        if row["status"] == "needs_reauth":
            print("skip sync: needs_reauth, reconnect in UI first.")
            continue
        try:
            job_id = trigger_sync(args.api_base, row["id"])
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            print("sync trigger failed:", exc.code, body[:500])
            continue
        print("triggered:", job_id)
        job = wait_job(conn, job_id, timeout_sec=args.timeout)
        if job is None:
            print("job did not finish in time")
            continue
        print("job_result:", dict(job))
        print("docs_after:", docs_count(conn, provider))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
