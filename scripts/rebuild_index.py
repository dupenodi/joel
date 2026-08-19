"""CP11.3 — rebuild FTS/vectors/graph for every doc already sitting in
`docs`. This exists because of a real gap the CP7 wiring pass surfaced: the
production `data/` corpus (930 real docs from ten connectors) was ingested
entirely through the pre-CP5 `_persist_canonical_docs` path and has NEVER
been run through `store_sql.upsert_docs` — `docs_fts` and `graph_written`
are both empty against it, so retrieval would find nothing to search no
matter how correct the lane code is.

This does NOT re-run distillation (§7) — it reindexes each existing `docs`
row as-is (raw ingest granularity), which covers the ~99% of the real
corpus that's singleton documents (PRs, tickets, emails) rather than
threaded conversations. The handful of real Slack threads still get their
raw messages indexed (searchable, just not distilled into artifacts); a
full re-distillation pass is a separate, LLM-cost-bearing operation, not
part of a mechanical index rebuild.

Usage: `python scripts/rebuild_index.py [--batch-size N] [--dry-run]`
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402

import joel.app as app  # noqa: E402
from joel.config import Settings  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.live_index import LiveIndex  # noqa: E402
from joel.store import HydraStore  # noqa: E402
from joel.store_sql import StoreDoc, upsert_docs  # noqa: E402


def _row_to_store_doc(row) -> StoreDoc:
    return StoreDoc(
        id=row["id"],
        title=row["title"] or "",
        body=row["body"] or "",
        source_type=row["source_type"],
        container=row["container"],
        granularity=row["granularity"] or "document",
        artifact_class=row["artifact_class"] or "document",
        validity=row["validity"] or "current",
        resolved=row["resolved"] or "na",
        ts=row["timestamp"],
        period=row["period"],
        url=row["url"],
        content_hash=row["content_hash"] or "",
        visibility=row["visibility"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true", help="count what would be indexed, write nothing")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    settings = Settings.from_env()

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(settings.embed_model)

    def embed(texts: list[str]):
        return model.encode(texts, normalize_embeddings=True)

    dim = getattr(model, "get_embedding_dimension", model.get_sentence_embedding_dimension)()

    with app.db() as conn:
        # The live scheduler may be writing to this same file concurrently
        # (a real sync running right now); app.db()'s connection has no
        # busy_timeout set, so an uncontended default write lock would
        # otherwise fail immediately instead of waiting its turn.
        conn.execute("PRAGMA busy_timeout=30000")
        rows = conn.execute(
            """SELECT id, title, body, source_type, container, granularity,
                      artifact_class, validity, resolved, timestamp, period,
                      url, content_hash, visibility
               FROM docs WHERE forgotten=0"""
        ).fetchall()
        total = len(rows)
        print(f"{total} non-forgotten docs in SQLite to reindex")
        if args.dry_run:
            already = {r["id"] for r in conn.execute("SELECT id FROM graph_written")}
            missing = sum(1 for r in rows if r["id"] not in already)
            print(f"{missing} of {total} are missing a graph_written entry (never indexed)")
            return

        index_path = app.DATA_DIR / "index" / "joel.npz"
        index = LiveIndex(index_path, dim=dim)

        with Hydra(settings) as hydra:
            hydra_store = HydraStore(hydra)
            done = 0
            t0 = time.time()
            for i in range(0, total, args.batch_size):
                batch = [_row_to_store_doc(r) for r in rows[i : i + args.batch_size]]
                report = upsert_docs(conn, index, hydra_store, batch, embed_fn=embed, now=app._now())
                done += len(batch)
                elapsed = time.time() - t0
                print(
                    f"  {done}/{total} sqlite={len(report.sqlite_upserted)} "
                    f"vectors={len(report.vectors_upserted)} "
                    f"graph_created={len(report.graph_created)} "
                    f"graph_updated={len(report.graph_updated)} "
                    f"graph_skipped={len(report.graph_skipped)} "
                    f"({elapsed:.1f}s elapsed)"
                )

    print(f"\nRebuild complete: {total} docs reindexed into FTS + vectors + graph.")


if __name__ == "__main__":
    main()
