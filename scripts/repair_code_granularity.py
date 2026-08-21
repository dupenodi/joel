"""Backfill `granularity` for GitHub code chunks stored before the manifest
set it.

`GITHUB_CODE` in `joel/adapters/manifests.py` declares `granularity="code"`,
but rows ingested before that declaration landed carry `document`. Nothing
re-writes them: `upsert_docs` only updates a row whose `content_hash`
changed, and an unchanged blob keeps its stale granularity forever.

The consequence is not cosmetic. Every consumer that asks "is this evidence
source code?" -- the graph overview's quality filter, retrieval's lane
weighting -- reads `granularity`, so 161 code chunks were being treated as
prose documents and their extracted "ontology" (identifier names like
`thread_id` and `summary`, related by `OWNS`) outranked real claims.

Identification is by the `code_` id prefix the same manifest sets, not by
guessing from the title, so this only ever touches rows that provably came
from the code path. Idempotent; safe to re-run.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

DATA_DIR = Path(os.getenv("JOEL_DATA", "data"))


def repair(conn: sqlite3.Connection, *, apply: bool) -> int:
    rows = conn.execute(
        """SELECT id, granularity FROM docs
           WHERE source_type='github'
             AND id LIKE 'github\\_\\_code\\_%' ESCAPE '\\'
             AND granularity <> 'code'"""
    ).fetchall()
    if not rows:
        print("ok  no mislabelled code chunks")
        return 0
    print(f"found {len(rows)} code chunks stored with the wrong granularity")
    for row in rows[:5]:
        print(f"   {row['id']}  {row['granularity']} -> code")
    if len(rows) > 5:
        print(f"   ... and {len(rows) - 5} more")
    if not apply:
        print("dry run; pass --apply to write")
        return len(rows)
    conn.execute(
        """UPDATE docs SET granularity='code'
           WHERE source_type='github'
             AND id LIKE 'github\\_\\_code\\_%' ESCAPE '\\'
             AND granularity <> 'code'"""
    )
    conn.commit()
    print(f"ok  repaired {len(rows)} rows")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db_path = DATA_DIR / "index" / "joel.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        repair(conn, apply=args.apply)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
