-- §0.3's next skeleton checkpoint: connector ownership (groundwork only --
-- see the CP8b status note in PLAN.md for why real personal-connector
-- support needs more than these two columns) and channel membership, so a
-- desk/DM can read the private rooms the actor is actually in (§1.4).
BEGIN;

ALTER TABLE connections ADD COLUMN owned_by TEXT;             -- user id, NULL = workspace-owned (every row today)
ALTER TABLE connections ADD COLUMN kind TEXT NOT NULL DEFAULT 'org';  -- org | personal

CREATE TABLE channel_memberships (
  user_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, provider, channel_id)
);

COMMIT;
