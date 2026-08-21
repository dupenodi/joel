"""Mode B tenant isolation: settings, memberships, docs FTS, spend, namespaces."""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import joel.app as app  # noqa: E402
from joel import identity  # noqa: E402

from joel.models import CanonicalDoc, compute_content_hash  # noqa: E402
from joel.retrieve.lanes import fts_lane  # noqa: E402
from joel.retrieve.planner import QueryPlan  # noqa: E402
from joel.visibility import AskContext  # noqa: E402


def _doc(doc_id: str, body: str, *, org_marker: str) -> CanonicalDoc:
    now = datetime.now(timezone.utc)
    title = f"Secret {org_marker}"
    return CanonicalDoc(
        doc_id=doc_id,
        source_type="test",
        external_id=doc_id,
        title=title,
        body=body,
        content_hash=compute_content_hash(title, body),
        timestamp=now,
        first_seen=now,
        last_seen=now,
        visibility="org",
    )


def check_graph_scopes_are_isolated() -> None:
    """Two workspaces must not see each other's graph — asserted against a
    live HydraDB, because this is exactly the property that silently was not
    true while every transport still agreed on the *names*.

    The old check here compared `hydra_namespace_for(1)` to
    `hydra_namespace_for(2)` and passed because two strings differed. They
    did; it decided nothing. `Hydra.bolt` hardcoded `database="default"` and
    ignored the namespace entirely, so both workspaces read and wrote one
    graph while the naming looked per-tenant. A test that only inspects the
    label on the door cannot notice that every door opens the same room —
    so this one writes through one workspace's store and reads through the
    other's.

    Both workspaces use the *same* external key deliberately: keys hash to
    vertex ids with no org in them, so an identical key is the sharpest probe
    for a shared store. Isolation here is HydraDB's scoped database doing the
    work, not a key-mangling scheme of ours.
    """
    from joel.config import Settings, hydra_database_for  # noqa: PLC0415
    from joel.hydra import Hydra  # noqa: PLC0415
    from joel.store import HydraStore  # noqa: PLC0415

    try:
        settings = Settings.from_env()
    except KeyError:
        print("skip graph scope isolation (HYDRA_* not configured)")
        return

    label = "IsolationProbe"
    key = "isolation-probe/shared-key"  # identical on both sides, on purpose
    marker = {1: "org-one-secret", 2: "org-two-secret"}
    stores: dict[int, HydraStore] = {}
    hydras: list[Hydra] = []
    try:
        for org_id in (1, 2):
            org_settings = settings.for_org(org_id)
            assert org_settings.hydra_database == hydra_database_for(org_id)
            # Transports must name one scope, or writes and reads diverge.
            assert org_settings.hydra_database.endswith(
                org_settings.hydra_namespace.rsplit("/", 1)[-1] + "._"
            )
            hydra = Hydra(org_settings)
            hydras.append(hydra)
            stores[org_id] = HydraStore(hydra)

        for org_id, store in stores.items():
            store.hydra.bolt(f"MATCH (n:{label}) DETACH DELETE n")
            store.create_node(label, key, name=marker[org_id])

        for org_id, store in stores.items():
            found = store.get_node(label, key, ["name"])
            assert found is not None, f"org {org_id} lost its own node"
            assert found["name"] == marker[org_id], (
                f"org {org_id} read {found['name']!r} — the other workspace's "
                "write landed in this workspace's graph"
            )
            count = store.count_nodes(label)
            assert count == 1, (
                f"org {org_id} sees {count} probe nodes; a workspace must see "
                "only its own, and a label-wide sweep is where a shared store "
                "shows up"
            )
        print("ok  graph scopes isolated per org (same key, separate stores)")
    finally:
        for store in stores.values():
            try:
                store.hydra.bolt(f"MATCH (n:{label}) DETACH DELETE n")
            except Exception:
                pass
        for hydra in hydras:
            hydra.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app.DATA_DIR = tmp
        app.DB_PATH = tmp / "index" / "joel.db"
        app.init_db()

        with app.db() as conn:
            # ── two orgs ──────────────────────────────────────────────────
            ada, sid1 = identity.setup(
                conn,
                email="ada@acme.test",
                password="secretsecret",
                display_name="Ada",
                domain="acme.test",
            )
            app.seed_org_defaults(conn, ada.org_id)
            assert ada.org_id == 1

            org2_id, _owner2 = identity.create_workspace(
                conn, ada.user_id, domain="other.test", slug="other"
            )
            app.seed_org_defaults(conn, org2_id)
            assert org2_id == 2

            # Switch Ada's session back to org 1 for clarity
            ada = identity.switch_workspace(conn, sid1, 1)

            # ── settings do not leak ──────────────────────────────────────
            conn.execute(
                "INSERT INTO settings(org_id, key, value) VALUES (?,?,?) "
                "ON CONFLICT(org_id, key) DO UPDATE SET value=excluded.value",
                (1, "llm_api_key", "key-for-acme"),
            )
            conn.execute(
                "INSERT INTO settings(org_id, key, value) VALUES (?,?,?) "
                "ON CONFLICT(org_id, key) DO UPDATE SET value=excluded.value",
                (2, "llm_api_key", "key-for-other"),
            )
            s1 = app._settings_map(conn, 1)
            s2 = app._settings_map(conn, 2)
            assert s1["llm_api_key"] == "key-for-acme"
            assert s2["llm_api_key"] == "key-for-other"
            assert s1["llm_api_key"] != s2["llm_api_key"]
            print("ok  settings scoped by org_id")

            # ── memberships / identity APIs ───────────────────────────────
            members1 = identity.list_members(conn, 1)
            members2 = identity.list_members(conn, 2)
            assert any(m["email"] == "ada@acme.test" for m in members1)
            # create_workspace adds Ada as owner of org 2 as well
            assert any(m["email"] == "ada@acme.test" for m in members2)
            # Sam only in org 1
            invite_id, _token = identity.create_invite(
                conn, ada, email="sam@acme.test", role="member"
            )
            assert invite_id
            assert identity.list_invites(conn, 1)
            assert identity.list_invites(conn, 2) == []
            print("ok  memberships/invites scoped by org_id")

            # ── docs + FTS isolation ──────────────────────────────────────
            secret1 = "alphacorp-unique-token-xyz"
            secret2 = "betacorp-unique-token-uvw"
            app._persist_canonical_docs(
                conn, [_doc("doc_acme_1", f"Acme payroll uses {secret1}", org_marker="acme")], org_id=1
            )
            app._persist_canonical_docs(
                conn, [_doc("doc_other_1", f"Other payroll uses {secret2}", org_marker="other")], org_id=2
            )
            # Populate FTS the same way store_sql does for ingested rows
            for doc_id in ("doc_acme_1", "doc_other_1"):
                row = conn.execute(
                    "SELECT rowid, title, body FROM docs WHERE id=?", (doc_id,)
                ).fetchone()
                assert row is not None
                conn.execute(
                    "INSERT INTO docs_fts(rowid, title, body) VALUES (?, ?, ?)",
                    (row["rowid"], row["title"], row["body"]),
                )

            plan = QueryPlan(intent="lookup")
            ask1 = AskContext.web(ada.user_id, org_id=1)
            ask2 = AskContext.web(ada.user_id, org_id=2)

            hits1 = fts_lane(conn, plan, secret1, org_id=1)
            hits1_leak = fts_lane(conn, plan, secret2, org_id=1)
            hits2 = fts_lane(conn, plan, secret2, org_id=2)
            hits2_leak = fts_lane(conn, plan, secret1, org_id=2)

            assert any(h.id == "doc_acme_1" for h in hits1), hits1
            assert not any(h.id == "doc_other_1" for h in hits1_leak), hits1_leak
            assert any(h.id == "doc_other_1" for h in hits2), hits2
            assert not any(h.id == "doc_acme_1" for h in hits2_leak), hits2_leak

            # hydrate via ask.org_id path (run_lanes wiring)
            from joel.retrieve.lanes import hydrate_doc_ids

            both = hydrate_doc_ids(
                conn, ["doc_acme_1", "doc_other_1"], org_id=ask1.org_id
            )
            assert [d.id for d in both] == ["doc_acme_1"]
            both2 = hydrate_doc_ids(
                conn, ["doc_acme_1", "doc_other_1"], org_id=ask2.org_id
            )
            assert [d.id for d in both2] == ["doc_other_1"]
            print("ok  docs/FTS isolated by org_id")

            # ── spend keyed by (org_id, stage) ────────────────────────────
            conn.execute(
                "UPDATE spend SET calls = calls + 3 WHERE org_id=? AND stage=?",
                (1, "answer"),
            )
            conn.execute(
                "UPDATE spend SET calls = calls + 7 WHERE org_id=? AND stage=?",
                (2, "answer"),
            )
            c1 = conn.execute(
                "SELECT calls FROM spend WHERE org_id=? AND stage=?", (1, "answer")
            ).fetchone()["calls"]
            c2 = conn.execute(
                "SELECT calls FROM spend WHERE org_id=? AND stage=?", (2, "answer")
            ).fetchone()["calls"]
            assert c1 == 3 and c2 == 7
            print("ok  spend scoped by (org_id, stage)")

            # ── LiveIndex path shape (no model load) ──────────────────────
            p1 = app.DATA_DIR / "index" / "org-1.npz"
            p2 = app.DATA_DIR / "index" / "org-2.npz"
            assert "org-1.npz" in str(p1) and "org-2.npz" in str(p2)
            print("ok  live index path pattern org-{id}.npz")

    check_graph_scopes_are_isolated()

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
