"""Users, membership, sessions, invites — one workspace per install."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import joel.app as app  # noqa: E402
from joel import identity  # noqa: E402
from joel.identity import IdentityError  # noqa: E402


def expect(exc_type, fn):
    try:
        fn()
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__}")


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app.DATA_DIR = tmp
        app.DB_PATH = tmp / "index" / "joel.db"
        app.init_db()

        with app.db() as conn:
            assert identity.setup_needed(conn)

            actor, sid = identity.setup(
                conn,
                email="Ada@Yourco.dev",
                password="secretsecret",
                display_name="Ada",
                domain="https://www.yourco.dev/about",
            )
            assert actor.is_admin
            assert actor.email == "ada@yourco.dev"
            ws = identity.workspace_public(conn)
            assert ws is not None
            assert ws["domain"] == "yourco.dev"
            assert ws["name"] == "Yourco"
            loaded = identity.actor_from_session(conn, sid)
            assert loaded is not None and loaded.user_id == actor.user_id

            dup = expect(
                IdentityError,
                lambda: identity.setup(
                    conn,
                    email="other@yourco.dev",
                    password="secretsecret",
                    display_name="Other",
                    domain="yourco.dev",
                ),
            )
            assert dup.status == 409

            bad = expect(
                IdentityError,
                lambda: identity.login(conn, "ada@yourco.dev", "nope-nope"),
            )
            assert bad.status == 401

            again, sid2 = identity.login(conn, "ada@yourco.dev", "secretsecret")
            assert again.user_id == actor.user_id
            assert sid2 != sid

            invite_id, token = identity.create_invite(
                conn, actor, email="sam@yourco.dev", role="member"
            )
            peek = identity.peek_invite(conn, token)
            assert peek["email"] == "sam@yourco.dev"
            assert peek["workspace_domain"] == "yourco.dev"

            sam, sam_sid = identity.accept_invite(
                conn, token, password="memberpass", display_name="Sam"
            )
            assert sam.role == "member"
            assert identity.actor_from_session(conn, sam_sid) is not None
            used = expect(IdentityError, lambda: identity.peek_invite(conn, token))
            assert used.status == 410

            members = identity.list_members(conn)
            assert {m["email"] for m in members} == {
                "ada@yourco.dev",
                "sam@yourco.dev",
            }

            forbid = expect(
                IdentityError,
                lambda: identity.create_invite(conn, sam, email="pat@yourco.dev"),
            )
            assert forbid.status == 403

            demote = expect(
                IdentityError,
                lambda: identity.set_member_role(conn, actor, actor.user_id, "member"),
            )
            assert "demote" in str(demote).lower() or "can’t" in str(demote) or "can't" in str(demote)

            identity.set_member_role(conn, actor, sam.user_id, "admin")
            identity.set_member_role(conn, actor, sam.user_id, "member")
            identity.remove_member(conn, actor, sam.user_id)
            left = identity.list_members(conn)
            assert [m["email"] for m in left] == ["ada@yourco.dev"]
            assert identity.actor_from_session(conn, sam_sid) is None

            identity.update_workspace(conn, actor, name="Yourco Inc")
            renamed = identity.workspace_public(conn)
            assert renamed is not None and renamed["name"] == "Yourco Inc"

            identity.logout(conn, sid2)
            assert identity.actor_from_session(conn, sid2) is None
            assert invite_id

    print("ok  identity: setup, login, invite, roles, workspace")


if __name__ == "__main__":
    main()
