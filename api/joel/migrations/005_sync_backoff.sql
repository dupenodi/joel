-- Phase 8 / CP8 (§11.2): the sync scheduler's due-query already existed
-- (status='ready' AND next_sync_at<=now), but nothing ever moved an
-- errored connector back toward 'ready' -- once a sync failed, the
-- connector sat in status='error' forever, invisible to the scheduler,
-- with no automatic retry. consecutive_failures drives the backoff ladder
-- (1m -> 5m -> 15m -> 1h -> 6h, capped, reset on success) in app.py.
BEGIN;

ALTER TABLE connections ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0;

COMMIT;
