"""GraphSlice neighborhood: alias resolve, visibility, reversal, no aliases in payload."""

from __future__ import annotations

import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from joel.config import Settings  # noqa: E402
from joel.graph_slice import around  # noqa: E402
from joel.hydra import Hydra  # noqa: E402
from joel.live_index import LiveIndex  # noqa: E402
from joel.models import CanonicalDoc, compute_content_hash  # noqa: E402
from joel.store import HydraStore  # noqa: E402
from joel.store_sql import StoreDoc, from_canonical_doc, upsert_docs  # noqa: E402
from joel.visibility import Visibility  # noqa: E402

import joel.app as app  # noqa: E402

RUN_ID = uuid.uuid4().hex[:8]
_FAKE_EMBED_DIM = 64
_created_doc_ids: list[str] = []
_created_entity_keys: list[str] = []
_created_alias_keys: list[str] = []


def _fake_embed(texts: list[str]):
    import numpy as np

    matrix = np.zeros((len(texts), _FAKE_EMBED_DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in text.lower().split():
            matrix[i, hash(word) % _FAKE_EMBED_DIM] += 1.0
    return matrix


def _doc(
    i: int,
    title: str,
    body: str,
    *,
    visibility: str = "org",
    validity: str = "current",
    granularity: str = "artifact",
    artifact_class: str = "decision",
) -> CanonicalDoc:
    doc_id = f"gs_{RUN_ID}_{i}"
    _created_doc_ids.append(doc_id)
    return CanonicalDoc(
        doc_id=doc_id,
        source_type="slack",
        external_id=f"ext_{i}",
        title=title,
        body=body,
        container=f"C_GS_{RUN_ID}",
        content_hash=compute_content_hash(title, body),
        timestamp=datetime(2026, 8, 1, tzinfo=timezone.utc),
        visibility=visibility,
        validity=validity,
        granularity=granularity,
        artifact_class=artifact_class,
        url=f"https://example.com/{doc_id}",
    )


def check_neighborhood(conn: sqlite3.Connection, index: LiveIndex, hydra_store: HydraStore) -> None:
    maya = f"gs_maya_{RUN_ID}"
    pricing = f"gs_pricing_{RUN_ID}"
    _created_entity_keys.extend([maya, pricing])
    hydra_store.upsert_nodes(
        "Entity",
        [
            {"key": maya, "name": "Maya Chen", "etype": "PERSON", "identifier": ""},
            {"key": pricing, "name": "Pricing v3", "etype": "POLICY", "identifier": ""},
        ],
    )
    hydra_store.upsert_nodes(
        "Alias",
        [{"key": "maya chen", "name": "maya chen", "entity_key": maya}],
    )
    _created_alias_keys.append("maya chen")

    public = _doc(1, "Pricing v3 decision", "Maya decided we ship pricing v3.")
    private = _doc(
        2,
        "Private aside",
        "Maya also said this in a DM.",
        visibility=Visibility.user("gmail", "hidden@x.com").stamp,
    )
    old = _doc(
        3,
        "Pricing v2",
        "Old plan.",
        validity="superseded",
        artifact_class="decision",
    )
    upsert_docs(
        conn,
        index,
        hydra_store,
        [from_canonical_doc(d) for d in (public, private, old)],
        embed_fn=_fake_embed,
        now="t0",
        org_id=1,
    )

    burst_id = f"gs_{RUN_ID}_burst"
    _created_doc_ids.append(burst_id)
    upsert_docs(
        conn,
        index,
        hydra_store,
        [
            StoreDoc(
                id=burst_id,
                title="maya: chatter",
                body="lol",
                source_type="slack",
                container="C",
                granularity="burst",
                artifact_class="document",
                validity="current",
                resolved="na",
                ts="2026-08-01T00:00:00+00:00",
                period="2026Q3",
                url=None,
                content_hash=compute_content_hash("maya: chatter", "lol"),
            )
        ],
        embed_fn=_fake_embed,
        now="t0",
        org_id=1,
    )
    hydra_store.link_nodes(
        "MENTIONS",
        "Doc",
        "Entity",
        [
            {"from_key": burst_id, "to_key": maya, "rel_key": f"{burst_id}::{maya}"},
        ],
    )

    hydra_store.link_nodes(
        "DECIDED",
        "Entity",
        "Entity",
        [
            {
                "from_key": maya,
                "to_key": pricing,
                "rel_key": f"{public.doc_id}::{maya}::DECIDED::{pricing}",
                "doc_id": public.doc_id,
                "ctx": "Maya decided we ship pricing v3.",
                "ts": "2026-08-01T00:00:00+00:00",
                "confidence": 0.9,
            }
        ],
    )
    hydra_store.link_nodes(
        "MENTIONS",
        "Doc",
        "Entity",
        [
            {"from_key": public.doc_id, "to_key": maya, "rel_key": f"{public.doc_id}::{maya}"},
            {"from_key": public.doc_id, "to_key": pricing, "rel_key": f"{public.doc_id}::{pricing}"},
            {"from_key": private.doc_id, "to_key": maya, "rel_key": f"{private.doc_id}::{maya}"},
            {"from_key": old.doc_id, "to_key": pricing, "rel_key": f"{old.doc_id}::{pricing}"},
        ],
    )
    hydra_store.link_nodes(
        "AUTHORED",
        "Entity",
        "Doc",
        [{"from_key": maya, "to_key": public.doc_id, "rel_key": f"{maya}::{public.doc_id}"}],
    )
    hydra_store.create_edge(
        "Doc", public.doc_id, "REVERSED", "Doc", old.doc_id, ts="2026-08-01T00:00:00+00:00"
    )

    empty = around(hydra_store, conn, "")
    assert empty["focus"] is None and empty["nodes"] == []

    missing = around(hydra_store, conn, "nobody-here")
    assert missing["focus"] is None

    slice_ = around(
        hydra_store, conn, "Maya Chen", hops=1, allowed=frozenset({"org"}), org_id=1
    )
    ids = {n["id"] for n in slice_["nodes"]}
    kinds = {n["id"]: n["kind"] for n in slice_["nodes"]}
    assert slice_["focus"]["id"] == maya
    assert "maya chen" not in ids, "Alias nodes must not appear"
    assert pricing in ids and kinds[pricing] == "entity"
    assert public.doc_id in ids
    assert private.doc_id not in ids, "private doc must not leak as a node"
    assert burst_id not in ids, "bursts stay off the neighborhood"
    assert old.doc_id in ids
    superseded = next(n for n in slice_["nodes"] if n["id"] == old.doc_id)
    assert superseded["validity"] == "superseded"

    predicates = {e["predicate"] for e in slice_["edges"]}
    assert "DECIDED" in predicates
    assert "REVERSED" in predicates
    assert "MENTIONS" in predicates
    assert "AUTHORED" in predicates
    assert any(e["id"] == private.doc_id for e in slice_["nodes"]) is False

    who = slice_["who_knows"]
    assert any(e["predicate"] == "DECIDED" and e["target"] == pricing for e in who)
    assert slice_["reversals"], "REVERSED ledger should surface"
    print("ok  graph slice: alias resolve, no aliases, private/burst filtered, reversal kept")


def main() -> None:
    load_dotenv(ROOT / ".env")
    settings = Settings.from_env()

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        app.DATA_DIR = tmp_dir
        app.DB_PATH = tmp_dir / "index" / "joel.db"
        app.init_db()

        with app.db() as conn:
            conn.execute(
                "INSERT INTO orgs(id, domain, name, logo_url, created_at) "
                "VALUES (1, 'x.co', 'X', '', '2026-08-20T00:00:00+00:00')"
            )
            conn.commit()
            with Hydra(settings) as hydra:
                hydra_store = HydraStore(hydra)
                index = LiveIndex(tmp_dir / f"vectors_{RUN_ID}.npz", dim=_FAKE_EMBED_DIM)
                try:
                    check_neighborhood(conn, index, hydra_store)
                finally:
                    for doc_id in _created_doc_ids:
                        try:
                            hydra_store.delete_node("Doc", doc_id)
                        except Exception:
                            pass
                    for key in _created_entity_keys:
                        try:
                            hydra_store.delete_node("Entity", key)
                        except Exception:
                            pass
                    for key in _created_alias_keys:
                        try:
                            hydra_store.delete_node("Alias", key)
                        except Exception:
                            pass

    print("\ngraph slice: all automated checks passed.")


if __name__ == "__main__":
    main()
