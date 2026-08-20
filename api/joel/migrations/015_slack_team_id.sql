-- Slack workspace id for hosted Add to Slack. Events from the install-wide
-- Slack app all share one signing secret; team_id is how we find the org.
BEGIN;

ALTER TABLE orgs ADD COLUMN slack_team_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS orgs_slack_team_id
  ON orgs(slack_team_id)
  WHERE slack_team_id IS NOT NULL;

COMMIT;
