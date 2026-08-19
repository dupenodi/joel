-- §11.3 progressive deep backfill: the fast pass (lookback_days) already
-- gets a connector to `ready` in minutes; this is the second, backward-
-- walking pass that eventually reaches the account's true beginning (or a
-- provider-specific floor) instead of leaving `backfill_done` meaning
-- nothing more than "first sync happened."
BEGIN;

-- ISO timestamp: everything from this point forward to now is covered.
-- NULL = deep backfill not applicable to this provider, or not started yet.
ALTER TABLE connections ADD COLUMN backfill_cursor TEXT;

COMMIT;
