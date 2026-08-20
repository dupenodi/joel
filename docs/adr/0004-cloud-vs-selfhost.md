# ADR: Cloud vs self-host

**Status:** Accepted  
**Date:** 2026-08-21  
**File:** `api/joel/deployment.py`

## Decision

One codebase, two deploys:

- **self-host** — operator runs joel (localhost, Docker, their VPS). Default.
- **cloud** — the hosted product at `meetjoel.xyz` (any subdomain).

Callers use `deployment()` / `slack_install()`. They do not parse `JOEL_WEB_ORIGIN` themselves.

Detection:

1. `JOEL_DEPLOYMENT=cloud|selfhost` wins.
2. Else origin host is `meetjoel.xyz` or `*.meetjoel.xyz` → cloud.
3. Else self-host.

Slack install is a separate capability (`SLACK_CLIENT_ID` + `SLACK_CLIENT_SECRET` + `SLACK_SIGNING_SECRET`):

| | Slack env set | Slack env empty |
|---|---|---|
| **Cloud** | Add to Slack | Unavailable — never the DIY manifest |
| **Self-host** | Add to Slack (optional) | Manifest + paste secrets |

## Consequences

- OSS keeps creating a Slack app from the repo manifest.
- meetjoel.xyz customers click Add to Slack. Events hit this origin; orgs are keyed by `orgs.slack_team_id`.
- Later hosted-only work (billing) adds a function next to `deployment()`, not a second origin check. MCP OAuth is **both** modes: joel is the authorization server on this origin.

## Rejected alternatives

- One Slack app serving every self-host (Slack allows one Events URL).
- Inferring cloud only from an env flag with no origin fallback (easy to mis-set in production).
- A features/plugin object — one module, small interface.
