-- Mode B multi-workspace: multiple orgs, owner role, sessions track active_org_id,
-- settings keyed by (org_id, key), org_id on all tenant tables.
-- PRAGMA foreign_keys must be toggled OUTSIDE transactions.
PRAGMA foreign_keys=OFF;

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════
-- orgs: drop CHECK(id=1), add slug UNIQUE
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE orgs_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE,
  domain TEXT NOT NULL,
  name TEXT NOT NULL,
  logo_url TEXT NOT NULL,
  created_at TEXT NOT NULL,
  created_by TEXT
);

INSERT INTO orgs_new(id, slug, domain, name, logo_url, created_at, created_by)
SELECT id, lower(replace(domain, '.', '-')), domain, name, logo_url, created_at, created_by
FROM orgs;

DROP TABLE orgs;
ALTER TABLE orgs_new RENAME TO orgs;

-- ═══════════════════════════════════════════════════════════════════════════
-- memberships: add 'owner' role, promote first admin to owner
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE memberships_new (
  user_id TEXT NOT NULL,
  org_id INTEGER NOT NULL DEFAULT 1,
  role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, org_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(org_id) REFERENCES orgs(id) ON DELETE CASCADE
);

INSERT INTO memberships_new(user_id, org_id, role, created_at)
SELECT user_id, org_id, role, created_at FROM memberships;

DROP TABLE memberships;
ALTER TABLE memberships_new RENAME TO memberships;

-- Promote first admin (by created_at) in each org to owner
UPDATE memberships SET role = 'owner'
WHERE rowid IN (
  SELECT m.rowid FROM memberships m
  WHERE m.role = 'admin'
    AND m.created_at = (
      SELECT MIN(m2.created_at) FROM memberships m2
      WHERE m2.org_id = m.org_id AND m2.role = 'admin'
    )
  GROUP BY m.org_id
);

-- ═══════════════════════════════════════════════════════════════════════════
-- sessions: add active_org_id (nullable = pick_workspace state)
-- ═══════════════════════════════════════════════════════════════════════════
ALTER TABLE sessions ADD COLUMN active_org_id INTEGER REFERENCES orgs(id);

-- Backfill: set active_org_id to user's first membership org
UPDATE sessions SET active_org_id = (
  SELECT org_id FROM memberships WHERE user_id = sessions.user_id LIMIT 1
);

-- ═══════════════════════════════════════════════════════════════════════════
-- settings: rebuild with (org_id, key) PK
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE settings_new (
  org_id INTEGER NOT NULL DEFAULT 1,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (org_id, key),
  FOREIGN KEY(org_id) REFERENCES orgs(id) ON DELETE CASCADE
);

INSERT INTO settings_new(org_id, key, value)
SELECT 1, key, value FROM settings;

DROP TABLE settings;
ALTER TABLE settings_new RENAME TO settings;

-- ═══════════════════════════════════════════════════════════════════════════
-- connections: add org_id, rebuild with UNIQUE(org_id, provider, owned_by)
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE connections_new (
  id TEXT PRIMARY KEY,
  org_id INTEGER NOT NULL DEFAULT 1,
  provider TEXT NOT NULL,
  mode TEXT,
  status TEXT NOT NULL,
  doc_count INTEGER NOT NULL DEFAULT 0,
  last_sync_at TEXT,
  next_sync_at TEXT,
  backfill_done INTEGER NOT NULL DEFAULT 0,
  backfill_progress REAL,
  error TEXT,
  interval_min INTEGER NOT NULL DEFAULT 15,
  paused INTEGER NOT NULL DEFAULT 0,
  checklist_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  lookback_days INTEGER NOT NULL DEFAULT 30,
  channel_ids_json TEXT NOT NULL DEFAULT '[]',
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  owned_by TEXT,
  kind TEXT NOT NULL DEFAULT 'org',
  backfill_cursor TEXT,
  UNIQUE(org_id, provider, owned_by),
  FOREIGN KEY(org_id) REFERENCES orgs(id) ON DELETE CASCADE
);

