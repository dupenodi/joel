"""§14.4/CP11.3 — rebuild `docs` + FTS + vectors + graph from the canonical
JSONL files (`data/canonical/*.jsonl`), the one thing this whole build
treats as the actual source of truth (§2.1: "the three indexes are
disposable; the canonical JSONL is not"). This is the recovery path, the
migration path, the change-your-embedding-model path, and the "I think the
index is wrong" path — it has to work from canonical alone, not from
SQLite, or it isn't actually any of those things.

An earlier version of this script read FROM the SQLite `docs` table
instead of canonical — a real gap: if `docs` itself were lost or
corrupted, that version had nothing to rebuild FROM. Fixed here.

Canonical is append-only (one line per new/changed doc, across every
sync); this replays every line in file order and keeps only the LAST
state per `doc_id`, which is either a real `CanonicalDoc` or a forget
tombstone (`{"doc_id":..., "forgotten": true, ...}` from historical
canonical lines) — a tombstone is excluded from the rebuild
entirely, which is what makes “a forgotten doc does not come back
after a rebuild” true.

Scope, same as the version this replaces: RAW ingested docs only (one row
per canonical line) — this does not re-run distillation or ontology
extraction, so thread artifacts/bursts and `:Entity`/ontology edges are
NOT recreated by a rebuild (those never had a canonical line to begin
with; they're the store layer's own derived state). A full re-distillation
+ re-extraction pass is a separate, LLM-cost-bearing operation.

Usage: `python scripts/rebuild_index.py [--batch-size N] [--dry-run]`
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import joel.app as app  # noqa: E402
from joel.config import Settings  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.live_index import LiveIndex  # noqa: E402
from joel.models import CanonicalDoc, period_of  # noqa: E402
from joel.store import HydraStore  # noqa: E402
from joel.store_sql import from_canonical_doc, upsert_docs  # noqa: E402


def replay_canonical(canonical_dir: Path) -> tuple[dict[str, CanonicalDoc], set[str]]:
    """One pass over every `*.jsonl` file, in file order, folding to the
    LAST state per doc_id. Returns (surviving_docs, forgotten_doc_ids)."""
    latest: dict[str, CanonicalDoc] = {}
    forgotten: set[str] = set()
    for path in sorted(canonical_dir.glob("*.jsonl")):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                doc = CanonicalDoc.model_validate_json(line)
            except ValidationError:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    print(f"  skipping unparseable line {path.name}:{lineno}")
                    continue
                doc_id = payload.get("doc_id")
                if not doc_id:
                    print(f"  skipping line with no doc_id {path.name}:{lineno}")
                    continue
                if payload.get("forgotten"):
                    forgotten.add(doc_id)
                    latest.pop(doc_id, None)
                else:
                    print(f"  skipping unrecognized non-tombstone line {path.name}:{lineno}")
                continue
            forgotten.discard(doc.doc_id)
            latest[doc.doc_id] = doc
    return latest, forgotten


def _upsert_docs_table(conn, docs: list[CanonicalDoc], *, now: str) -> None:
    """Reconstruct the raw `docs` row for each canonical doc — the same
    shape `app.py::_persist_canonical_docs` writes at ingest time, minus
    the triage/canonical-append side effects a replay must not repeat."""
    for doc in docs:
        conn.execute(
            """INSERT INTO docs(
                 id, source_type, external_id, title, body, content_hash, url,
                 timestamp, thread_id, parent_id, author_raw, container,
                 extra_json, first_seen, last_seen, forgotten, visibility,
                 granularity, artifact_class, validity, resolved, period)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 source_type=excluded.source_type, external_id=excluded.external_id,
                 title=excluded.title, body=excluded.body, content_hash=excluded.content_hash,
                 url=excluded.url, timestamp=excluded.timestamp, thread_id=excluded.thread_id,
                 parent_id=excluded.parent_id, author_raw=excluded.author_raw,
                 container=excluded.container, extra_json=excluded.extra_json,
                 last_seen=excluded.last_seen, forgotten=0, visibility=excluded.visibility,
                 granularity=excluded.granularity, artifact_class=excluded.artifact_class,
                 validity=excluded.validity, resolved=excluded.resolved, period=excluded.period""",
            (
                doc.doc_id,
                doc.source_type,
                doc.external_id,
                doc.title,
                doc.body,
                doc.content_hash,
                doc.url,
                doc.timestamp.isoformat() if doc.timestamp else None,
                doc.thread_id,
                doc.parent_id,
                doc.author_raw,
                doc.container,
                json.dumps(doc.extra),
                doc.first_seen.isoformat() if doc.first_seen else now,
                now,
                doc.visibility,
                doc.granularity,
                doc.artifact_class,
                doc.validity,
                doc.resolved,
                period_of(doc.timestamp),
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true", help="count what would be rebuilt, write nothing")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    settings = Settings.from_env()

    canonical_dir = app.DATA_DIR / "canonical"
    print(f"Replaying canonical from {canonical_dir} ...")
    surviving, forgotten = replay_canonical(canonical_dir)
    print(f"{len(surviving)} live docs, {len(forgotten)} forgotten (excluded) across canonical")

    if args.dry_run:
        return

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(settings.embed_model)

    def embed(texts: list[str]):
        return model.encode(texts, normalize_embeddings=True)

    dim = getattr(model, "get_embedding_dimension", model.get_sentence_embedding_dimension)()

    docs = list(surviving.values())
    with app.db() as conn:
        # The live scheduler may be writing to this same file concurrently
        # (a real sync running right now); app.db()'s connection has no
        # busy_timeout set, so an uncontended default write lock would
        # otherwise fail immediately instead of waiting its turn.
        conn.execute("PRAGMA busy_timeout=30000")

        index_path = app.DATA_DIR / "index" / "joel.npz"
        index = LiveIndex(index_path, dim=dim)

        with Hydra(settings) as hydra:
            hydra_store = HydraStore(hydra)
            now = app._now()
            total = len(docs)
            done = 0
            t0 = time.time()
            for i in range(0, total, args.batch_size):
                batch = docs[i : i + args.batch_size]
                _upsert_docs_table(conn, batch, now=now)
                report = upsert_docs(
                    conn, index, hydra_store, [from_canonical_doc(d) for d in batch], embed_fn=embed, now=now
                )
                conn.commit()
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

    print(f"\nRebuild complete: {len(docs)} docs reindexed into docs/FTS + vectors + graph from canonical.")


if __name__ == "__main__":
    main()
