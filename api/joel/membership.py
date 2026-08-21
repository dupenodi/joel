"""§1.4's channel-membership groundwork: matching Slack channel members to
workspace Actors by email — the same signal Gmail visibility already uses
(§0.3: "Gmail is visible on web only when the mailbox matches the actor's
workspace email") — so a desk/DM can read the private rooms the actor is
actually in, closing the literal gap the plan calls out by name: "web
cannot yet include channel:slack:… even for people who are in that Slack
room."
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from joel.connectors.slack import SlackClient
from joel.visibility import Visibility


def sync_slack_channel_memberships(
    conn: sqlite3.Connection,
    *,
    channel_ids: list[str],
    token: str = "",
    caller: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    now: str,
    org_id: int = 1,
) -> int:
    """For every configured channel, fetch its member Slack user ids, match
    them against workspace users by email, and upsert `channel_memberships`
    rows. Returns the number written. Best-effort: a member whose email
    isn't visible to this token's scopes, or doesn't match any workspace
    user, is silently skipped — there's no ambiguity to resolve, just
    nothing to record for that member."""
    if not channel_ids:
        return 0
    client = SlackClient(token, caller=caller)
    slack_emails = client.user_emails()
    if not slack_emails:
        return 0
    workspace_users = {
        str(row["email"]).strip().lower(): row["id"]
        for row in conn.execute(
            """SELECT u.id, u.email FROM users u
               JOIN memberships m ON m.user_id = u.id AND m.org_id=?""",
            (org_id,),
        )
    }
    if not workspace_users:
        return 0

    written = 0
    for channel_id in channel_ids:
        for member_id in client.channel_member_ids(channel_id):
            email = slack_emails.get(member_id)
            user_id = workspace_users.get(email) if email else None
            if not user_id:
                continue
            conn.execute(
                """INSERT INTO channel_memberships(org_id, user_id, provider, channel_id, updated_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(org_id, user_id, provider, channel_id)
                   DO UPDATE SET updated_at=excluded.updated_at""",
                (org_id, user_id, "slack", channel_id, now),
            )
            written += 1
    return written


def member_channel_stamps(
    conn: sqlite3.Connection, user_id: str, *, org_id: int = 1
) -> frozenset[str]:
    """Every `channel:{provider}:{id}` visibility stamp this actor is a
    member of — feeds `AskContext.web`'s `channels` set directly."""
    rows = conn.execute(
        "SELECT provider, channel_id FROM channel_memberships WHERE user_id=? AND org_id=?",
        (user_id, org_id),
    ).fetchall()
    return frozenset(Visibility.channel(r["provider"], r["channel_id"]).stamp for r in rows)


def mailbox_stamps(
    conn: sqlite3.Connection, user_id: str, *, org_id: int = 1
) -> frozenset[str]:
    """Every `user:{provider}:{mailbox}` stamp this actor may read.

    A mailbox is private to the person who connected it, not to whoever
    happens to share its name. The read side used to derive this stamp from
    the actor's workspace email, which silently assumed a person's login and
    their connected mailbox were the same string — so anyone whose work
    address differed from their personal Gmail lost access to the mail they
    had just connected.

    The authorising user is the one who gets the stamp: `owned_by` for a
    personal connection, `connected_by` for an org-scoped one. Being an
    admin of the workspace does not grant it; nobody inherits somebody
    else's inbox by role.
    """
    rows = conn.execute(
        """SELECT provider, account_id FROM connections
           WHERE org_id=? AND account_id IS NOT NULL AND account_id != ''
             AND (owned_by=? OR (owned_by IS NULL AND connected_by=?))""",
        (org_id, user_id, user_id),
    ).fetchall()
    return frozenset(
        Visibility.user(r["provider"], str(r["account_id"]).strip().lower()).stamp
        for r in rows
    )


__all__ = [
    "sync_slack_channel_memberships",
    "member_channel_stamps",
    "mailbox_stamps",
]
