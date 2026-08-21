# SaaS skeleton research — workspaces, membership, tenancy

Primary-source notes on how dual-mode OSS products (and Linear via public API/docs) structure the "SaaS skeleton": workspace/org, users, memberships, invites, roles, sessions, settings scope, and self-host vs cloud multi-tenancy. Compared to joel today.

**Sources policy:** GitHub source + official docs only. Linear is **not** open source; Linear claims below are from the public GraphQL schema / help docs, and are called out as such.

**joel local sources:** `api/joel/migrations/003_identity.sql`, `api/joel/identity.py`, `docs/SYSTEM_OVERVIEW.md`.

---

## Executive verdict

**joel’s “one workspace per install” skeleton is the right default for a company-brain product.** It matches how serious self-host collaboration tools treat the deploy as the trust boundary: one company’s memory, connectors, and people live in one install. That is closer to Mattermost’s self-host posture and Outline’s self-host URL behavior than to cloud multi-tenant subdomain SaaS.

**Graduate to multi-workspace (many orgs per deploy) only when the product itself becomes a shared cloud:** one control plane hosting many unrelated customers, with cross-tenant isolation as a hard requirement. Do **not** invent multi-workspace early to model “teams,” “departments,” or “projects” — those are *optional sub-scopes inside one company*, not extra workspaces. For a company brain, the dangerous early mistake is treating the install as a hotel for many companies before the single-company identity/permissions path is boring and correct.

**When you’d graduate:**

1. You sell a **managed multi-tenant cloud** (joel.cloud hosting Acme + Beta on one cluster).
2. One human identity must belong to **many independent customer workspaces** on the same deploy (agency / consultant / platform pattern).
3. You need per-workspace billing, suspension, and subdomain routing in one process.

Until then: harden single-workspace Mode A (below). Keep schema shapes that *could* grow (`memberships.org_id`, Actor carrying `org_id`) without building Mode B.

---

## Two deployment modes OSS products use

| Mode | Meaning | Typical routing | Data tenancy |
|---|---|---|---|
| **(A) Single-tenant self-host** | One org / company per deploy | One base URL (`env.URL`); no customer subdomains | Entire DB belongs to that company; “org id” is often a constant or a single row |
| **(B) Multi-tenant cloud** | Many orgs per deploy | Subdomain / custom domain → org resolution | Every row keyed by workspace/org; auth resolves *which* org |

**Outline** encodes this explicitly: cloud is detected when `URL` is Outline’s hosted app URL; team URLs use `subdomain` only when cloud-hosted, otherwise `Team.url` returns `env.URL`.

```909:915:https://github.com/outline/outline/blob/main/server/env.ts
public get isCloudHosted() {
  return [
    "https://app.getoutline.com",
    "https://app.outline.dev",
    "https://app.outline.dev:3000",
  ].includes(this.URL);
}
```

```text
# Team.url (server/models/Team.ts) — cloud subdomain vs self-host base URL
if (!this.subdomain || !env.isCloudHosted) {
  return env.URL;
}
url.host = `${this.subdomain}.${getBaseDomain()}`;
```

**Mattermost:** self-host / Cloud Enterprise described as single-tenant; Professional called out as multi-tenant SaaS. Within one instance, “teams” are collaboration partitions, not separate customer tenancies. Docs recommend single-team deploy for most orgs.

**GitLab:** Self-Managed is one instance with groups/projects inside; GitLab.com is the multi-tenant SaaS. Docs note that on Self-Managed, a single top-level group is the usual way to get an “organization overview.”

**Plane / Cal.com:** schema is multi-workspace capable (unique workspace slugs; org/team trees). Self-host still *can* run many workspaces in one DB (Plane lets users create workspaces), but the *product* pattern for company tools is still “this install is our company.”

**joel today:** Mode A only — `ORG_ID = 1`, one `orgs` row, memberships default `org_id=1`.

---

## Canonical SaaS skeleton layers

