-- MCP OAuth (authorization code + PKCE). Cursor/Claude register as clients
-- against this install; tokens map to a normal Actor the same way API keys do.
BEGIN;

CREATE TABLE mcp_oauth_clients (
  client_id TEXT PRIMARY KEY,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE mcp_oauth_pending (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  params_json TEXT NOT NULL,
  expires_at REAL NOT NULL
);

CREATE TABLE mcp_oauth_codes (
  code TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  org_id INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  expires_at REAL NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(org_id) REFERENCES orgs(id) ON DELETE CASCADE
);

CREATE TABLE mcp_oauth_tokens (
  token_hash TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('access', 'refresh')),
  client_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  org_id INTEGER NOT NULL,
  scopes_json TEXT NOT NULL,
  expires_at REAL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(org_id) REFERENCES orgs(id) ON DELETE CASCADE
);

CREATE INDEX mcp_oauth_tokens_actor ON mcp_oauth_tokens(user_id, org_id, kind);

COMMIT;
