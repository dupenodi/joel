-- Phase 5 / CP5 (§8.1): the columns and side-tables the store layer needs
-- that plain ingest (Phase 3) never had a reason to write.
BEGIN;

ALTER TABLE docs ADD COLUMN granularity TEXT NOT NULL DEFAULT 'document';
ALTER TABLE docs ADD COLUMN artifact_class TEXT NOT NULL DEFAULT 'document';
ALTER TABLE docs ADD COLUMN validity TEXT NOT NULL DEFAULT 'current';
ALTER TABLE docs ADD COLUMN resolved TEXT NOT NULL DEFAULT 'na';
ALTER TABLE docs ADD COLUMN period TEXT;

-- Contentless: FTS5 stores only the inverted index, not the text itself
-- (docs.title/body already have it -- duplicating would double storage for
-- no benefit). This means the 'delete' command before a re-upsert needs the
-- OLD title/body passed in explicitly; see store_sql.py's upsert_docs.
CREATE VIRTUAL TABLE docs_fts USING fts5(id UNINDEXED, title, body, content='');

-- The client-side MERGE ledger (§8.2): compares content_hash here against
-- the doc being upserted to decide CREATE vs SET vs skip against HydraDB.
CREATE TABLE graph_written (
  id TEXT PRIMARY KEY,
  content_hash TEXT NOT NULL
);

COMMIT;
