"""Multi-workspace identity: people, memberships, sessions, API keys.

Mode B: multiple orgs, owner/admin/member roles, sessions track active_org_id.
No more ORG_ID=1 constant — all helpers take org_id from Actor or explicit param.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

ROLES = frozenset({"owner", "admin", "member"})
SESSION_DAYS = 30
INVITE_DAYS = 14
PASSWORD_MIN = 8
PBKDF2_ROUNDS = 120_000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")


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
    org_id: int

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
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


def slug_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if len(slug) < 3:
        slug = (slug or "ws") + "-ws"
    return slug[:40]


def derive_slug(domain: str) -> str:
    return slug_from_name(domain.split(".")[0] or domain)


def favicon(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"


def _logo_url(host: str) -> str:
    if not host or host.endswith(".local"):
        return ""
    return favicon(host)


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug = _validate_slug(base) if _SLUG_RE.match(base) else slug_from_name(base)
    candidate = slug
    n = 2
    while conn.execute("SELECT id FROM orgs WHERE slug=?", (candidate,)).fetchone():
        suffix = f"-{n}"
        candidate = slug[: max(3, 40 - len(suffix))] + suffix
        n += 1
        if n > 100:
            raise IdentityError("Could not allocate a workspace URL")
    return candidate


def _remember_org(conn: sqlite3.Connection, user_id: str, org_id: int) -> None:
    conn.execute("UPDATE users SET last_org_id=? WHERE id=?", (org_id, user_id))


def last_org_for_user(conn: sqlite3.Connection, user_id: str) -> int | None:
    """Last workspace this person used, if they still belong to it."""
    row = conn.execute(
        "SELECT last_org_id FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if row is None or row["last_org_id"] is None:
        return None
    org_id = int(row["last_org_id"])
    member = conn.execute(
        "SELECT 1 FROM memberships WHERE user_id=? AND org_id=?",
        (user_id, org_id),
    ).fetchone()
    return org_id if member else None


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
        raise IdentityError("Role must be owner, admin, or member")
    return role


def _validate_slug(slug: str) -> str:
    slug = slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise IdentityError("Slug must be 3-40 lowercase letters, numbers, hyphens")
    return slug


def _insert_session(
    conn: sqlite3.Connection, user_id: str, active_org_id: int | None
) -> str:
    session_id = secrets.token_urlsafe(32)
    now = _now()
    conn.execute(
        """INSERT INTO sessions(id, user_id, created_at, expires_at, active_org_id)
           VALUES (?,?,?,?,?)""",
        (
            session_id,
            user_id,
            _iso(now),
            _iso(now + timedelta(days=SESSION_DAYS)),
            active_org_id,
        ),
    )
    return session_id


def _actor_row(conn: sqlite3.Connection, user_id: str, org_id: int) -> Actor:
    row = conn.execute(
        """SELECT u.id, u.email, u.display_name, m.role, m.org_id
           FROM users u JOIN memberships m ON m.user_id = u.id
           WHERE u.id=? AND m.org_id=?""",
        (user_id, org_id),
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


def actor_from_session(
    conn: sqlite3.Connection, session_id: str | None
) -> Actor | None:
    if not session_id:
        return None
    row = conn.execute(
        "SELECT user_id, expires_at, active_org_id FROM sessions WHERE id=?",
        (session_id,),
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
    active_org_id = row["active_org_id"]
    if active_org_id is None:
        return None
    try:
        return _actor_row(conn, row["user_id"], active_org_id)
    except IdentityError:
        return None


def session_user_id(conn: sqlite3.Connection, session_id: str | None) -> str | None:
    """Get user_id from session even if active_org_id is null (pick_workspace state)."""
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
    return row["user_id"]


def session_active_org_id(
    conn: sqlite3.Connection, session_id: str | None
) -> int | None:
    """Get active_org_id from session (null means pick_workspace state)."""
    if not session_id:
        return None
    row = conn.execute(
        "SELECT active_org_id FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
    return row["active_org_id"] if row else None


API_KEY_PREFIX = "joel_sk_"


def create_api_key(
    conn: sqlite3.Connection, actor: Actor, label: str
) -> tuple[str, str]:
    """Create API key scoped to actor's current org."""
    key_id = _new_id("key")
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    conn.execute(
        """INSERT INTO api_keys(id, user_id, org_id, label, key_hash, key_last4, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            key_id,
            actor.user_id,
            actor.org_id,
            label.strip() or "API key",
            hash_token(raw),
            raw[-4:],
            _iso(_now()),
        ),
    )
    return key_id, raw


def list_api_keys(conn: sqlite3.Connection, actor: Actor) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT id, label, key_last4, created_at, last_used_at
           FROM api_keys WHERE user_id=? AND org_id=?
           ORDER BY created_at DESC""",
        (actor.user_id, actor.org_id),
    ).fetchall()