Almost every product surveyed stacks the same layers (names differ):

```
User
  └─ Membership (user × workspace/org, with role)
       └─ Workspace / Org / Team(workspace-level)   ← tenancy root
            └─ optional Team / Project / Collection  ← sub-scope
                 └─ Roles (workspace-level and/or sub-scope)
                 └─ Invites (pending join into workspace ± teams)
                 └─ Sessions / tokens (prove User; Membership derived)
                 └─ Settings scope (user prefs vs workspace prefs vs project prefs)
                 └─ Data tenancy (every business row → workspace_id / teamId)
```

| Layer | Job | Anti-pattern |
|---|---|---|
| **User** | Global person identity (email, password/OAuth, display name) | Equating “user” with “customer company” |
| **Membership** | Join table: which users belong to which workspace, with role | Stashing role only on User when multi-workspace is possible |
| **Workspace/Org** | Tenancy root: billing, branding, allowed domains, connectors | Using “team” to mean both company and squad |
| **Team/Project** (optional) | Sub-partition *inside* one company | Promoting sub-teams to separate DBs early |
| **Roles** | Capability at workspace (admin/member/…) and sometimes at project | Unbounded custom RBAC in v1 |
| **Invites** | Pre-membership grant (email + role + token + expiry) | Open signup into a company brain |
| **Sessions** | Auth proof for User; Actor = User + Membership | Session that doesn’t re-check membership |
| **Settings scope** | User / workspace / project preference namespaces | One flat `settings` bag mixing LLM keys and UI chrome |
| **Data tenancy** | Every doc/issue keyed to workspace | Relying on “we only have one org so skip the FK” forever |

**joel mapping today**

| Layer | joel |
|---|---|
| User | `users` |
| Membership | `memberships (user_id, org_id, role)` |
| Workspace | `orgs` row `id=1` |
| Team/Project | *none* (visibility rooms substitute for channel/privacy, not org structure) |
| Roles | `admin` \| `member` |
| Invites | `invites` (hashed token, expiry, role) |
| Sessions | `sessions` (+ `api_keys` as bearer Actor) |
| Settings | workspace settings pages; LLM keys etc. (workspace-scoped in practice) |
| Data tenancy | implicit single org; docs use visibility stamps, not `org_id` on every row |

---

## Product deep-dives (primary sources)

### 1. Outline — Team = workspace; User belongs to one Team; UserMembership ≠ org membership

**Tenancy root:** `Team` (UI often says “workspace”). Fields include `name`, `subdomain`, `domain`, preferences, `inviteRequired`, `defaultUserRole`.

**User:** `User` has required `teamId` + `role` (`admin` \| `member` \| `viewer` \| `guest`). Invites create a `User` row with `invitedById` and `lastActiveAt = null` (`isInvited`). There is no separate `invites` table in the inviter path — pending users *are* the invite.

**Org membership vs content membership:**

- Belonging to the workspace = `User.teamId` + `User.role`.
- `UserMembership` (table `user_permissions`) is **collection/document ACL**, not “member of company.”

**Auth:** JWT session cookies (`accessToken`), signed with per-user `jwtSecret`; rotating secret invalidates sessions. Middleware loads user + team.

**Self-host vs cloud:** `env.isCloudHosted` gates subdomain hosting; self-host `Team.url` collapses to `env.URL`. Cloud uses `subdomain.getoutline.com` or custom `domain`.

**Citations**

- Team model: https://github.com/outline/outline/blob/main/server/models/Team.ts  
- User model: https://github.com/outline/outline/blob/main/server/models/User.ts  
- UserMembership (collection/doc ACL): https://github.com/outline/outline/blob/main/server/models/UserMembership.ts  
- Roles enum: https://github.com/outline/outline/blob/main/shared/types.ts (`UserRole`)  
- Inviter creates User rows: https://github.com/outline/outline/blob/main/server/commands/userInviter.ts  
- Auth middleware: https://github.com/outline/outline/blob/main/server/middlewares/authentication.ts  
- Cloud detection: https://github.com/outline/outline/blob/main/server/env.ts  

