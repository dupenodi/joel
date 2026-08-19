-- §0.3/§1.4 real personal-connector support, the increment CP8b's
-- groundwork (owned_by/kind, migration 006) was left waiting on:
-- `connections.provider` has been UNIQUE since migration 001, which meant
-- there could never be more than one connection per provider at all --
-- not even a second Gmail inbox for a second person. SQLite can't ALTER a
-- UNIQUE constraint in place, so this rebuilds the table with
-- UNIQUE(provider, owned_by) instead: SQLite treats every NULL as
-- distinct from every other NULL, so this allows exactly one org-shared
-- row (owned_by IS NULL) *plus* one personal row per user, per provider,
-- and keeps every existing row (all NULL-owned today) valid unchanged.
--
-- PRAGMA foreign_keys must be toggled OUTSIDE the transaction --  SQLite
-- silently ignores changing it mid-transaction -- so this file is not a
-- single BEGIN/COMMIT block like the others.
PRAGMA foreign_keys=OFF;

BEGIN;

CREATE TABLE connections_new (
  id TEXT PRIMARY KEY,
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
  UNIQUE(provider, owned_by)
);

INSERT INTO connections_new(
  id, provider, mode, status, doc_count, last_sync_at, next_sync_at,
  backfill_done, backfill_progress, error, interval_min, paused,
  checklist_json, created_at, lookback_days, channel_ids_json,
  consecutive_failures, owned_by, kind, backfill_cursor
)
SELECT
  id, provider, mode, status, doc_count, last_sync_at, next_sync_at,
  backfill_done, backfill_progress, error, interval_min, paused,
  checklist_json, created_at, lookback_days, channel_ids_json,
  consecutive_failures, owned_by, kind, backfill_cursor
FROM connections;

DROP TABLE connections;
ALTER TABLE connections_new RENAME TO connections;

-- §12.2's connect flow needs to remember, between "start OAuth" and "the
-- provider redirects back," which actor asked for a PERSONAL connection
-- (the callback is a public, unauthenticated redirect endpoint with no
-- session to consult -- see the CP8b status note). Same shape as the
-- lookback_days/return_to/origin fields this table already carries
-- across that same gap.
ALTER TABLE pending_connects ADD COLUMN owned_by TEXT;

COMMIT;

PRAGMA foreign_keys=ON;
