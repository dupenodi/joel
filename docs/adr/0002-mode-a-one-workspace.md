# ADR: Mode A — one workspace per install

**Context:** [`docs/SAAS_SKELETON.md`](../SAAS_SKELETON.md)  
**File:** `docs/adr/0002-mode-a-one-workspace.md`

## Decision

joel self-host is **Mode A**: one deploy = one company = one `orgs` row (`id=1`).

- First admin creates the workspace at `/setup`.
- Everyone else joins via invite (email optional; link always recoverable).
- Roles: `admin` | `member` only.
- No “create another workspace” in the product UI.
- Departments/squads are **not** extra workspaces — use visibility stamps (`org` / channel / user), or a future in-workspace team table if needed.

## Consequences

- Schema may carry `org_id` (default 1) so a future multi-tenant cloud (Mode B) is a migration, not a rewrite.
- Mode B (many orgs per process, subdomain routing, billing) is explicitly deferred until we sell hosted multi-tenant cloud.

## Rejected alternatives

- Multi-workspace self-host UI (Plane-style) — wrong trust boundary for a company brain.
- Open signup — wrong for private org memory.
