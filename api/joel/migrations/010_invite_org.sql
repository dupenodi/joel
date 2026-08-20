-- Invites carry org_id so Mode B isn't a rewrite of the invite path.
-- Mode A keeps a single org (id=1); DEFAULT 1 backfills existing rows.
BEGIN;

ALTER TABLE invites ADD COLUMN org_id INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS invites_org ON invites(org_id);

COMMIT;
