-- §0.3's "API keys — not built": the MCP surface's identity mechanism.
-- A key maps to exactly one person's normal Actor -- no separate
-- privilege model, the exact same AskContext/allowed_stamps machinery
-- every other surface already uses.
BEGIN;

CREATE TABLE api_keys (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  label TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  key_last4 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX api_keys_user ON api_keys(user_id);

COMMIT;
