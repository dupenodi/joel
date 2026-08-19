-- Every doc lives in exactly one room. Written at ingest; retrieval filters
-- this column. Existing company-data rows stay org; gmail is personal.
BEGIN;

ALTER TABLE docs ADD COLUMN visibility TEXT NOT NULL DEFAULT 'org';

UPDATE docs
   SET visibility = 'user:gmail:' || lower(container)
 WHERE source_type = 'gmail'
   AND container IS NOT NULL
   AND container != '';

CREATE INDEX docs_visibility ON docs(visibility);

COMMIT;