### 2. Plane — Workspace → Project; separate memberships and invites at both levels

**Hierarchy:** `Workspace` (slug unique) → `Project` (FK `workspace`) → issues etc. Abstract `WorkspaceBaseModel` / `ProjectBaseModel` force workspace (and project) FKs down the tree.

**Membership:** `WorkspaceMember(workspace, member, role)` with roles `Admin=20`, `Member=15`, `Guest=5`. `ProjectMember` mirrors the same role integers at project scope.

**Invites:** `WorkspaceMemberInvite` and `ProjectMemberInvite` (email, token, role, accepted).

**Optional Team:** Plane also has a `Team` model *under* a workspace (named groups) — not the tenancy root.

**Users:** Django auth user is global; a user can be in many workspaces via `WorkspaceMember`.

**Self-host:** Official docs describe deploying Plane on your infrastructure (Docker/K8s). Schema remains multi-workspace; whether you create one or many workspaces is operational choice.

**Citations**

- Workspace / member / invite models: https://github.com/makeplane/plane/blob/main/apps/api/plane/db/models/workspace.py  
- Project / project member / invite: https://github.com/makeplane/plane/blob/main/apps/api/plane/db/models/project.py  
- Self-host overview: https://docs.plane.so/self-hosting/overview  

### 3. Cal.com — Team doubles as Organization; Membership join; Profile per org

**Tenancy:** `Team` with `isOrganization` boolean. Child teams use `parentId` → parent org. Organizations get `OrganizationSettings` (verified domain, auto-accept email domain, etc.).

**Membership:** `Membership(userId, teamId, role, accepted)` with `MembershipRole`: `MEMBER` \| `ADMIN` \| `OWNER`. Unique `(userId, teamId)`.

**Profile:** `Profile(userId, organizationId, username)` — a user can have multiple org profiles (`@@unique([userId, organizationId])`).

**Invites:** `VerificationToken` optionally tied to `teamId` (invite tokens on the team).

**User:** Global `User` with email/password; `teams Membership[]`.

**Citations**

- Prisma schema (User, Profile, Team, Membership, OrganizationSettings): https://github.com/calcom/cal.com/blob/main/packages/prisma/schema.prisma  

### 4. Mattermost / GitLab — brief self-host “one org per install” vs multi-tenant

**Mattermost**

- Self-host / Cloud Enterprise: framed as **single-tenant** (your data in your boundary).  
- Professional: explicitly **multi-tenant SaaS**.  
- Inside one instance: multiple **Teams** are collaboration workspaces; docs recommend **single team** for most deployments so the org doesn’t silo itself.

Citations:

- Teams / single vs multi team: https://docs.mattermost.com/end-user-guide/collaborate/organize-using-teams.html  
- Cloud Enterprise single-tenant vs Professional multi-tenant: https://docs.mattermost.com/product-overview/faq-enterprise.html  
- MMTA / single-tenant security framing: https://docs.mattermost.com/security-guide/security-guide-index.html  

**GitLab**

- **Self-Managed** = administer one instance.  
- **GitLab.com** = multi-tenant SaaS.  
- Inside an instance/org: **Groups → Subgroups → Projects**; members inherit. Docs recommend one top-level group on Self-Managed for org-wide analytics.

Citations:

- Groups hierarchy: https://docs.gitlab.com/user/group/  
- Administer Self-Managed: https://docs.gitlab.com/administration/  
- Organizations (emerging org abstraction): https://docs.gitlab.com/user/organization/  

### 5. Linear — public API/docs only (not open source)

> **Note:** Linear is proprietary. The following is from Linear’s public GraphQL schema descriptions and help docs, not source code.

**Workspace = Organization (API name).** Schema description: workspace is the root container for teams, users, projects, issues, settings.

