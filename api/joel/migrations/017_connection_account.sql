-- Record whose account a connector actually authenticated as.
--
-- `visibility.derive` stamps every Gmail document `user:gmail:<mailbox>`,
-- where the mailbox is the address the connector authenticated as. But the
-- read side built its stamp from `actor.email` — the workspace login — so
-- the two only matched when a person's work email happened to be the same
-- string as their personal Gmail address. For everyone else, every message
-- they connected was invisible to them: the corpus was ingested, indexed,
-- and then filtered out of their own answers.
--
-- Nothing in the schema recorded the connected account, so there was no way
-- to fix it at read time. `account_id` stores it (the mailbox for Gmail;
-- whatever identifies the authenticated account for other providers) and
-- `connected_by` records which user authorised the connection, since an
-- org-scoped connection has `owned_by` NULL by design.
--
-- Backfill derives the account from the documents the connection already
-- produced: for Gmail, `docs.container` IS the mailbox. Existing installs
-- therefore repair themselves on boot rather than needing a reconnect.
BEGIN;

ALTER TABLE connections ADD COLUMN account_id TEXT;
ALTER TABLE connections ADD COLUMN connected_by TEXT REFERENCES users(id);

UPDATE connections
SET account_id = (
  SELECT d.container
  FROM docs d
  WHERE d.org_id = connections.org_id
    AND d.source_type = connections.provider
    AND d.container IS NOT NULL
    AND d.container != ''
  GROUP BY d.container
  ORDER BY COUNT(*) DESC
  LIMIT 1
)
WHERE provider = 'gmail' AND account_id IS NULL;

-- A personal connection already names its owner. For org-scoped ones the
-- authoriser is unrecorded; attribute them to the workspace owner, who is
-- the only person who could have created them on a single-admin install.
UPDATE connections
SET connected_by = COALESCE(
  owned_by,
  (SELECT m.user_id FROM memberships m
    WHERE m.org_id = connections.org_id AND m.role = 'owner'
    ORDER BY m.created_at LIMIT 1)
)
WHERE connected_by IS NULL;

CREATE INDEX IF NOT EXISTS connections_account
  ON connections(org_id, provider, connected_by);

COMMIT;
