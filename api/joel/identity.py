"""People, membership, and sessions for one self-hosted workspace.

The workspace *is* the `orgs` row (still id=1). This module does not know
about FastAPI, cookies, or connectors — callers pass a SQLite connection
and get an Actor back.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

ORG_ID = 1
ROLES = frozenset({"admin", "member"})
SESSION_DAYS = 30
INVITE_DAYS = 14
PASSWORD_MIN = 8
PBKDF2_ROUNDS = 120_000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class IdentityError(ValueError):
    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Actor:
    user_id: str
    email: str
    display_name: str
    role: str
    org_id: int = ORG_ID

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # A naive result (no offset in `value`) would otherwise crash any
    # comparison against `_now()`'s aware datetime with a TypeError instead
    # of a clean 401 -- every stored timestamp in this module goes through
    # `_iso(_now())` and is always aware, but this keeps a malformed row
    # from 500ing every authenticated request.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_domain(raw: str) -> str:
    domain = (
        raw.strip()
        .removeprefix("https://")
        .removeprefix("http://")
        .split("/")[0]
        .lower()
        .removeprefix("www.")
    )
    if "." not in domain:
        raise IdentityError("Enter a domain like yourco.dev")
    return domain


def derive_name(domain: str) -> str:
    base = domain.split(".")[0] or domain
    return base[:1].upper() + base[1:]


def favicon(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def hash_password(password: str) -> str:
    if len(password) < PASSWORD_MIN:
        raise IdentityError(f"Password must be at least {PASSWORD_MIN} characters")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds_s, salt, digest = stored.split("$", 3)
        rounds = int(rounds_s)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    check = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), rounds
    ).hex()
    return hmac.compare_digest(check, digest)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def user_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


def setup_needed(conn: sqlite3.Connection) -> bool:
    return user_count(conn) == 0


def _validate_email(email: str) -> str:
    value = normalize_email(email)
    if not _EMAIL_RE.match(value):
        raise IdentityError("Enter a valid email")
    return value


def _validate_role(role: str) -> str:
    if role not in ROLES:
        raise IdentityError("Role must be admin or member")
    return role


def _insert_session(conn: sqlite3.Connection, user_id: str) -> str:
    session_id = secrets.token_urlsafe(32)
    now = _now()
    conn.execute(
        """INSERT INTO sessions(id, user_id, created_at, expires_at)
           VALUES (?,?,?,?)""",
        (
            session_id,
            user_id,
            _iso(now),
            _iso(now + timedelta(days=SESSION_DAYS)),
        ),
    )
    return session_id


def _actor_row(conn: sqlite3.Connection, user_id: str) -> Actor:
    row = conn.execute(
        """SELECT u.id, u.email, u.display_name, m.role, m.org_id
           FROM users u JOIN memberships m ON m.user_id = u.id
           WHERE u.id=? AND m.org_id=?""",
        (user_id, ORG_ID),
    ).fetchone()
    if row is None:
        raise IdentityError("Not a member of this workspace", status=403)
    return Actor(
        user_id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        role=row["role"],
        org_id=row["org_id"],
    )


def actor_from_session(conn: sqlite3.Connection, session_id: str | None) -> Actor | None:
    if not session_id:
        return None
    row = conn.execute(
        "SELECT user_id, expires_at FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
    if row is None:
        return None
    try:
        expires = parse_iso(row["expires_at"])
    except ValueError:
        return None
    if expires <= _now():
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        return None
    try:
        return _actor_row(conn, row["user_id"])
    except IdentityError:
        return None


API_KEY_PREFIX = "joel_sk_"


def create_api_key(conn: sqlite3.Connection, user_id: str, label: str) -> tuple[str, str]:
    """MCP identity (§0.3's "API keys — not built"): a key maps to exactly
    ONE person's normal Actor, so a request made with it gets that
    person's normal permissions through the exact same AskContext/
    allowed_stamps machinery every other surface uses -- no separate
    privilege model to keep in sync. The raw key is returned ONCE; only
    its hash is ever stored, same as `hash_token` already does for invite
    tokens."""
    key_id = _new_id("key")
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    conn.execute(
        """INSERT INTO api_keys(id, user_id, label, key_hash, key_last4, created_at)
           VALUES (?,?,?,?,?,?)""",
        (key_id, user_id, label.strip() or "API key", hash_token(raw), raw[-4:], _iso(_now())),
    )
    return key_id, raw


def list_api_keys(conn: sqlite3.Connection, user_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, label, key_last4, created_at, last_used_at FROM api_keys WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()


def revoke_api_key(conn: sqlite3.Connection, user_id: str, key_id: str) -> bool:
    cur = conn.execute("DELETE FROM api_keys WHERE id=? AND user_id=?", (key_id, user_id))
    return cur.rowcount > 0


def actor_from_api_key(conn: sqlite3.Connection, raw_key: str | None) -> Actor | None:
    """Same shape as `actor_from_session`, keyed by a hashed bearer token
    instead of a cookie -- the MCP surface's identity path (§13's third
    tier of surfaces, alongside web and, eventually, Slack)."""
    if not raw_key or not raw_key.startswith(API_KEY_PREFIX):
        return None
    row = conn.execute(
        "SELECT user_id FROM api_keys WHERE key_hash=?", (hash_token(raw_key),)
    ).fetchone()
    if row is None:
        return None
    try:
        actor = _actor_row(conn, row["user_id"])
    except IdentityError:
        return None
    conn.execute("UPDATE api_keys SET last_used_at=? WHERE key_hash=?", (_iso(_now()), hash_token(raw_key)))
    return actor


def actor_for_user(conn: sqlite3.Connection, user_id: str) -> Actor | None:
    """Same lookup `actor_from_session`/`actor_from_api_key` both use
    internally, for a caller that already resolved a raw user_id by some
    other means (the Slack bot surface matching a mentioning Slack
    user's email to a workspace member) and just needs the Actor."""
    try:
        return _actor_row(conn, user_id)
    except IdentityError:
        return None


def workspace_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM orgs WHERE id=?", (ORG_ID,)).fetchone()


def _ensure_workspace(
    conn: sqlite3.Connection, domain: str | None, created_by: str | None
) -> None:
    existing = workspace_row(conn)
    if existing is not None:
        if created_by and not existing["created_by"]:
            conn.execute(
                "UPDATE orgs SET created_by=? WHERE id=?", (created_by, ORG_ID)
            )
        return
    if not domain:
        raise IdentityError("Enter a domain like yourco.dev")
    host = normalize_domain(domain)
    conn.execute(
        """INSERT INTO orgs(id, domain, name, logo_url, created_at, created_by)
           VALUES (?,?,?,?,?,?)""",
        (
            ORG_ID,
            host,
            derive_name(host),
            favicon(host),
            _iso(_now()),
            created_by,
        ),
    )


def setup(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    display_name: str,
    domain: str | None,
) -> tuple[Actor, str]:
    if not setup_needed(conn):
        raise IdentityError("This workspace already has an admin", status=409)
    addr = _validate_email(email)
    name = display_name.strip() or addr.split("@", 1)[0]
    user_id = _new_id("user")
    created = _iso(_now())
    conn.execute(
        """INSERT INTO users(id, email, display_name, password_hash, created_at)
           VALUES (?,?,?,?,?)""",
        (user_id, addr, name, hash_password(password), created),
    )
    _ensure_workspace(conn, domain, user_id)
    if workspace_row(conn) is None:
        raise IdentityError("Enter a domain like yourco.dev")
    conn.execute(
        """INSERT INTO memberships(user_id, org_id, role, created_at)
           VALUES (?,?, 'admin', ?)""",
        (user_id, ORG_ID, created),
    )
    conn.execute(
        "UPDATE orgs SET created_by=? WHERE id=? AND (created_by IS NULL OR created_by='')",
        (user_id, ORG_ID),
    )
    actor = _actor_row(conn, user_id)
    return actor, _insert_session(conn, user_id)


def login(conn: sqlite3.Connection, email: str, password: str) -> tuple[Actor, str]:
    addr = _validate_email(email)
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE email=?", (addr,)
    ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        raise IdentityError("Email or password is wrong", status=401)
    actor = _actor_row(conn, row["id"])
    return actor, _insert_session(conn, actor.user_id)


def logout(conn: sqlite3.Connection, session_id: str | None) -> None:
    if session_id:
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def create_invite(
    conn: sqlite3.Connection, actor: Actor, *, email: str, role: str = "member"
) -> tuple[str, str]:
    if not actor.is_admin:
        raise IdentityError("Only an admin can invite", status=403)
    addr = _validate_email(email)
    role = _validate_role(role)
    existing = conn.execute("SELECT id FROM users WHERE email=?", (addr,)).fetchone()
    if existing:
        raise IdentityError("That person is already in this workspace", status=409)
    pending = conn.execute(
        """SELECT id FROM invites
           WHERE email=? AND accepted_at IS NULL AND expires_at>?""",
        (addr, _iso(_now())),
    ).fetchone()
    if pending:
        conn.execute("DELETE FROM invites WHERE id=?", (pending["id"],))
    invite_id = _new_id("inv")
    raw = secrets.token_urlsafe(32)
    now = _now()
    conn.execute(
        """INSERT INTO invites(
             id, email, role, token_hash, created_by, created_at, expires_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            invite_id,
            addr,
            role,
            hash_token(raw),
            actor.user_id,
            _iso(now),
            _iso(now + timedelta(days=INVITE_DAYS)),
        ),
    )
    return invite_id, raw


def peek_invite(conn: sqlite3.Connection, raw_token: str) -> dict[str, str]:
    row = conn.execute(
        """SELECT i.email, i.role, i.expires_at, i.accepted_at, o.name, o.domain
           FROM invites i JOIN orgs o ON o.id=?
           WHERE i.token_hash=?""",
        (ORG_ID, hash_token(raw_token.strip())),
    ).fetchone()
    if row is None:
        raise IdentityError("Invite not found", status=404)
    if row["accepted_at"]:
        raise IdentityError("This invite was already used", status=410)
    if parse_iso(row["expires_at"]) <= _now():
        raise IdentityError("This invite has expired", status=410)
    return {
        "email": row["email"],
        "role": row["role"],
        "workspace_name": row["name"],
        "workspace_domain": row["domain"],
    }


def accept_invite(
    conn: sqlite3.Connection,
    raw_token: str,
    *,
    password: str,
    display_name: str,
) -> tuple[Actor, str]:
    peek = peek_invite(conn, raw_token)
    user_id = _new_id("user")
    name = display_name.strip() or peek["email"].split("@", 1)[0]
    created = _iso(_now())
    try:
        conn.execute(
            """INSERT INTO users(id, email, display_name, password_hash, created_at)
               VALUES (?,?,?,?,?)""",
            (user_id, peek["email"], name, hash_password(password), created),
        )
    except sqlite3.IntegrityError as exc:
        raise IdentityError("That person is already in this workspace", status=409) from exc
    conn.execute(
        """INSERT INTO memberships(user_id, org_id, role, created_at)
           VALUES (?,?,?,?)""",
        (user_id, ORG_ID, peek["role"], created),
    )
    conn.execute(
        "UPDATE invites SET accepted_at=? WHERE token_hash=?",
        (created, hash_token(raw_token.strip())),
    )
    actor = _actor_row(conn, user_id)
    return actor, _insert_session(conn, user_id)


def list_members(conn: sqlite3.Connection) -> list[dict[str, str]]:
    rows = conn.execute(
        """SELECT u.id, u.email, u.display_name, m.role, m.created_at
           FROM memberships m JOIN users u ON u.id = m.user_id
           WHERE m.org_id=?
           ORDER BY m.role ASC, u.display_name COLLATE NOCASE ASC""",
        (ORG_ID,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "email": r["email"],
            "display_name": r["display_name"],
            "role": r["role"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def list_invites(conn: sqlite3.Connection) -> list[dict[str, str | None]]:
    rows = conn.execute(
        """SELECT id, email, role, created_at, expires_at, accepted_at
           FROM invites
           WHERE accepted_at IS NULL AND expires_at>?
           ORDER BY created_at DESC""",
        (_iso(_now()),),
    ).fetchall()
    return [dict(r) for r in rows]


def revoke_invite(conn: sqlite3.Connection, actor: Actor, invite_id: str) -> None:
    if not actor.is_admin:
        raise IdentityError("Only an admin can revoke an invite", status=403)
    row = conn.execute(
        "SELECT id FROM invites WHERE id=? AND accepted_at IS NULL", (invite_id,)
    ).fetchone()
    if row is None:
        raise IdentityError("Invite not found", status=404)
    conn.execute("DELETE FROM invites WHERE id=?", (invite_id,))


def set_member_role(
    conn: sqlite3.Connection, actor: Actor, user_id: str, role: str
) -> None:
    if not actor.is_admin:
        raise IdentityError("Only an admin can change roles", status=403)
    role = _validate_role(role)
    target = conn.execute(
        "SELECT role FROM memberships WHERE user_id=? AND org_id=?",
        (user_id, ORG_ID),
    ).fetchone()
    if target is None:
        raise IdentityError("Member not found", status=404)
    if user_id == actor.user_id and role != "admin":
        raise IdentityError("You can’t demote yourself")
    if target["role"] == "admin" and role != "admin":
        admins = conn.execute(
            "SELECT COUNT(*) AS n FROM memberships WHERE org_id=? AND role='admin'",
            (ORG_ID,),
        ).fetchone()["n"]
        if admins <= 1:
            raise IdentityError("Keep at least one admin")
    conn.execute(
        "UPDATE memberships SET role=? WHERE user_id=? AND org_id=?",
        (role, user_id, ORG_ID),
    )


def remove_member(conn: sqlite3.Connection, actor: Actor, user_id: str) -> None:
    if not actor.is_admin:
        raise IdentityError("Only an admin can remove a member", status=403)
    if user_id == actor.user_id:
        raise IdentityError("You can’t remove yourself")
    target = conn.execute(
        "SELECT role FROM memberships WHERE user_id=? AND org_id=?",
        (user_id, ORG_ID),
    ).fetchone()
    if target is None:
        raise IdentityError("Member not found", status=404)
    if target["role"] == "admin":
        admins = conn.execute(
            "SELECT COUNT(*) AS n FROM memberships WHERE org_id=? AND role='admin'",
            (ORG_ID,),
        ).fetchone()["n"]
        if admins <= 1:
            raise IdentityError("Keep at least one admin")
    conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    conn.execute(
        "DELETE FROM memberships WHERE user_id=? AND org_id=?", (user_id, ORG_ID)
    )
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))


def update_display_name(conn: sqlite3.Connection, actor: Actor, display_name: str) -> None:
    name = display_name.strip() or actor.email.split("@", 1)[0]
    conn.execute("UPDATE users SET display_name=? WHERE id=?", (name, actor.user_id))


def update_workspace(
    conn: sqlite3.Connection,
    actor: Actor,
    *,
    domain: str | None = None,
    name: str | None = None,
) -> None:
    if not actor.is_admin:
        raise IdentityError("Only an admin can change the workspace", status=403)
    row = workspace_row(conn)
    if row is None:
        raise IdentityError("Workspace not created yet", status=404)
    host = row["domain"]
    label = row["name"]
    if domain is not None:
        host = normalize_domain(domain)
        label = derive_name(host) if name is None else label
    if name is not None:
        label = name.strip() or derive_name(host)
    conn.execute(
        "UPDATE orgs SET domain=?, name=?, logo_url=? WHERE id=?",
        (host, label, favicon(host), ORG_ID),
    )


def workspace_public(conn: sqlite3.Connection) -> dict[str, str] | None:
    row = workspace_row(conn)
    if row is None:
        return None
    return {
        "id": str(row["id"]),
        "domain": row["domain"],
        "name": row["name"],
        "logo_url": row["logo_url"],
        "created_at": row["created_at"],
        "created_by": row["created_by"] or "",
    }


def actor_dict(actor: Actor) -> dict[str, str]:
    return {
        "id": actor.user_id,
        "email": actor.email,
        "display_name": actor.display_name,
        "role": actor.role,
    }


__all__ = [
    "Actor",
    "INVITE_DAYS",
    "IdentityError",
    "ORG_ID",
    "SESSION_DAYS",
    "accept_invite",
    "actor_dict",
    "actor_for_user",
    "actor_from_api_key",
    "actor_from_session",
    "create_api_key",
    "create_invite",
    "favicon",
    "list_api_keys",
    "list_invites",
    "list_members",
    "login",
    "logout",
    "normalize_domain",
    "peek_invite",
    "remove_member",
    "revoke_api_key",
    "revoke_invite",
    "set_member_role",
    "setup",
    "setup_needed",
    "update_display_name",
    "update_workspace",
    "user_count",
    "workspace_public",
    "workspace_row",
]
