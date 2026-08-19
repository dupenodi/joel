"""Visibility stamps at ingest, and the rooms an ask is allowed to read.

Does not need Hydra or an embedding model. Retrieval assertions use the
same fake bag-of-words embed as check_5/check_7.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import numpy as np  # noqa: E402

import joel.app as app  # noqa: E402
from joel.adapters import GMAIL, SLACK, adapt  # noqa: E402
from joel.connectors.slack import channel_kind  # noqa: E402
from joel.live_index import LiveIndex  # noqa: E402
from joel.membership import member_channel_stamps, sync_slack_channel_memberships  # noqa: E402
from joel.models import CanonicalDoc, compute_content_hash  # noqa: E402
from joel.retrieve.lanes import fts_lane, run_lanes  # noqa: E402
from joel.retrieve.planner import QueryPlan  # noqa: E402
from joel.store_sql import from_canonical_doc, upsert_docs  # noqa: E402
from joel.visibility import (  # noqa: E402
    ORG,
    AskContext,
    Room,
    Visibility,
    VisibilityError,
    allowed_stamps,
    apply,
    derive,
    parse,
)

_FAKE_EMBED_DIM = 64


def expect(exc_type, fn):
    try:
        fn()
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__}")


def _fake_embed(texts: list[str]):
    matrix = np.zeros((len(texts), _FAKE_EMBED_DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in text.lower().split():
            matrix[i, hash(word) % _FAKE_EMBED_DIM] += 1.0
    return matrix


class _NoGraph:
    def upsert_nodes(self, *a, **k):
        return None

    def link_nodes(self, *a, **k):
        return None

    def delete_node(self, *a, **k):
        return None


def check_parse_roundtrip() -> None:
    assert parse("org").stamp == ORG
    private = parse("channel:slack:C123")
    assert private.kind == "channel" and private.provider == "slack" and private.scope == "C123"
    mail = parse("user:gmail:ada@yourco.dev")
    assert mail.stamp == "user:gmail:ada@yourco.dev"
    expect(VisibilityError, lambda: parse("channel:slack"))
    expect(VisibilityError, lambda: parse("acl:everyone"))
    expect(VisibilityError, lambda: Visibility("org", provider="slack"))
    print("ok  parse / stamp roundtrip")


def check_derive() -> None:
    assert derive("github", container="acme/joel").stamp == ORG
    assert derive("notion").stamp == ORG
    assert derive("slack", extra={"channel_kind": "public", "channel_id": "Cpub"}).stamp == ORG
    assert (
        derive("slack", extra={"channel_kind": "private", "channel_id": "Cpriv"}).stamp
        == "channel:slack:Cpriv"
    )
    assert (
        derive("slack", extra={"channel_kind": "im", "channel_id": "Dada"}).stamp
        == "user:slack:Dada"
    )
    assert derive("gmail", container="Ada@Yourco.dev").stamp == "user:gmail:ada@yourco.dev"
    print("ok  derive from source facts")


def check_adapt_stamps() -> None:
    slack_public = adapt(
        SLACK,
        {
            "ts": "1700000000.000001",
            "text": "Public channel note about the restore hang after manifest load.",
            "user": "U1",
            "channel": "eng",
            "channel_id": "Cpub",
            "channel_kind": "public",
            "team_domain": "acme",
        },
    )
    assert slack_public is not None and slack_public.visibility == ORG
    slack_private = adapt(
        SLACK,
        {
            "ts": "1700000000.000002",
            "text": "Private channel note about the restore hang after manifest load.",
            "user": "U1",
            "channel": "founders",
            "channel_id": "Cpriv",
            "channel_kind": "private",
            "team_domain": "acme",
        },
    )
    assert slack_private is not None
    assert slack_private.visibility == "channel:slack:Cpriv"
    assert slack_private.extra["channel_id"] == "Cpriv"
    assert slack_private.extra["channel_kind"] == "private"
    hashed = slack_private.content_hash
    restamped = apply(slack_private)
    assert restamped.content_hash == hashed, "visibility must not enter content_hash"

    gmail = adapt(
        GMAIL,
        {
            "id": "m1",
            "threadId": "t1",
            "subject": "Restore hang on NFS",
            "from": "soham@acme.dev",
            "to": ["alice@acme.dev"],
            "internalDate": "1755000000000",
            "mailbox": "you@acme.dev",
            "body": "Setting CKPT_PREFETCH=4 unblocked restore on the NFS mount.",
        },
    )
    assert gmail is not None and gmail.visibility == "user:gmail:you@acme.dev"

    assert channel_kind({"is_private": True}) == "private"
    assert channel_kind({"is_im": True}) == "im"
    assert channel_kind({"is_channel": True}) == "public"
    print("ok  adapt stamps slack/gmail; hash ignores visibility")


def check_ask_policy() -> None:
    web = AskContext.web("user_ada")
    assert allowed_stamps(web) == frozenset({ORG})

    desk = AskContext.web(
        "user_ada",
        aliases={"user:gmail:ada@yourco.dev"},
        channels={"channel:slack:Cpriv"},
    )
    assert allowed_stamps(desk) == frozenset(
        {ORG, "user:gmail:ada@yourco.dev", "channel:slack:Cpriv"}
    )

    public_slack = AskContext(actor_id="user_ada", room=Room.public("slack"))
    assert allowed_stamps(public_slack) == frozenset({ORG})

    in_channel = AskContext(
        actor_id="user_ada",
        room=Room.channel("slack", "slack", "Cpriv"),
    )
    assert allowed_stamps(in_channel) == frozenset({ORG, "channel:slack:Cpriv"})
    assert "user:gmail:ada@yourco.dev" not in allowed_stamps(in_channel)
    print("ok  ask policy: public ⊂ channel ⊂ desk")


def check_persist_and_migration() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app.DATA_DIR = tmp
        app.DB_PATH = tmp / "index" / "joel.db"
        app.DB_PATH.parent.mkdir(parents=True)
        with app.db() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            conn.execute("INSERT INTO schema_version(version) VALUES (0)")
            for path in sorted(app.MIGRATIONS_DIR.glob("[0-9]*.sql")):
                version = int(path.name.split("_", 1)[0])
                if version > 3:
                    continue
                conn.executescript(path.read_text())
                conn.execute("UPDATE schema_version SET version = ?", (version,))
            conn.execute(
                """INSERT INTO docs(
                     id, source_type, external_id, title, body, content_hash,
                     container, extra_json, first_seen, last_seen)
                   VALUES ('old_mail','gmail','m0','hi','hello there this is long enough',
                           'hash','Ada@Yourco.dev','{}','t0','t0')"""
            )
            conn.execute(
                """INSERT INTO docs(
                     id, source_type, external_id, title, body, content_hash,
                     container, extra_json, first_seen, last_seen)
                   VALUES ('old_pr','github','1','pr','a github pr body long enough',
                           'hash','acme/joel','{}','t0','t0')"""
            )
            conn.commit()
            app.run_migrations(conn)
            assert conn.execute("SELECT version FROM schema_version").fetchone()[0] >= 4
            mail = conn.execute("SELECT visibility FROM docs WHERE id='old_mail'").fetchone()
            pr = conn.execute("SELECT visibility FROM docs WHERE id='old_pr'").fetchone()
            assert mail["visibility"] == "user:gmail:ada@yourco.dev"
            assert pr["visibility"] == ORG

        app.init_db()
        with app.db() as conn:
            docs = [
                CanonicalDoc(
                    doc_id="slack_priv",
                    source_type="slack",
                    external_id="Cpriv:1",
                    title="secret",
                    body="private channel note about the payroll number for Q3",
                    extra={"channel_kind": "private", "channel_id": "Cpriv"},
                    container="founders",
                    content_hash=compute_content_hash(
                        "secret", "private channel note about the payroll number for Q3"
                    ),
                    timestamp=datetime(2026, 8, 1, tzinfo=timezone.utc),
                )
            ]
            counts, dirty = app._persist_canonical_docs(conn, docs)
            assert counts["new"] == 1
            assert dirty[0].visibility == "channel:slack:Cpriv"
            row = conn.execute("SELECT visibility FROM docs WHERE id='slack_priv'").fetchone()
            assert row["visibility"] == "channel:slack:Cpriv"
    print("ok  persist writes stamp; gmail restamp is personal")


def check_old_npz_defaults_org() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "old.npz"
        n, dim = 2, 8
        np.savez(
            path,
            matrix=np.ones((n, dim), dtype=np.float32),
            ids=np.array(["a", "b"], dtype=object),
            forgotten=np.zeros(n, dtype=bool),
            granularity=np.array(["document", "document"], dtype=object),
            artifact_class=np.array(["document", "document"], dtype=object),
            validity=np.array(["current", "current"], dtype=object),
            resolved=np.array(["na", "na"], dtype=object),
            period=np.array(["", ""], dtype=object),
            source_type=np.array(["slack", "gmail"], dtype=object),
        )
        index = LiveIndex(path, dim=dim)
        assert list(index.snapshot().meta["visibility"]) == ["org", "org"]
        mask = index.mask(visibility=(ORG,))
        assert mask.all()
    print("ok  old npz missing visibility loads as org")


def check_retrieval_respects_room() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app.DATA_DIR = tmp
        app.DB_PATH = tmp / "index" / "joel.db"
        app.init_db()
        index = LiveIndex(tmp / "vectors.npz", dim=_FAKE_EMBED_DIM)

        public = CanonicalDoc(
            doc_id="pub",
            source_type="slack",
            external_id="Cpub:1",
            title="Public restore note",
            body="The public restore hang is fixed by CKPT_PREFETCH.",
            extra={"channel_kind": "public", "channel_id": "Cpub"},
            content_hash=compute_content_hash(
                "Public restore note", "The public restore hang is fixed by CKPT_PREFETCH."
            ),
            visibility=ORG,
        )
        private = CanonicalDoc(
            doc_id="priv",
            source_type="slack",
            external_id="Cpriv:1",
            title="Private payroll note",
            body="The private restore hang is also mentioned with CKPT_PREFETCH.",
            extra={"channel_kind": "private", "channel_id": "Cpriv"},
            content_hash=compute_content_hash(
                "Private payroll note",
                "The private restore hang is also mentioned with CKPT_PREFETCH.",
            ),
            visibility="channel:slack:Cpriv",
        )
        mail = CanonicalDoc(
            doc_id="mail",
            source_type="gmail",
            external_id="m1",
            title="Personal restore mail",
            body="My private restore hang notes mention CKPT_PREFETCH too.",
            container="ada@yourco.dev",
            content_hash=compute_content_hash(
                "Personal restore mail",
                "My private restore hang notes mention CKPT_PREFETCH too.",
            ),
            visibility="user:gmail:ada@yourco.dev",
        )
        with app.db() as conn:
            upsert_docs(
                conn,
                index,
                _NoGraph(),
                [from_canonical_doc(d) for d in (public, private, mail)],
                embed_fn=_fake_embed,
                now="t0",
            )
            plan = QueryPlan(intent="lookup")
            q = "CKPT_PREFETCH restore hang"

            web_ids = {
                d.id
                for docs in run_lanes(
                    conn, index, _fake_embed, plan, q, ask=AskContext.web("user_ada")
                ).values()
                for d in docs
            }
            assert "pub" in web_ids
            assert "priv" not in web_ids
            assert "mail" not in web_ids

            channel_ids = {
                d.id
                for docs in run_lanes(
                    conn,
                    index,
                    _fake_embed,
                    plan,
                    q,
                    ask=AskContext(
                        actor_id="user_ada",
                        room=Room.channel("slack", "slack", "Cpriv"),
                    ),
                ).values()
                for d in docs
            }
            assert "pub" in channel_ids and "priv" in channel_ids
            assert "mail" not in channel_ids

            desk_ids = {
                d.id
                for docs in run_lanes(
                    conn,
                    index,
                    _fake_embed,
                    plan,
                    q,
                    ask=AskContext.web(
                        "user_ada",
                        aliases={"user:gmail:ada@yourco.dev"},
                        channels={"channel:slack:Cpriv"},
                    ),
                ).values()
                for d in docs
            }
            assert desk_ids >= {"pub", "priv", "mail"}

            fts_public = {
                d.id
                for d in fts_lane(
                    conn, plan, "CKPT_PREFETCH", allowed=frozenset({ORG})
                )
            }
            assert fts_public == {"pub"}
    print("ok  retrieval: public cannot see private or mail")


def check_channel_membership() -> None:
    """§1.4's channel-membership groundwork: a Slack channel member,
    matched to a workspace Actor by email, gets that channel's stamp in
    AskContext.web -- and a non-member doesn't."""

    def fake_caller(method: str, params: dict) -> dict:
        if method == "users.list":
            return {
                "ok": True,
                "members": [
                    {"id": "U1", "profile": {"email": "ada@yourco.dev"}},
                    {"id": "U2", "profile": {"email": "bob@yourco.dev"}},
                    {"id": "U3", "profile": {}},  # no email visible -- must not crash, just skip
                ],
            }
        if method == "conversations.members":
            assert params.get("channel") == "Cpriv"
            return {"ok": True, "members": ["U1"]}  # only Ada is in this channel
        raise AssertionError(f"unexpected Slack method {method!r}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app.DATA_DIR = tmp
        app.DB_PATH = tmp / "index" / "joel.db"
        app.init_db()
        with app.db() as conn:
            conn.execute(
                "INSERT INTO users(id, email, display_name, password_hash, created_at) VALUES (?,?,?,?,?)",
                ("user_ada", "ada@yourco.dev", "Ada", "x", "t0"),
            )
            conn.execute(
                "INSERT INTO users(id, email, display_name, password_hash, created_at) VALUES (?,?,?,?,?)",
                ("user_bob", "bob@yourco.dev", "Bob", "x", "t0"),
            )

            written = sync_slack_channel_memberships(
                conn, channel_ids=["Cpriv"], caller=fake_caller, now="t0"
            )
            assert written == 1, f"only Ada should match a channel membership, got {written}"

            ada_stamps = member_channel_stamps(conn, "user_ada")
            assert ada_stamps == {"channel:slack:Cpriv"}, ada_stamps
            bob_stamps = member_channel_stamps(conn, "user_bob")
            assert bob_stamps == frozenset(), f"Bob is not a member of Cpriv, got {bob_stamps}"

            # Re-running the sync must not duplicate the row (ON CONFLICT
            # upsert, primary key is (user_id, provider, channel_id)).
            sync_slack_channel_memberships(conn, channel_ids=["Cpriv"], caller=fake_caller, now="t1")
            rows = conn.execute(
                "SELECT COUNT(*) AS n FROM channel_memberships WHERE user_id='user_ada'"
            ).fetchone()
            assert rows["n"] == 1, "re-syncing membership must not create a duplicate row"

            # End-to-end: Ada's resolved membership actually grants read
            # access to the private-channel doc, via the exact same
            # AskContext/allowed_stamps path check_retrieval_respects_room
            # already proved works when the channel set is passed in by hand.
            index = LiveIndex(tmp / "vectors.npz", dim=_FAKE_EMBED_DIM)
            private = CanonicalDoc(
                doc_id="priv2",
                source_type="slack",
                external_id="Cpriv:2",
                title="Private membership-gated note",
                body="Only channel members should find this via CKPT_PREFETCH.",
                extra={"channel_kind": "private", "channel_id": "Cpriv"},
                content_hash=compute_content_hash(
                    "Private membership-gated note",
                    "Only channel members should find this via CKPT_PREFETCH.",
                ),
                visibility="channel:slack:Cpriv",
            )
            upsert_docs(
                conn, index, _NoGraph(), [from_canonical_doc(private)], embed_fn=_fake_embed, now="t0"
            )
            plan = QueryPlan(intent="lookup")
            ada_ask = AskContext.web("user_ada", channels=member_channel_stamps(conn, "user_ada"))
            ada_ids = {
                d.id
                for docs in run_lanes(conn, index, _fake_embed, plan, "CKPT_PREFETCH", ask=ada_ask).values()
                for d in docs
            }
            assert "priv2" in ada_ids, "a real channel member must be able to retrieve that channel's doc"

            bob_ask = AskContext.web("user_bob", channels=member_channel_stamps(conn, "user_bob"))
            bob_ids = {
                d.id
                for docs in run_lanes(conn, index, _fake_embed, plan, "CKPT_PREFETCH", ask=bob_ask).values()
                for d in docs
            }
            assert "priv2" not in bob_ids, "a non-member must NOT be able to retrieve that channel's doc"
    print("ok  channel membership: a real member reads the channel, a non-member doesn't")


def main() -> None:
    check_parse_roundtrip()
    check_derive()
    check_adapt_stamps()
    check_ask_policy()
    check_persist_and_migration()
    check_old_npz_defaults_org()
    check_retrieval_respects_room()
    check_channel_membership()
    print("\nall visibility checks passed")


if __name__ == "__main__":
    main()
