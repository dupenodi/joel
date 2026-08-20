-- Remember last active workspace so login restores it instead of always
-- dumping multi-org users on the picker.
BEGIN;

ALTER TABLE users ADD COLUMN last_org_id INTEGER REFERENCES orgs(id);

UPDATE users SET last_org_id = (
  SELECT s.active_org_id FROM sessions s
  WHERE s.user_id = users.id AND s.active_org_id IS NOT NULL
  ORDER BY s.created_at DESC
  LIMIT 1
)
WHERE last_org_id IS NULL;

UPDATE users SET last_org_id = (
  SELECT m.org_id FROM memberships m
  WHERE m.user_id = users.id
  ORDER BY m.created_at DESC
  LIMIT 1
)
WHERE last_org_id IS NULL;

COMMIT;
