# ADR: Mode B — multi-workspace

**Status:** Accepted (supersedes [`0002-mode-a-one-workspace.md`](0002-mode-a-one-workspace.md) for product scope)  
**Date:** 2026-08-20  
**Context:** [`docs/SAAS_SKELETON.md`](../SAAS_SKELETON.md)

## Decision

joel supports **multiple workspaces (orgs) per install** (Mode B):

- Global `users` (email unique); memberships join users ↔ orgs with roles `owner` | `admin` | `member`.
- Sessions carry `active_org_id`. Login restores the last workspace when still a member; otherwise the picker.
- Any signed-in user can create a workspace and becomes its **owner**.
- Workspace settings, connectors, docs, conversations, spend, mail, etc. are scoped by `org_id`.
- Vector index: `index/org-{id}.npz`. Hydra namespace: `joel-org-{id}`.
- Still **invite-only** into a workspace (no open signup into someone else's company brain).

Self-host with a single company remains valid: one org row, no picker UX friction when you only have one membership.

## Consequences

- ADR 0002’s “no create-workspace UI” is revoked.
- Cross-tenant isolation is a hard invariant — every query path must filter `Actor.org_id`.
- Billing / subdomain routing / SSO remain deferred.

## Rejected alternatives

- Keeping `ORG_ID = 1` as a permanent constant while “also” supporting many orgs.
- Equating departments with separate workspaces (use visibility stamps or future in-workspace teams).