**User:** Belongs to a workspace (`organization`); roles described as admin / member / guest / app. `User.admin`, `User.guest`. Users can join multiple **teams** via `TeamMembership`.

**Team:** Primary unit for issues/workflows; public or restricted; members via `TeamMembership` (optional `owner` flag for team-level elevation).

**Invites:** `OrganizationInvite` — email, workspace `role` (`admin` \| `member` \| `guest` \| `owner`), optional team assignment in product UI, expiry / acceptedAt.

**Help docs:** Workspace composed of one or several teams; invite from Administration → Members; Free plan treats all as Admin for invites.

Citations:

- GraphQL API entry: https://developers.linear.app/docs/graphql/working-with-the-graphql-api  
- Introspection (`Organization`, `Team`, `User`, `OrganizationInvite`, `TeamMembership`) via https://api.linear.app/graphql  
- Teams help: https://linear.app/docs/teams  
- Invite members: https://linear.app/docs/invite-members  

---

## Comparison table

| Dimension | Outline | Plane | Cal.com | Linear (public) | joel today |
|---|---|---|---|---|---|
| **Tenancy root name** | Team (“workspace”) | Workspace | Team (`isOrganization`) | Organization (“workspace”) | `orgs` (“workspace”) |
| **User ↔ tenant** | User has `teamId` (one team per user row) | `WorkspaceMember` M:N | `Membership` M:N + `Profile` per org | User → one Organization; multi-team inside | `memberships` M:N-shaped but hardcoded `ORG_ID=1` |
| **Sub-scope** | Collections / docs (+ Groups) | Project (+ optional Team group) | Child `Team` under org | Team (issues live here) | Visibility rooms (`org` / channel / user) — privacy, not org chart |
| **Workspace roles** | admin, member, viewer, guest | Admin 20, Member 15, Guest 5 | OWNER, ADMIN, MEMBER | admin, member, guest, owner (invite role) | admin, member |
| **Invites** | Create pending `User` + email | `WorkspaceMemberInvite` / project invites | `VerificationToken` on team | `OrganizationInvite` | `invites` table, hashed token |
| **Sessions** | JWT in cookie; per-user `jwtSecret` | Django sessions / tokens (framework) | NextAuth-style stack (schema: passwords, tokens) | OAuth / API keys (docs) | Cookie `sessions` + `api_keys` → Actor |
| **Settings scope** | Team preferences + User preferences | Workspace / project / user property JSON | Org settings + team + user | Org + team settings (product) | Workspace settings; actor-scoped personal connectors |
| **Self-host mode** | Mode A: `Team.url = env.URL` | Deploy own infra; schema still multi-ws | Self-hostable; schema multi-org | N/A (cloud product) | Mode A only |
| **Cloud multi-tenant** | Mode B: subdomain / custom domain | Hosted Plane: many workspaces | Hosted: many orgs/teams | Always Mode B | Not built |
| **Data tenancy key** | `teamId` on documents/users | `workspace_id` (+ `project_id`) | `teamId` / org via parent | `organization` / `team` on entities | Implicit single org; stamp-based read ACL |

---

## joel today (grounded)

From `003_identity.sql` + `identity.py`:

- Settled product decision: **one self-hosted workspace, many members**; `/setup` creates first admin; invites for everyone else; roles `admin` / `member`.
- Implementation: `ORG_ID = 1`; `Actor` always resolves membership for that org; sessions are opaque IDs in SQLite; invites hash tokens like API keys.
- Company-brain twist: **data ACL is room stamps**, not a second org hierarchy — employee / private channel / public-style rooms (see PLAN visibility). That is closer to Mattermost channels than to Plane projects.

This is already a recognizable Mode A SaaS skeleton. Gaps vs hardened OSS peers are mostly: last-admin guards already exist; missing richer roles / SSO / allowed domains / explicit `org_id` on every business table / soft-delete membership without deleting the user row.

