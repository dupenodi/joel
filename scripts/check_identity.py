"""Multi-workspace identity: users, membership, sessions, invites, workspaces."""

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

            # ═══════════════════════════════════════════════════════════════
            # Setup creates org 1 with owner role
            # ═══════════════════════════════════════════════════════════════
            actor, sid = identity.setup(
                conn,
                email="Ada@Yourco.dev",
                password="secretsecret",
                display_name="Ada",
                domain="https://www.yourco.dev/about",
            )
            app.seed_org_defaults(conn, actor.org_id)
            assert actor.is_admin, "owner should be admin"
            assert actor.is_owner, "first user should be owner"
            assert actor.role == "owner"
            assert actor.email == "ada@yourco.dev"
            assert actor.org_id == 1
            ws = identity.workspace_public(conn, actor.org_id)
            assert ws is not None
            assert ws["domain"] == "yourco.dev"
            assert ws["name"] == "Yourco"
            assert ws["slug"] == "yourco"
            loaded = identity.actor_from_session(conn, sid)
            assert loaded is not None and loaded.user_id == actor.user_id
            assert loaded.org_id == 1

            # Duplicate setup fails
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

            # Wrong password fails login
            bad = expect(
                IdentityError,
                lambda: identity.login(conn, "ada@yourco.dev", "nope-nope"),
            )
            assert bad.status == 401

            # Login with single membership auto-binds
            again, sid2, workspaces = identity.login(conn, "ada@yourco.dev", "secretsecret")
            assert again is not None, "single membership should auto-bind"
            assert again.user_id == actor.user_id
            assert sid2 != sid
            assert len(workspaces) == 1
            assert workspaces[0]["role"] == "owner"

            # ═══════════════════════════════════════════════════════════════
            # Invites scoped to org
            # ═══════════════════════════════════════════════════════════════
            invite_id, token = identity.create_invite(
                conn, actor, email="sam@yourco.dev", role="member"
            )
            peek = identity.peek_invite(conn, token)
            assert peek["email"] == "sam@yourco.dev"
            assert peek["workspace_domain"] == "yourco.dev"
            assert peek["org_id"] == actor.org_id
            assert peek["account_exists"] is False
            assert peek["viewer"] == "anonymous"

            sam, sam_sid = identity.accept_invite(
                conn, token, password="memberpass", display_name="Sam"
            )
            assert sam.role == "member"
            assert sam.org_id == actor.org_id
            assert identity.actor_from_session(conn, sam_sid) is not None
            used = expect(IdentityError, lambda: identity.peek_invite(conn, token))
            assert used.status == 410

            members = identity.list_members(conn, actor.org_id)
            assert {m["email"] for m in members} == {
                "ada@yourco.dev",
                "sam@yourco.dev",
            }

            # Member can't invite
            forbid = expect(
                IdentityError,
                lambda: identity.create_invite(conn, sam, email="pat@yourco.dev"),
            )
            assert forbid.status == 403

            # Owner can't demote self to member (would leave no owner)
            demote = expect(
                IdentityError,
                lambda: identity.set_member_role(conn, actor, actor.user_id, "member"),
            )
            assert "owner" in str(demote).lower() or "admin" in str(demote).lower()

            # Role management
            identity.set_member_role(conn, actor, sam.user_id, "admin")
            identity.set_member_role(conn, actor, sam.user_id, "member")
            identity.remove_member(conn, actor, sam.user_id)
            left = identity.list_members(conn, actor.org_id)
            assert [m["email"] for m in left] == ["ada@yourco.dev"]
            assert identity.actor_from_session(conn, sam_sid) is None
            # Soft-remove keeps users row
            assert conn.execute(
                "SELECT id FROM users WHERE email=?", ("sam@yourco.dev",)
            ).fetchone()
            assert identity.actor_for_user(conn, sam.user_id, actor.org_id) is None

            # Re-invite after soft-remove
            invite2, token2 = identity.create_invite(
                conn, actor, email="sam@yourco.dev", role="member"
            )
            assert invite2
            row_inv = conn.execute(
                "SELECT org_id FROM invites WHERE id=?", (invite2,)
            ).fetchone()
            assert row_inv is not None and row_inv["org_id"] == actor.org_id
            _id, token2b, email2, _role = identity.resend_invite(conn, actor, invite2)
            assert email2 == "sam@yourco.dev" and token2b != token2
            sam2, sam2_sid = identity.accept_invite(
                conn, token2b, password="memberpass", display_name="Sam"
            )
            assert sam2.user_id == sam.user_id
            assert identity.actor_from_session(conn, sam2_sid) is not None
            # Re-join must not reset the existing password
            again_sam, _, _ = identity.login(conn, "sam@yourco.dev", "memberpass")
            assert again_sam is not None and again_sam.user_id == sam.user_id

            # ═══════════════════════════════════════════════════════════════
            # Password change
            # ═══════════════════════════════════════════════════════════════
            identity.change_password(
                conn,
                actor,
                current_password="secretsecret",
                new_password="secretsecret2",
            )
            again3, _, _ = identity.login(conn, "ada@yourco.dev", "secretsecret2")
            assert again3 is not None and again3.user_id == actor.user_id

            # Workspace update
            identity.update_workspace(conn, actor, name="Yourco Inc")
            renamed = identity.workspace_public(conn, actor.org_id)
            assert renamed is not None and renamed["name"] == "Yourco Inc"

            identity.logout(conn, sid2)
            assert identity.actor_from_session(conn, sid2) is None
            assert invite_id

            # ═══════════════════════════════════════════════════════════════
            # Multi-workspace: owner creates second org
            # ═══════════════════════════════════════════════════════════════
            org2_id, actor2 = identity.create_workspace(
                conn, actor.user_id, domain="acme.io", slug="acme"
            )
            app.seed_org_defaults(conn, org2_id)
            assert org2_id == 2
            assert actor2.org_id == 2
            assert actor2.is_owner
            assert actor2.user_id == actor.user_id

            ws2 = identity.workspace_public(conn, org2_id)
            assert ws2 is not None
            assert ws2["slug"] == "acme"
            assert ws2["domain"] == "acme.io"

            # Named workspace without a domain
            org3_id, actor3 = identity.create_workspace(
                conn, actor.user_id, name="Beta Co"
            )
            assert actor3.org_id == org3_id
            ws3 = identity.workspace_public(conn, org3_id)
            assert ws3 is not None
            assert ws3["name"] == "Beta Co"
            assert ws3["slug"] == "beta-co"

            # Ada now has 3 memberships
            ada_workspaces = identity.list_workspaces_for_user(conn, actor.user_id)
            assert len(ada_workspaces) == 3
            assert {w["id"] for w in ada_workspaces} == {1, 2, org3_id}

            # Login restores last workspace (org3, just created)
            multi_actor, multi_sid, multi_ws = identity.login(
                conn, "ada@yourco.dev", "secretsecret2"
            )
            assert multi_actor is not None, "last workspace should auto-bind"
            assert multi_actor.org_id == org3_id
            assert len(multi_ws) == 3
            assert identity.session_active_org_id(conn, multi_sid) == org3_id

            # No last org → picker
            conn.execute(
                "UPDATE users SET last_org_id=NULL WHERE id=?", (actor.user_id,)
            )
            pick_actor, pick_sid, pick_ws = identity.login(
                conn, "ada@yourco.dev", "secretsecret2"
            )
            assert pick_actor is None
            assert len(pick_ws) == 3
            assert identity.session_user_id(conn, pick_sid) == actor.user_id
            assert identity.session_active_org_id(conn, pick_sid) is None
            assert identity.actor_from_session(conn, pick_sid) is None

            # Switch workspace
            switched = identity.switch_workspace(conn, pick_sid, org2_id)
            assert switched.org_id == org2_id
            assert switched.is_owner
            assert identity.session_active_org_id(conn, pick_sid) == org2_id
            from_session = identity.actor_from_session(conn, pick_sid)
            assert from_session is not None
            assert from_session.org_id == org2_id
            assert identity.last_org_for_user(conn, actor.user_id) == org2_id

            # Switch back to org 1
            switched_back = identity.switch_workspace(conn, pick_sid, 1)
            assert switched_back.org_id == 1

            multi_sid = pick_sid

            # ═══════════════════════════════════════════════════════════════
            # Org isolation: Sam in org1 cannot access org2
            # ═══════════════════════════════════════════════════════════════
            # Sam is still in org1
            sam_loaded = identity.actor_from_session(conn, sam2_sid)
            assert sam_loaded is not None
            assert sam_loaded.org_id == 1

            # Sam cannot switch to org2 (no membership)
            no_access = expect(
                IdentityError,
                lambda: identity.switch_workspace(conn, sam2_sid, org2_id),
            )
            assert no_access.status == 403

            # Invite to org2 is separate from org1
            # First switch actor context to org2
            actor_org2 = identity.switch_workspace(conn, multi_sid, org2_id)
            inv_org2, tok_org2 = identity.create_invite(
                conn, actor_org2, email="bob@acme.io", role="member"
            )
            peek_org2 = identity.peek_invite(conn, tok_org2)
            assert peek_org2["org_id"] == org2_id
            assert peek_org2["workspace_domain"] == "acme.io"

            # Signed-in invitee joins without a new password
            _, tok_sam_org2 = identity.create_invite(
                conn, actor_org2, email="sam@yourco.dev", role="member"
            )
            peek_signed = identity.peek_invite(
                conn, tok_sam_org2, viewer_user_id=sam2.user_id
            )
            assert peek_signed["account_exists"] is True
            assert peek_signed["viewer"] == "invitee"
            wrong_person = expect(
                IdentityError,
                lambda: identity.accept_invite(
                    conn, tok_sam_org2, session_id=multi_sid
                ),
            )
            assert wrong_person.status == 403
            sam_join, reused_sid = identity.accept_invite(
                conn, tok_sam_org2, session_id=sam2_sid
            )
            assert sam_join.org_id == org2_id
            assert reused_sid == sam2_sid
            still_sam, _, _ = identity.login(conn, "sam@yourco.dev", "memberpass")
            assert still_sam is not None

            # ═══════════════════════════════════════════════════════════════
            # API keys scoped to org
            # ═══════════════════════════════════════════════════════════════
            # Create API key in org1
            actor_org1 = identity.switch_workspace(conn, multi_sid, 1)
            key_id, raw_key = identity.create_api_key(conn, actor_org1, "test key")
            api_actor = identity.actor_from_api_key(conn, raw_key)
            assert api_actor is not None
            assert api_actor.org_id == 1
            assert api_actor.user_id == actor.user_id

            keys = identity.list_api_keys(conn, actor_org1)
            assert len(keys) == 1
            assert keys[0]["label"] == "test key"

            # API key for org2
            key_id2, raw_key2 = identity.create_api_key(conn, actor_org2, "acme key")
            api_actor2 = identity.actor_from_api_key(conn, raw_key2)
            assert api_actor2 is not None
            assert api_actor2.org_id == org2_id

            # Keys are org-scoped
            keys_org1 = identity.list_api_keys(conn, actor_org1)
            keys_org2 = identity.list_api_keys(conn, actor_org2)
            assert len(keys_org1) == 1
            assert len(keys_org2) == 1
            assert keys_org1[0]["id"] != keys_org2[0]["id"]

            # Revoke API key
            assert identity.revoke_api_key(conn, actor_org1, key_id)
            assert identity.actor_from_api_key(conn, raw_key) is None

            # ═══════════════════════════════════════════════════════════════
            # Owner-only operations
            # ═══════════════════════════════════════════════════════════════
            # Promote Sam to admin in org1
            identity.set_member_role(conn, actor_org1, sam2.user_id, "admin")
            sam_admin = identity.actor_for_user(conn, sam2.user_id, 1)
            assert sam_admin is not None
            assert sam_admin.is_admin
            assert not sam_admin.is_owner

            # Admin cannot promote to owner
            cannot_promote = expect(
                IdentityError,
                lambda: identity.set_member_role(conn, sam_admin, sam_admin.user_id, "owner"),
            )
            assert cannot_promote.status == 403

            # Owner can promote to owner
            identity.set_member_role(conn, actor_org1, sam2.user_id, "owner")
            sam_owner = identity.actor_for_user(conn, sam2.user_id, 1)
            assert sam_owner is not None
            assert sam_owner.is_owner

            # Demote back to admin
            identity.set_member_role(conn, actor_org1, sam2.user_id, "admin")

            # Cannot invite as owner
            cannot_inv_owner = expect(
                IdentityError,
                lambda: identity.create_invite(conn, actor_org1, email="pat@yourco.dev", role="owner"),
            )
            assert "owner" in str(cannot_inv_owner).lower()

    print("ok  identity: setup, login, invite, roles, workspace, multi-org, switch, api-keys")


if __name__ == "__main__":
    main()
