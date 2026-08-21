"""Rebuild the entity/relation graph from scratch.

Extraction normally runs incrementally, once per sync, over whatever that
sync touched. That is right for steady state and wrong after any change to
the extraction vocabulary or prompt: the graph then holds a mixture of
claims produced under different rules, and the old ones never get revisited
because their documents have not changed.

This walks the whole corpus instead. It purges the entity layer (Entity and
Alias nodes, and via DETACH every MENTIONS/AUTHORED/ontology edge attached
to them), resets the entity registry, and re-extracts.

WHAT IT DOES NOT TOUCH
    Doc nodes, :DISTILLED_FROM, :REVERSED, and everything in SQLite. Only
    the derived entity layer is rebuilt, so a bad run costs LLM spend and
    time, never source data.

TARGET SELECTION
    One target per unit of meaning, never two. A thread that produced a
    distilled artifact is represented by that artifact; the raw messages
    behind it are skipped, because extracting from both writes the same
    claim twice from two doc_ids and the reconciler cannot tell that apart
    from genuine corroboration. Threads with no artifact fall back to their
    own documents. Source code is excluded outright -- it yields entities
    that are identifier names.

CONCURRENCY
    The extraction call is network-bound and independent per document, so
    those run in a pool. Applying results is serial by necessity: entity
    resolution mutates a shared registry and is order-dependent, since two
    documents naming the same person must see each other's writes to
    resolve to one entity instead of two.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from joel.config import Settings  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.llm import make_openrouter_caller  # noqa: E402
from joel.ontology.extract import ExtractFailure, ExtractInput, extract_ontology  # noqa: E402
from joel.ontology.pipeline import (  # noqa: E402
    OntologyReport,
    apply_extraction,
    registry_paths,
)
from joel.ontology.resolve import EntityRegistry, load_cache, save_cache  # noqa: E402
from joel.store import ALIAS_LABEL, ENTITY_LABEL, HydraStore  # noqa: E402

DATA_DIR = Path(os.getenv("JOEL_DATA", ROOT / "data"))


def _targets(conn: sqlite3.Connection, org_id: int) -> list[ExtractInput]:
    rows = conn.execute(
        """
        SELECT id, source_type, container, timestamp, author_raw, title, body,
               granularity
        FROM docs d
        WHERE d.org_id = ?
          AND d.forgotten = 0
          AND (
                d.granularity = 'artifact'
             OR (
                  d.granularity = 'document'
              AND d.source_type != 'github'
              AND (
                    d.thread_id IS NULL
                 OR d.thread_id NOT IN (
                      SELECT thread_id FROM thread_state
                      WHERE artifact_id IS NOT NULL AND artifact_id != ''
                    )
              )
             )
          )
        ORDER BY d.granularity DESC, d.timestamp DESC
        """,
        (org_id,),
    ).fetchall()
    return [
        ExtractInput(
            doc_id=r["id"],
            source_type=r["source_type"],
            container=r["container"],
            timestamp=r["timestamp"],
            # Artifacts have actors[], not one author; AUTHORED is not
            # derived for them (mirrors `_artifact_extract_input`).
            author_raw=None if r["granularity"] == "artifact" else r["author_raw"],
            title=r["title"],
            body=r["body"],
        )
        for r in rows
        if (r["body"] or "").strip()
    ]


def purge(store: HydraStore, data_dir: Path) -> None:
    """Drop the entity layer and the registry that names it.

    Both have to go together. The registry maps a surface form to an entity
    id; keeping it while deleting the nodes would have the next run resolve
    "BESCOM" to an id that no longer exists in the graph, and the nodes
    would come back only if some document happened to mention them again.
    """
    entities = store.all_entities(limit=100000)
    print(f"  purging {len(entities)} entities …", flush=True)
    for e in entities:
        store.delete_node(ENTITY_LABEL, e["key"])

    aliases = store.hydra.bolt(f"MATCH (a:{ALIAS_LABEL}) RETURN a.key AS key LIMIT 100000")
    keys = [r["key"] for r in aliases if r["key"]]
    print(f"  purging {len(keys)} aliases …", flush=True)
    for key in keys:
        store.delete_node(ALIAS_LABEL, key)

    registry_path, cache_path, _ = registry_paths(data_dir)
    for path in (registry_path, cache_path):
        if path.exists():
            path.unlink()
            print(f"  removed {path.name}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="cap targets (smoke test)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", default="", help="override the extract model")
    ap.add_argument("--no-purge", action="store_true", help="add to the existing graph")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    args = ap.parse_args()

    conn = sqlite3.connect(DATA_DIR / "index" / "joel.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row

    settings_map = {
        r["key"]: r["value"]
        for r in conn.execute("SELECT key, value FROM settings WHERE org_id=?", (args.org,))
    }
    if args.model:
        settings_map["llm_model_extract"] = args.model
    if not settings_map.get("llm_api_key"):
        print("no llm_api_key configured for this org", file=sys.stderr, flush=True)
        return 1
    llm_call = make_openrouter_caller(settings_map)

    store = HydraStore(Hydra(Settings.from_env().for_org(args.org)))
    targets = _targets(conn, args.org)
    if args.limit:
        targets = targets[: args.limit]

    print(f"targets: {len(targets)}", flush=True)
    print(f"extract model: {settings_map.get('llm_model_extract')}")
    print(f"resolve model: {settings_map.get('llm_model_resolve')}", flush=True)
    if not args.yes:
        reply = input(f"run {len(targets)} extraction calls? [y/N] ").strip().lower()
        if reply != "y":
            print("aborted", flush=True)
            return 1

    started = time.time()
    if not args.no_purge:
        purge(store, DATA_DIR)

    registry_path, cache_path, conflicts_path = registry_paths(DATA_DIR)
    registry = EntityRegistry.load(registry_path)
    cache = load_cache(cache_path)
    report = OntologyReport()

    # -- phase 1: extract, concurrently --------------------------------
    done = 0
    results: list[tuple[ExtractInput, object]] = []

    def _extract(target: ExtractInput):
        try:
            return target, extract_ontology(llm_call, target)
        except ExtractFailure as exc:
            return target, exc
        except Exception as exc:  # a rebuild must not die on one bad doc
            return target, ExtractFailure(target.doc_id, str(exc))

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for target, outcome in pool.map(_extract, targets):
            done += 1
            if done % 25 == 0 or done == len(targets):
                rate = done / max(time.time() - started, 1e-6)
                left = (len(targets) - done) / max(rate, 1e-6)
                print(f"  extracted {done}/{len(targets)}  ({rate:.1f}/s, ~{left/60:.1f}m left)", flush=True)
            results.append((target, outcome))

    # -- phase 2: resolve + write, serially ----------------------------
    print("applying …", flush=True)
    for i, (target, outcome) in enumerate(results, 1):
        if isinstance(outcome, ExtractFailure):
            report.extract_errors.append(str(outcome))
            continue
        try:
            apply_extraction(
                conn, store, llm_call, target, outcome, registry, cache, conflicts_path, report
            )
            # Commit per document. Python's sqlite3 opens an implicit
            # transaction on the first write and holds it until commit, so
            # without this the whole apply phase is one transaction: the
            # write lock is held for the entire run, every other writer gets
            # "database is locked", and the API cannot even boot (its
            # startup seeding is a write). A bulk job must not take the
            # database hostage from the app it is rebuilding data for.
            conn.commit()
        except Exception as exc:
            conn.rollback()
            report.extract_errors.append(f"apply {target.doc_id}: {exc}")
        if i % 50 == 0 or i == len(results):
            print(f"  applied {i}/{len(results)}", flush=True)

    registry.save(registry_path)
    save_cache(cache_path, cache)

    elapsed = time.time() - started
    print(f"\ndone in {elapsed/60:.1f}m", flush=True)
    print(f"  extracted        {report.docs_extracted}")
    print(f"  skipped as noise {report.docs_skipped_noise}", flush=True)
    print(f"  entities touched {report.entities_touched}")
    print(f"  relations written {report.relations_written}", flush=True)
    print(f"  errors           {len(report.extract_errors)}")
    for err in report.extract_errors[:5]:
        print(f"    {err[:150]}", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