---

## Recommended joel roadmap

Numbered path from current state → hardened single-workspace skeleton → optional multi-workspace later.

1. **Keep Mode A as the product contract.** Document in PLAN/ADR: deploy = one company. Do not add “create workspace” UX.
2. **Treat `orgs` + `memberships` as the real tenancy API even while `ORG_ID=1`.** Every identity path already joins membership; refuse “skip membership” shortcuts for Slack/MCP.
3. **Harden invites + membership lifecycle.** Expiry, revoke, resend, deactivate member without hard-deleting user history where possible; keep last-admin invariants (already partially present).
4. **Clarify settings namespaces.** Split **workspace settings** (domain, LLM spend budgets, org connectors) vs **user settings** (display name, API keys, personal connectors). Match Outline/Plane’s dual preference bags.
5. **Put explicit tenancy on hot data paths when convenient.** Prefer `org_id` on new tables (docs/jobs already conceptually org-scoped) so Mode B is a migration, not a rewrite — but don’t dual-write multi-tenant routers yet.
6. **Optional sub-scopes only if product needs them.** If you need “eng vs sales” partitions, add **teams/projects inside the one workspace** (Plane/Linear style) — or keep leaning on channel stamps. Don’t invent a second workspace.
7. **Auth upgrades for real companies.** SSO/OIDC, allowed email domains, invite-required flag (Outline `inviteRequired` / Cal `orgAutoAcceptEmail` patterns) — still Mode A.
8. **Only then Mode B (optional cloud).** Subdomain or path routing → `org_id`; sessions bind to user; Actor resolves membership for *selected* org; hard tenant filters on every query; billing/suspension per org.

---

## Explicit NON-goals for v1

- Multi-workspace / multi-tenant cloud hosting on one deploy  
- User accounts that span many customer companies in one joel process  
- Custom RBAC / fine-grained permission matrices beyond `admin` \| `member`  
- Outline-style collection ACL as a second membership system (joel uses visibility stamps)  
- Cal.com-style organization→child-team tree  
- Billing, seats, SSO marketplace integrations  
- “Create another workspace” in self-host UI  
- Soft multi-tenancy via Postgres RLS before a real Mode B product exists  

---

## Citations index (every external factual claim)

| Claim | URL |
|---|---|
| Outline Team model, subdomain, `url` cloud vs self-host | https://github.com/outline/outline/blob/main/server/models/Team.ts |
| Outline `isCloudHosted` | https://github.com/outline/outline/blob/main/server/env.ts |
| Outline User `teamId`, roles, invites-as-users, JWT session helpers | https://github.com/outline/outline/blob/main/server/models/User.ts |
| Outline `UserRole` enum | https://github.com/outline/outline/blob/main/shared/types.ts |
| Outline `UserMembership` = collection/document permission | https://github.com/outline/outline/blob/main/server/models/UserMembership.ts |
| Outline `userInviter` creates users + email | https://github.com/outline/outline/blob/main/server/commands/userInviter.ts |
| Outline auth cookie/JWT middleware | https://github.com/outline/outline/blob/main/server/middlewares/authentication.ts |
| Plane Workspace, WorkspaceMember, invites, Team-under-workspace | https://github.com/makeplane/plane/blob/main/apps/api/plane/db/models/workspace.py |
| Plane Project + ProjectMember + invites | https://github.com/makeplane/plane/blob/main/apps/api/plane/db/models/project.py |
| Plane self-host docs | https://docs.plane.so/self-hosting/overview |
| Cal.com User / Team / Membership / Profile / OrganizationSettings | https://github.com/calcom/cal.com/blob/main/packages/prisma/schema.prisma |
| Mattermost single vs multiple teams guidance | https://docs.mattermost.com/end-user-guide/collaborate/organize-using-teams.html |
| Mattermost Cloud Enterprise single-tenant vs Professional multi-tenant | https://docs.mattermost.com/product-overview/faq-enterprise.html |
| Mattermost single-tenant vs MMTA security discussion | https://docs.mattermost.com/security-guide/security-guide-index.html |
| GitLab groups hierarchy / Self-Managed top-level group note | https://docs.gitlab.com/user/group/ |
| GitLab administer Self-Managed | https://docs.gitlab.com/administration/ |
| GitLab organizations docs | https://docs.gitlab.com/user/organization/ |
| Linear GraphQL docs hub | https://developers.linear.app/docs/graphql/working-with-the-graphql-api |
| Linear public schema (`Organization`/`Team`/`User`/`OrganizationInvite`/`TeamMembership`) | https://api.linear.app/graphql |
| Linear teams help | https://linear.app/docs/teams |
| Linear invite members help | https://linear.app/docs/invite-members |
| joel identity migration | `api/joel/migrations/003_identity.sql` |
| joel identity module | `api/joel/identity.py` |
| joel one-workspace product decision | `docs/adr/0002-mode-a-one-workspace.md` |