INSERT INTO connections_new(
  id, org_id, provider, mode, status, doc_count, last_sync_at, next_sync_at,
  backfill_done, backfill_progress, error, interval_min, paused,
  checklist_json, created_at, lookback_days, channel_ids_json,
  consecutive_failures, owned_by, kind, backfill_cursor
)
SELECT
  id, 1, provider, mode, status, doc_count, last_sync_at, next_sync_at,
  backfill_done, backfill_progress, error, interval_min, paused,
  checklist_json, created_at, lookback_days, channel_ids_json,
  consecutive_failures, owned_by, kind, backfill_cursor
FROM connections;

DROP TABLE connections;
ALTER TABLE connections_new RENAME TO connections;

-- ═══════════════════════════════════════════════════════════════════════════
-- docs: add org_id
-- ═══════════════════════════════════════════════════════════════════════════
ALTER TABLE docs ADD COLUMN org_id INTEGER NOT NULL DEFAULT 1 REFERENCES orgs(id);
CREATE INDEX IF NOT EXISTS docs_org ON docs(org_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- conversations: add org_id, user_id
-- ═══════════════════════════════════════════════════════════════════════════
ALTER TABLE conversations ADD COLUMN org_id INTEGER NOT NULL DEFAULT 1 REFERENCES orgs(id);
ALTER TABLE conversations ADD COLUMN user_id TEXT REFERENCES users(id);
CREATE INDEX IF NOT EXISTS conversations_org ON conversations(org_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- spend: rebuild with (org_id, stage) PK
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE spend_new (
  org_id INTEGER NOT NULL DEFAULT 1,
  stage TEXT NOT NULL,
  calls INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (org_id, stage),
  FOREIGN KEY(org_id) REFERENCES orgs(id) ON DELETE CASCADE
);

INSERT INTO spend_new(org_id, stage, calls)
SELECT 1, stage, calls FROM spend;

DROP TABLE spend;
ALTER TABLE spend_new RENAME TO spend;

-- ═══════════════════════════════════════════════════════════════════════════
-- channel_memberships: add org_id to PK
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE channel_memberships_new (
  org_id INTEGER NOT NULL DEFAULT 1,
  user_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (org_id, user_id, provider, channel_id),
  FOREIGN KEY(org_id) REFERENCES orgs(id) ON DELETE CASCADE
);

INSERT INTO channel_memberships_new(org_id, user_id, provider, channel_id, updated_at)
SELECT 1, user_id, provider, channel_id, updated_at FROM channel_memberships;

DROP TABLE channel_memberships;
ALTER TABLE channel_memberships_new RENAME TO channel_memberships;

-- ═══════════════════════════════════════════════════════════════════════════
-- api_keys: add org_id
-- ═══════════════════════════════════════════════════════════════════════════
ALTER TABLE api_keys ADD COLUMN org_id INTEGER NOT NULL DEFAULT 1 REFERENCES orgs(id);
CREATE INDEX IF NOT EXISTS api_keys_org ON api_keys(org_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- oauth_states: add org_id
-- ═══════════════════════════════════════════════════════════════════════════
ALTER TABLE oauth_states ADD COLUMN org_id INTEGER REFERENCES orgs(id);

-- ═══════════════════════════════════════════════════════════════════════════
-- pending_connects: add org_id
-- ═══════════════════════════════════════════════════════════════════════════
ALTER TABLE pending_connects ADD COLUMN org_id INTEGER REFERENCES orgs(id);

-- ═══════════════════════════════════════════════════════════════════════════
-- graph_written: add org_id
-- ═══════════════════════════════════════════════════════════════════════════
ALTER TABLE graph_written ADD COLUMN org_id INTEGER NOT NULL DEFAULT 1 REFERENCES orgs(id);

-- ═══════════════════════════════════════════════════════════════════════════
-- thread_state: add org_id
-- ═══════════════════════════════════════════════════════════════════════════
ALTER TABLE thread_state ADD COLUMN org_id INTEGER NOT NULL DEFAULT 1 REFERENCES orgs(id);

COMMIT;

PRAGMA foreign_keys=ON;
