-- Initial schema. Applied once, to a brand-new database only (existing
-- installs are already at this shape via the pre-migrations executescript
-- and this migration is a no-op for them -- see run_migrations() in app.py).
BEGIN;

CREATE TABLE orgs (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  domain TEXT NOT NULL,
  name TEXT NOT NULL,
  logo_url TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE connections (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL UNIQUE,
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
  channel_ids_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE connector_credentials (
  connection_id TEXT PRIMARY KEY,
  encrypted_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(connection_id) REFERENCES connections(id) ON DELETE CASCADE
);

CREATE TABLE oauth_states (
  state TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  redirect_uri TEXT NOT NULL,
  return_to TEXT NOT NULL,
  expires_at REAL NOT NULL
);

CREATE TABLE pending_connects (
  toolkit TEXT PRIMARY KEY,
  lookback_days INTEGER NOT NULL DEFAULT 30,
  return_to TEXT NOT NULL,
  origin TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  connection_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  new_count INTEGER NOT NULL DEFAULT 0,
  changed_count INTEGER NOT NULL DEFAULT 0,
  unchanged_count INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER,
  error TEXT,
  FOREIGN KEY(connection_id) REFERENCES connections(id) ON DELETE CASCADE
);

CREATE TABLE docs (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  url TEXT,
  timestamp TEXT,
  thread_id TEXT,
  parent_id TEXT,
  author_raw TEXT,
  container TEXT,
  extra_json TEXT NOT NULL DEFAULT '{}',
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  forgotten INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX docs_hash ON docs(id, content_hash);

CREATE TABLE conversations (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE spend (
  stage TEXT PRIMARY KEY,
  calls INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE thread_state (
  thread_id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  artifact_id TEXT NOT NULL,
  kept_bursts_json TEXT NOT NULL DEFAULT '{}',
  last_distilled_at TEXT NOT NULL
);

COMMIT;