---

## Implementation checklist (against joel today)

Work these in order. Each step ends with a `scripts/check_*.py` green (or an extension of an existing check). Stop and re-propose if a step wants to grow into Mode B.

### Step 1 — Product contract (docs only)
- [x] Add a short ADR / PLAN pointer: **deploy = one company (Mode A)**; no “create workspace” in self-host UI. (`docs/adr/0002-mode-a-one-workspace.md`)
- [x] Cross-link `docs/SAAS_SKELETON.md` from `docs/SYSTEM_OVERVIEW.md`.
- [x] Explicitly state: departments/squads ≠ extra workspaces; use visibility stamps (or a future in-workspace team) instead.

### Step 2 — Tenancy API discipline (code, still Mode A)
- [x] Audit every Actor / Slack / MCP path: membership join required; no “user without membership.”
- [x] Keep `ORG_ID=1` as the constant; identity helpers own org scoping.
- [x] Add `org_id` to `invites` (default 1) so Mode B isn’t a rewrite of invites later.
- [x] Extend `scripts/check_identity.py` for “no membership ⇒ no Actor.”

### Step 3 — Invites + membership lifecycle
- [x] Resend invite (new token + optional email) — UI + API.
- [x] Copy-link again for pending invites via Resend.
- [x] Soft-remove member: drop membership + sessions + API keys + personal connectors; **keep** `users` row.
- [ ] Optional: `memberships.status` active/disabled instead of delete.
- [x] Last-admin errors enforced in `identity.py` (surfaced as API errors in Members UI).

### Step 4 — Settings namespaces
- [x] Document / enforce: workspace settings (LLM, mail, org connectors, slack signing) vs user settings (profile, password, API keys, personal connectors).
- [x] Admin-only `PUT /api/settings` + Composio key; org connector mutations admin-gated.

### Step 5 — Explicit tenancy on new data (opportunistic)
- [ ] New tables get `org_id NOT NULL DEFAULT 1`.
- [ ] Do **not** dual-write multi-tenant routers or subdomain resolution yet.

### Step 6 — Optional in-workspace sub-scopes (product-gated)
- [ ] Only if we need eng/sales partitions beyond channel stamps.
- [ ] Shape: `teams` under one `orgs` row + `team_memberships` (Plane/Linear), **not** a second workspace.

### Step 7 — Company auth upgrades (still Mode A)
- [ ] Allowed email domains / invite-required flag.
- [ ] SSO/OIDC (Outline-style external IdP) when a real customer needs it.

### Step 8 — Mode B multi-workspace cloud (explicitly later)
- [ ] Subdomain or path → `org_id`; session = user; Actor = membership for *selected* org.
- [ ] Hard tenant filters on docs/jobs/connectors; billing/suspension per org.

---

*Research + roadmap for engineering. Step 1 is docs; steps 2+ change code after explicit approval of each step.*
