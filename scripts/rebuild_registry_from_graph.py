"""Reconstruct `data/entities/registry.json` from the entities already in
HydraDB.

The registry is the resolver's memory: surface form -> entity id. Extraction
writes entities to Hydra *and* to the registry, but the registry is only
flushed to disk when the pipeline run finishes. A run that is interrupted
therefore leaves a populated graph and no registry, and the next sync
resolves "BESCOM" against an empty memory, mints a second entity id for it,
and quietly forks every entity in the graph.

Everything the registry holds is recoverable, because it is all already on
the nodes: `Entity.key/name/etype/identifier` and the `Alias` nodes pointing
at them. `EntityRegistry.load` re-derives its id counters from the id
suffixes, so a reconstructed file also resumes numbering correctly.

Evidence (`contexts`/`containers`) is not recoverable — it is only used to
explain a merge decision after the fact, never to make one — so it comes
back empty.

Idempotent. Refuses to overwrite a registry that already has more entities
than the graph, since that would be a downgrade rather than a repair.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from joel.config import Settings  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.ontology.pipeline import registry_paths  # noqa: E402
from joel.store import ALIAS_LABEL, HydraStore  # noqa: E402

DATA_DIR = Path(os.getenv("JOEL_DATA", ROOT / "data"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", type=int, default=1)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    store = HydraStore(Hydra(Settings.from_env().for_org(args.org)))
    entities = store.all_entities(limit=100000)

    alias_rows = store.hydra.bolt(
        f"MATCH (a:{ALIAS_LABEL}) RETURN a.key AS key, a.entity_key AS entity_key "
        "LIMIT 100000"
    )
    by_entity: dict[str, list[str]] = defaultdict(list)
    for row in alias_rows:
        key = row["key"]
        entity_key = row["entity_key"]
        if key and entity_key:
            by_entity[str(entity_key)].append(str(key))

    payload: dict[str, dict] = {}
    unnamed = 0
    for e in entities:
        entity_id = e["key"]
        name = (e.get("name") or "").strip()
        if not name:
            # A nameless entity cannot be resolved against by surface form;
            # carrying it into the registry would only let it absorb future
            # mentions it has no claim to.
            unnamed += 1
            continue
        payload[entity_id] = {
            "canonical_name": name,
            "type": e.get("etype") or "SERVICE",
            "identifier": e.get("identifier") or None,
            "aliases": sorted(set(by_entity.get(entity_id, []))),
            "evidence": {"contexts": [], "containers": []},
        }

    registry_path, _cache_path, _ = registry_paths(DATA_DIR)
    existing = 0
    if registry_path.exists():
        try:
            existing = len(json.loads(registry_path.read_text() or "{}"))
        except ValueError:
            existing = 0

    print(f"graph entities      {len(entities)}")
    print(f"  reconstructable   {len(payload)}")
    print(f"  skipped (no name) {unnamed}")
    print(f"  aliases mapped    {sum(len(v['aliases']) for v in payload.values())}")
    print(f"existing registry   {existing}")

    if existing > len(payload):
        print("existing registry is larger than the graph; refusing to overwrite")
        return 1
    if not args.apply:
        print("dry run; pass --apply to write")
        return 0

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote {registry_path} ({len(payload)} entities)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