def revoke_api_key(conn: sqlite3.Connection, actor: Actor, key_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM api_keys WHERE id=? AND user_id=? AND org_id=?",
        (key_id, actor.user_id, actor.org_id),
    )
    return cur.rowcount > 0


def actor_from_api_key(conn: sqlite3.Connection, raw_key: str | None) -> Actor | None:
    """Resolve API key to Actor. Key is scoped to one org."""
    if not raw_key or not raw_key.startswith(API_KEY_PREFIX):
        return None
    row = conn.execute(
        "SELECT user_id, org_id FROM api_keys WHERE key_hash=?", (hash_token(raw_key),)
    ).fetchone()
    if row is None:
        return None
    try:
        actor = _actor_row(conn, row["user_id"], row["org_id"])
    except IdentityError:
        return None
    conn.execute(
        "UPDATE api_keys SET last_used_at=? WHERE key_hash=?",
        (_iso(_now()), hash_token(raw_key)),
    )
    return actor


def actor_for_user(
    conn: sqlite3.Connection, user_id: str, org_id: int
) -> Actor | None:
    """Lookup Actor for a known user_id + org_id."""
    try:
        return _actor_row(conn, user_id, org_id)
    except IdentityError:
        return None


def workspace_row(conn: sqlite3.Connection, org_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM orgs WHERE id=?", (org_id,)).fetchone()


def _create_org(
    conn: sqlite3.Connection,
    *,
    name: str | None,
    domain: str | None,
    slug: str | None,
    created_by: str | None,
) -> int:
    label = (name or "").strip()
    host = normalize_domain(domain) if domain else None
    if not label and not host:
        raise IdentityError("Enter a company name")
    if not label:
        label = derive_name(host or "")
    if slug:
        org_slug = _validate_slug(slug)
        taken = conn.execute(
            "SELECT id FROM orgs WHERE slug=?", (org_slug,)
        ).fetchone()
        if taken:
            raise IdentityError(f"Slug '{org_slug}' is already taken", status=409)
    else:
        org_slug = _unique_slug(
            conn, slug_from_name(label) if name else derive_slug(host or label)
        )
    if not host:
        host = f"{org_slug}.local"
    cur = conn.execute(
        """INSERT INTO orgs(slug, domain, name, logo_url, created_at, created_by)
           VALUES (?,?,?,?,?,?)""",
        (
            org_slug,
            host,
            label,
            _logo_url(host),
            _iso(_now()),
            created_by,
        ),
    )
    return cur.lastrowid


def setup(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    display_name: str,
    domain: str | None = None,
    company_name: str | None = None,
) -> tuple[Actor, str]:
    """First-time setup: create org + owner user. Returns (Actor, session_id)."""
    if not setup_needed(conn):
        raise IdentityError("This workspace already has an admin", status=409)
    if not (company_name or "").strip() and not domain:
        raise IdentityError("Enter a company name")
    addr = _validate_email(email)
    person = display_name.strip() or addr.split("@", 1)[0]
    user_id = _new_id("user")
    created = _iso(_now())
    conn.execute(
        """INSERT INTO users(id, email, display_name, password_hash, created_at)
           VALUES (?,?,?,?,?)""",
        (user_id, addr, person, hash_password(password), created),
    )
    org_id = _create_org(
        conn,
        name=company_name,
        domain=domain,
        slug=None,
        created_by=user_id,
    )
    conn.execute(
        """INSERT INTO memberships(user_id, org_id, role, created_at)
           VALUES (?,?, 'owner', ?)""",
        (user_id, org_id, created),
    )
    _remember_org(conn, user_id, org_id)
    actor = _actor_row(conn, user_id, org_id)
    return actor, _insert_session(conn, user_id, org_id)


def create_workspace(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    name: str | None = None,
    domain: str | None = None,
    slug: str | None = None,
    session_id: str | None = None,
) -> tuple[int, Actor]:
    """Create a new workspace. The creating user becomes owner.

    Any signed-in user may create a workspace (Plane/Cal-style). Optionally
    bind `session_id` to the new org so the caller lands inside it.
    """
    org_id = _create_org(
        conn, name=name, domain=domain, slug=slug, created_by=user_id
    )
    created = _iso(_now())
    conn.execute(
        """INSERT INTO memberships(user_id, org_id, role, created_at)
           VALUES (?,?, 'owner', ?)""",
        (user_id, org_id, created),
    )
    if session_id:
        conn.execute(
            "UPDATE sessions SET active_org_id=? WHERE id=?",
            (org_id, session_id),
        )
    _remember_org(conn, user_id, org_id)
    return org_id, _actor_row(conn, user_id, org_id)


def list_workspaces_for_user(
    conn: sqlite3.Connection, user_id: str
) -> list[dict[str, str | int]]:
    """List all workspaces user has membership in."""
    rows = conn.execute(
        """SELECT o.id, o.slug, o.domain, o.name, o.logo_url, m.role
           FROM memberships m JOIN orgs o ON o.id = m.org_id
           WHERE m.user_id=?
           ORDER BY o.name COLLATE NOCASE""",
        (user_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "slug": r["slug"],
            "domain": r["domain"],
            "name": r["name"],
            "logo_url": r["logo_url"],
            "role": r["role"],
        }
        for r in rows
    ]


def switch_workspace(
    conn: sqlite3.Connection, session_id: str, org_id: int
) -> Actor:
    """Switch session's active workspace. Returns new Actor."""
    row = conn.execute(
        "SELECT user_id FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
    if row is None:
        raise IdentityError("Session not found", status=401)
    user_id = row["user_id"]
    membership = conn.execute(
        "SELECT org_id FROM memberships WHERE user_id=? AND org_id=?",
        (user_id, org_id),
    ).fetchone()
    if membership is None:
        raise IdentityError("Not a member of this workspace", status=403)
    conn.execute("UPDATE sessions SET active_org_id=? WHERE id=?", (org_id, session_id))
    _remember_org(conn, user_id, org_id)
    return _actor_row(conn, user_id, org_id)


def login(
    conn: sqlite3.Connection, email: str, password: str
) -> tuple[Actor | None, str, list[dict[str, str | int]]]:
    """Login. Returns (actor_or_none, session_id, workspaces).

    One membership, or a remembered workspace they still belong to, binds
    the session. Otherwise active_org_id is null (pick_workspace).
    """
    addr = _validate_email(email)
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE email=?", (addr,)
    ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        raise IdentityError("Email or password is wrong", status=401)
    user_id = row["id"]
    workspaces = list_workspaces_for_user(conn, user_id)
    if not workspaces:
        raise IdentityError("No workspace membership found", status=403)
    org_id: int | None
    if len(workspaces) == 1:
        org_id = int(workspaces[0]["id"])
    else:
        org_id = last_org_for_user(conn, user_id)
    if org_id is None:
        session_id = _insert_session(conn, user_id, None)
        return None, session_id, workspaces
    actor = _actor_row(conn, user_id, org_id)
    _remember_org(conn, user_id, org_id)
    return actor, _insert_session(conn, user_id, org_id), workspaces


def logout(conn: sqlite3.Connection, session_id: str | None) -> None:
    if session_id:
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def _active_member_id(conn: sqlite3.Connection, email: str, org_id: int) -> str | None:
    row = conn.execute(
        """SELECT u.id FROM users u
           JOIN memberships m ON m.user_id = u.id AND m.org_id=?
           WHERE u.email=?""",
        (org_id, email),
    ).fetchone()
    return None if row is None else str(row["id"])


def create_invite(
    conn: sqlite3.Connection, actor: Actor, *, email: str, role: str = "member"
) -> tuple[str, str]:
    """Create invite scoped to actor's org."""
    if not actor.is_admin:
        raise IdentityError("Only an admin can invite", status=403)
    addr = _validate_email(email)
    role = _validate_role(role)
    if role == "owner":
        raise IdentityError("Cannot invite as owner — promote after joining")
    if _active_member_id(conn, addr, actor.org_id):
        raise IdentityError("That person is already in this workspace", status=409)
    pending = conn.execute(
        """SELECT id FROM invites
           WHERE org_id=? AND email=? AND accepted_at IS NULL AND expires_at>?""",
        (actor.org_id, addr, _iso(_now())),
    ).fetchone()
    if pending:
        conn.execute("DELETE FROM invites WHERE id=?", (pending["id"],))
    invite_id = _new_id("inv")
    raw = secrets.token_urlsafe(32)
    now = _now()
    conn.execute(
        """INSERT INTO invites(
             id, email, role, token_hash, created_by, created_at, expires_at, org_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            invite_id,
            addr,
            role,
            hash_token(raw),
            actor.user_id,
            _iso(now),
            _iso(now + timedelta(days=INVITE_DAYS)),
            actor.org_id,
        ),
    )
    return invite_id, raw


def resend_invite(
    conn: sqlite3.Connection, actor: Actor, invite_id: str
) -> tuple[str, str, str, str]:
    """Rotate invite token and extend expiry. Returns (id, raw, email, role)."""
    if not actor.is_admin:
        raise IdentityError("Only an admin can resend an invite", status=403)
    row = conn.execute(
        """SELECT id, email, role, expires_at FROM invites
           WHERE id=? AND org_id=? AND accepted_at IS NULL""",
        (invite_id, actor.org_id),
    ).fetchone()
    if row is None:
        raise IdentityError("Invite not found", status=404)
    if parse_iso(row["expires_at"]) <= _now():
        raise IdentityError("This invite has expired — create a new one", status=410)
    raw = secrets.token_urlsafe(32)
    now = _now()
    conn.execute(
        """UPDATE invites
           SET token_hash=?, expires_at=?, created_by=?
           WHERE id=?""",
        (
            hash_token(raw),
            _iso(now + timedelta(days=INVITE_DAYS)),
            actor.user_id,
            invite_id,
        ),
    )
    return str(row["id"]), raw, str(row["email"]), str(row["role"])


def peek_invite(
    conn: sqlite3.Connection,
    raw_token: str,
    *,
    viewer_user_id: str | None = None,
) -> dict[str, str | int | bool]:
    """Peek at invite by token. Returns invite details including org_id."""
    row = conn.execute(
        """SELECT i.email, i.role, i.expires_at, i.accepted_at, i.org_id,
                  o.name, o.domain, o.logo_url
           FROM invites i JOIN orgs o ON o.id = i.org_id
           WHERE i.token_hash=?""",
        (hash_token(raw_token.strip()),),
    ).fetchone()
    if row is None:
        raise IdentityError("Invite not found", status=404)
    if row["accepted_at"]:
        raise IdentityError("This invite was already used", status=410)
    if parse_iso(row["expires_at"]) <= _now():
        raise IdentityError("This invite has expired", status=410)
    existing = conn.execute(
        "SELECT id FROM users WHERE email=?", (row["email"],)
    ).fetchone()
    viewer = "anonymous"
    if viewer_user_id:
        who = conn.execute(
            "SELECT email FROM users WHERE id=?", (viewer_user_id,)
        ).fetchone()
        if who and who["email"] == row["email"]:
            viewer = "invitee"
        elif who:
            viewer = "other"
    return {
        "email": row["email"],
        "role": row["role"],
        "org_id": row["org_id"],
        "workspace_name": row["name"],
        "workspace_domain": row["domain"],
        "workspace_logo_url": row["logo_url"] or "",
        "account_exists": existing is not None,
        "viewer": viewer,
    }


def pending_invite_for_email(
    conn: sqlite3.Connection, org_id: int, email: str
) -> dict[str, str] | None:
    """Open invite for this email in this org, or None. Never creates anything."""
    addr = normalize_email(email)
    if not addr:
        return None
    row = conn.execute(
        """SELECT id, email, role, expires_at FROM invites
           WHERE org_id=? AND email=? AND accepted_at IS NULL AND expires_at>?""",
        (org_id, addr, _iso(_now())),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row["id"]),
        "email": str(row["email"]),
        "role": str(row["role"]),
        "expires_at": str(row["expires_at"]),
    }


def _join_from_invite_row(
    conn: sqlite3.Connection,
    *,
    org_id: int,
    invite_id: str,
    invite_email: str,
    role: str,
    password: str | None,
    display_name: str,
    session_user: str | None,
    allow_unauthenticated_existing: bool,
) -> tuple[Actor, str | None]:
    """Shared membership insert for /join and Connect-me.

    Returns (actor, reuse_session_hint). reuse_session_hint is the user_id when
    the caller may keep an existing session cookie; None means mint a new one
    (or skip session for Slack-only accept).
    """
    if _active_member_id(conn, invite_email, org_id):
        raise IdentityError("That person is already in this workspace", status=409)

    existing = conn.execute(
        "SELECT id, email, display_name, password_hash FROM users WHERE email=?",
        (invite_email,),
    ).fetchone()
    created = _iso(_now())
    reuse_session = False

    if existing:
        user_id = str(existing["id"])
        if session_user and session_user != user_id:
            raise IdentityError(
                f"This invite is for {invite_email}. Sign out to continue.",
                status=403,
            )
        if session_user == user_id:
            reuse_session = True
        elif password:
            if not verify_password(password, existing["password_hash"]):
                raise IdentityError("Email or password is wrong", status=401)
        elif not allow_unauthenticated_existing:
            raise IdentityError("Sign in to join this workspace", status=401)
        name = display_name.strip()
        if name:
            conn.execute(
                "UPDATE users SET display_name=? WHERE id=?", (name, user_id)
            )
    else:
        if session_user:
            raise IdentityError(
                f"This invite is for {invite_email}. Sign out to continue.",
                status=403,
            )
        if not password:
            raise IdentityError("Password is required")
        user_id = _new_id("user")
        name = display_name.strip() or invite_email.split("@", 1)[0]
        try:
            conn.execute(
                """INSERT INTO users(id, email, display_name, password_hash, created_at)
                   VALUES (?,?,?,?,?)""",
                (user_id, invite_email, name, hash_password(password), created),
            )
        except sqlite3.IntegrityError as extra:
            raise IdentityError(
                "That person is already in this workspace", status=409
            ) from extra

    conn.execute(
        """INSERT INTO memberships(user_id, org_id, role, created_at)
           VALUES (?,?,?,?)""",
        (user_id, org_id, role, created),
    )
    conn.execute(
        "UPDATE invites SET accepted_at=? WHERE id=?",
        (created, invite_id),
    )
    _remember_org(conn, user_id, org_id)
    actor = _actor_row(conn, user_id, org_id)
    return actor, (user_id if reuse_session else None)


def accept_invite(
    conn: sqlite3.Connection,
    raw_token: str,
    *,
    password: str | None = None,
    display_name: str = "",
    session_id: str | None = None,
) -> tuple[Actor, str]:
    """Accept invite. Never resets an existing password.

    New person: password + name creates the account.
    Existing person, signed in as the invitee: just join.
    Existing person, not signed in: current password proves the account.
    """
    peek = peek_invite(conn, raw_token)
    org_id = int(peek["org_id"])
    invite_email = str(peek["email"])
    invite_row = conn.execute(
        "SELECT id, role FROM invites WHERE token_hash=? AND accepted_at IS NULL",
        (hash_token(raw_token.strip()),),
    ).fetchone()
    if invite_row is None:
        raise IdentityError("Invite not found", status=404)

    session_user = session_user_id(conn, session_id) if session_id else None
    actor, reuse_user = _join_from_invite_row(
        conn,
        org_id=org_id,
        invite_id=str(invite_row["id"]),
        invite_email=invite_email,
        role=str(invite_row["role"]),
        password=password,
        display_name=display_name,
        session_user=session_user,
        allow_unauthenticated_existing=False,
    )
    if reuse_user and session_id:
        conn.execute(
            "UPDATE sessions SET active_org_id=? WHERE id=?",
            (org_id, session_id),
        )
        return actor, session_id
    return actor, _insert_session(conn, actor.user_id, org_id)


def accept_invite_from_slack(
    conn: sqlite3.Connection,
    org_id: int,
    email: str,
    *,
    display_name: str = "",
) -> Actor:
    """Connect-me: consume a pending invite for this Slack profile email.

    No password form. New accounts get a random unusable password hash —
    Slack answers work; web login waits for passwordless. Idempotent if
    already a member. Unknown / uninvited emails raise (caller stays silent
    or shows an error on the button, never auto-creates).
    """
    addr = _validate_email(email)
    existing_id = _active_member_id(conn, addr, org_id)
    if existing_id:
        return actor_for_user(conn, existing_id, org_id)

    invite = pending_invite_for_email(conn, org_id, addr)
    if invite is None:
        raise IdentityError("No pending invite for this email", status=404)

    already = conn.execute(
        "SELECT id FROM users WHERE email=?", (addr,)
    ).fetchone()
    # Existing account: prove identity via Slack email match, not password.
    # Brand-new: random hash so the row satisfies NOT NULL; web login waits.
    password = None if already else secrets.token_urlsafe(32)

    actor, _ = _join_from_invite_row(
        conn,
        org_id=org_id,
        invite_id=invite["id"],
        invite_email=invite["email"],
        role=invite["role"],
        password=password,
        display_name=display_name,
        session_user=None,
        allow_unauthenticated_existing=True,
    )
    return actor


def list_members(conn: sqlite3.Connection, org_id: int) -> list[dict[str, str]]:
    rows = conn.execute(
        """SELECT u.id, u.email, u.display_name, m.role, m.created_at
           FROM memberships m JOIN users u ON u.id = m.user_id
           WHERE m.org_id=?
           ORDER BY
             CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,
             u.display_name COLLATE NOCASE ASC""",
        (org_id,),
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


def list_invites(conn: sqlite3.Connection, org_id: int) -> list[dict[str, str | None]]:
    rows = conn.execute(
        """SELECT id, email, role, created_at, expires_at, accepted_at
           FROM invites
           WHERE org_id=? AND accepted_at IS NULL AND expires_at>?
           ORDER BY created_at DESC""",
        (org_id, _iso(_now())),
    ).fetchall()
    return [dict(r) for r in rows]


def revoke_invite(conn: sqlite3.Connection, actor: Actor, invite_id: str) -> None:
    if not actor.is_admin:
        raise IdentityError("Only an admin can revoke an invite", status=403)
    row = conn.execute(
        "SELECT id FROM invites WHERE id=? AND org_id=? AND accepted_at IS NULL",
        (invite_id, actor.org_id),
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
        (user_id, actor.org_id),
    ).fetchone()
    if target is None:
        raise IdentityError("Member not found", status=404)
    if target["role"] == "owner" and not actor.is_owner:
        raise IdentityError("Only an owner can change another owner's role", status=403)
    if role == "owner" and not actor.is_owner:
        raise IdentityError("Only an owner can promote to owner", status=403)
    if user_id == actor.user_id and actor.is_owner and role != "owner":
        owners = conn.execute(
            "SELECT COUNT(*) AS n FROM memberships WHERE org_id=? AND role='owner'",
            (actor.org_id,),
        ).fetchone()["n"]
        if owners <= 1:
            raise IdentityError("Keep at least one owner")
    if user_id == actor.user_id and role not in ("owner", "admin"):
        raise IdentityError("You can't demote yourself below admin")
    if target["role"] in ("owner", "admin") and role == "member":
        admins = conn.execute(
            "SELECT COUNT(*) AS n FROM memberships WHERE org_id=? AND role IN ('owner', 'admin')",
            (actor.org_id,),
        ).fetchone()["n"]
        if admins <= 1:
            raise IdentityError("Keep at least one admin")
    conn.execute(
        "UPDATE memberships SET role=? WHERE user_id=? AND org_id=?",
        (role, user_id, actor.org_id),
    )


def remove_member(conn: sqlite3.Connection, actor: Actor, user_id: str) -> None:
    """Soft-remove member from actor's org. Keeps user row for audit/re-invite."""
    if not actor.is_admin:
        raise IdentityError("Only an admin can remove a member", status=403)
    if user_id == actor.user_id:
        raise IdentityError("You can't remove yourself")
    target = conn.execute(
        "SELECT role FROM memberships WHERE user_id=? AND org_id=?",
        (user_id, actor.org_id),
    ).fetchone()
    if target is None:
        raise IdentityError("Member not found", status=404)
    if target["role"] == "owner" and not actor.is_owner:
        raise IdentityError("Only an owner can remove another owner", status=403)
    if target["role"] in ("owner", "admin"):
        admins = conn.execute(
            "SELECT COUNT(*) AS n FROM memberships WHERE org_id=? AND role IN ('owner', 'admin')",
            (actor.org_id,),
        ).fetchone()["n"]
        if admins <= 1:
            raise IdentityError("Keep at least one admin")
    conn.execute(
        "DELETE FROM sessions WHERE user_id=? AND active_org_id=?",
        (user_id, actor.org_id),
    )
    conn.execute(
        "DELETE FROM api_keys WHERE user_id=? AND org_id=?",
        (user_id, actor.org_id),
    )
    conn.execute(
        "DELETE FROM connections WHERE owned_by=? AND org_id=?",
        (user_id, actor.org_id),
    )
    conn.execute(
        "DELETE FROM memberships WHERE user_id=? AND org_id=?",
        (user_id, actor.org_id),
    )


def change_password(
    conn: sqlite3.Connection,
    actor: Actor,
    *,
    current_password: str,
    new_password: str,
) -> None:
    row = conn.execute(
        "SELECT password_hash FROM users WHERE id=?", (actor.user_id,)
    ).fetchone()
    if row is None or not verify_password(current_password, row["password_hash"]):
        raise IdentityError("Current password is wrong", status=401)
    conn.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        (hash_password(new_password), actor.user_id),
    )


def update_display_name(
    conn: sqlite3.Connection, actor: Actor, display_name: str
) -> None:
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
    row = workspace_row(conn, actor.org_id)
    if row is None:
        raise IdentityError("Workspace not found", status=404)
    host = row["domain"]
    label = row["name"]
    if domain is not None:
        host = normalize_domain(domain)
        label = derive_name(host) if name is None else label
    if name is not None:
        label = name.strip() or derive_name(host)
    conn.execute(
        "UPDATE orgs SET domain=?, name=?, logo_url=? WHERE id=?",
        (host, label, favicon(host), actor.org_id),
    )


def workspace_public(conn: sqlite3.Connection, org_id: int) -> dict[str, str] | None:
    row = workspace_row(conn, org_id)
    if row is None:
        return None
    return {
        "id": str(row["id"]),
        "slug": row["slug"] or "",
        "domain": row["domain"],
        "name": row["name"],
        "logo_url": row["logo_url"],
        "created_at": row["created_at"],
        "created_by": row["created_by"] or "",
    }


def actor_dict(actor: Actor) -> dict[str, str | bool]:
    return {
        "id": actor.user_id,
        "email": actor.email,
        "display_name": actor.display_name,
        "role": actor.role,
        "is_admin": actor.is_admin,
        "is_owner": actor.is_owner,
    }


__all__ = [
    "Actor",
    "INVITE_DAYS",
    "IdentityError",
    "ROLES",
    "SESSION_DAYS",
    "accept_invite",
    "accept_invite_from_slack",
    "actor_dict",
    "pending_invite_for_email",
    "actor_for_user",
    "actor_from_api_key",
    "actor_from_session",
    "create_api_key",
    "create_invite",
    "create_workspace",
    "change_password",
    "derive_slug",
    "favicon",
    "last_org_for_user",
    "list_api_keys",
    "list_invites",
    "list_members",
    "list_workspaces_for_user",
    "login",
    "logout",
    "normalize_domain",
    "peek_invite",
    "remove_member",
    "resend_invite",
    "revoke_api_key",
    "revoke_invite",
    "session_active_org_id",
    "session_user_id",
    "set_member_role",
    "setup",
    "setup_needed",
    "switch_workspace",
    "update_display_name",
    "update_workspace",
    "user_count",
    "workspace_public",
    "workspace_row",
]
