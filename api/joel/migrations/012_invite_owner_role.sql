-- Allow invite role = owner (memberships already support owner from 011).
PRAGMA foreign_keys=OFF;

BEGIN;

CREATE TABLE invites_new (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
  token_hash TEXT NOT NULL UNIQUE,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  accepted_at TEXT,
  org_id INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY(created_by) REFERENCES users(id),
  FOREIGN KEY(org_id) REFERENCES orgs(id) ON DELETE CASCADE
);

INSERT INTO invites_new(
  id, email, role, token_hash, created_by, created_at, expires_at, accepted_at, org_id
)
SELECT
  id, email, role, token_hash, created_by, created_at, expires_at, accepted_at, org_id
FROM invites;

DROP TABLE invites;
ALTER TABLE invites_new RENAME TO invites;

CREATE INDEX IF NOT EXISTS invites_email ON invites(email);
CREATE INDEX IF NOT EXISTS invites_org ON invites(org_id);

COMMIT;

PRAGMA foreign_keys=ON;
