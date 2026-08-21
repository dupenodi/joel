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
- Vector index: `index/org-{id}.npz`. Graph: a HydraDB scope of its own per
  workspace — Bolt database `{base}.scope1.{b64(joel-org-{id})}._`, HTTP
  namespace `{root}/{b64(joel-org-{id})}`, derived together in `Settings`
  (`config.py`) so the two transports cannot address different graphs.
- Still **invite-only** into a workspace (no open signup into someone else's company brain).

Self-host with a single company remains valid: one org row, no picker UX friction when you only have one membership.

## Consequences

- ADR 0002’s “no create-workspace UI” is revoked.
- Cross-tenant isolation is a hard invariant — every query path must filter `Actor.org_id`.
- The graph is the one store where isolation is **not** ours to enforce by
  filtering: vertex ids are hashes of external keys with no org in them, so
  two workspaces holding the same key hold the same id. Isolation comes from
  addressing separate HydraDB scopes, which means it is a property of the
  transport, not of any query. `scripts/check_multi_org_isolation.py` asserts
  it by writing one workspace's store and reading the other's — an earlier
  version compared two namespace *strings*, which passed throughout the
  period when `Hydra.bolt` ignored the namespace entirely and every workspace
  shared one graph.
- Installs predating scoped graphs keep their data in the install root;
  `scripts/migrate_graph_scope.py` copies it into a workspace scope.
- Billing / subdomain routing / SSO remain deferred.

## Rejected alternatives

- Keeping `ORG_ID = 1` as a permanent constant while “also” supporting many orgs.
- Equating departments with separate workspaces (use visibility stamps or future in-workspace teams).
