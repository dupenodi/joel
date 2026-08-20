-- Concurrent personal vs org OAuth used to share one pending_connects row
-- (PRIMARY KEY was toolkit). SQLite UNIQUE treats every NULL as distinct,
-- so UNIQUE(org_id, toolkit, owned_by) would still let two org-scoped
-- pendings collide. owner_key is '' for org-shared and the user id for
-- personal. Callback URLs carry pending id so two in-flight Gmail auths
-- cannot steal each other's lookback/owned_by.
PRAGMA foreign_keys=OFF;

BEGIN;

CREATE TABLE pending_connects_new (
  id TEXT PRIMARY KEY,
  toolkit TEXT NOT NULL,
  lookback_days INTEGER NOT NULL DEFAULT 30,
  return_to TEXT NOT NULL,
  origin TEXT NOT NULL,
  created_at TEXT NOT NULL,
  owned_by TEXT,
  org_id INTEGER NOT NULL DEFAULT 1 REFERENCES orgs(id),
  owner_key TEXT NOT NULL DEFAULT '',
  UNIQUE(org_id, toolkit, owner_key)
);

INSERT INTO pending_connects_new(
  id, toolkit, lookback_days, return_to, origin, created_at,
  owned_by, org_id, owner_key
)
SELECT
  'pc_' || lower(hex(randomblob(8))),
  toolkit,
  lookback_days,
  return_to,
  origin,
  created_at,
  owned_by,
  COALESCE(org_id, 1),
  COALESCE(owned_by, '')
FROM pending_connects;

DROP TABLE pending_connects;
ALTER TABLE pending_connects_new RENAME TO pending_connects;

COMMIT;

PRAGMA foreign_keys=ON;
