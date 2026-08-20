# Persona paths, roles, and what’s actually hooked up

Living inventory of **who can arrive**, **what they can see**, and **what they can do**.  
Primary source is the code as of this write-up (`identity.py`, `auth.py`, `app.py`, `web/lib/auth/*`, settings + integrations UI). Not a redesign — a map of current behavior, plus gaps.

Product language can stay **admin vs member**. The database has a third role, **owner**, which is “admin plus a few irreversible knobs.” This doc names all three so the map matches the code.

---

## 1. Personas (who exists)

| Persona | How they come into being | Session? | Active workspace? |
|---|---|---|---|
| **Empty-install visitor** | First hit on a DB with zero `users` | No | No |
| **Occupant visitor** | Users exist; not signed in | No | No |
| **Invitee (new email)** | Has a `/join?token=` link; no `users` row | Optional | After accept |
| **Invitee (existing account)** | Same email already has a password | Optional | After accept into *this* org |
| **Signed-in person, no org bound** | Cookie valid, `active_org_id` null | Yes | No (`pick_workspace`) |
| **Owner** | First person at `/setup`, or creator of a workspace, or promoted | Yes | Yes |
| **Admin** | Invited/promoted `admin` | Yes | Yes |
| **Member** | Invited/promoted `member` | Yes | Yes |
| **MCP client** | Bearer `joel_sk_…` API key | No cookie | Key is scoped to one org |
| **Slack mentioner** | `@joel` in Slack; email matches a member of that org | Slack HMAC, not cookie | Org of the Slack connector |
| **Removed person** | Soft-removed: `users` row kept, membership gone | Sessions for that org deleted | None in that org |
| **Multi-org person** | Same `users` row, many `memberships` | One cookie; one `active_org_id` | The bound org only |

There is **no guest, no public signup into an existing company, no SSO, no “viewer” role.**

`Actor.is_admin` is true for **owner and admin**. Almost every “admin-only” API uses that. Owner-only is a short list (promote/demote/remove other owners). Invite-as-owner is not offered in the UI and is rejected by the API.

---

## 2. Capability matrix (workspace-scoped)

Legend: **yes** / **no** / **own only** / **gap** (UI and API disagree, or a leak).

### Identity & company

| Action | Owner | Admin | Member |
|---|---|---|---|
| See Chat / Integrations / Graph chrome | yes | yes | yes |
| Switch / create another workspace | yes | yes | yes |
| Join another company via invite | yes | yes | yes |
| Rename workspace, change domain | yes | yes | no |
| Invite member or admin | yes | yes | no |
| Invite *as owner* | no (API + UI) | no | no |
| Change someone’s role | yes (including to owner) | yes except other owners / promoting to owner | no |
| Remove a member | yes (including owners if another owner remains) | yes except owners | no |
| Remove / demote self below last owner/admin | no | no | n/a |
| See member list | yes | yes | yes (no pending invites) |
| Wipe indexed data for this org | yes | yes | no |
| Pause org-wide sync | yes | yes | see status only |

### Me (the person)

| Action | Owner | Admin | Member |
|---|---|---|---|
| Change display name | yes (global `users` row — all orgs) | yes | yes |
| Change password | yes (global) | yes | yes |
| Sign out | yes | yes | yes |
| Create / revoke **own** MCP API keys for **this** org | yes | yes | yes |
| See someone else’s API keys | no | no | no |

### Settings pages (nav)

| Page | Owner | Admin | Member |
|---|---|---|---|
| General | edit | edit | read name/domain |
| Members | manage | manage | list only |
| Profile | yes | yes | yes |
| API keys | own keys | own keys | own keys |
| Models | yes | yes | hidden + `AdminOnly` |
| Email | yes | yes | hidden + `AdminOnly` |
| Slack bot | yes | yes | hidden + `AdminOnly` |
| Usage | org spend | org spend | org spend (same numbers) |
| Danger zone | wipe | wipe | hidden + `AdminOnly` |

API: `PUT /api/settings`, mail test, Composio key, workspace patch, invites, wipe → `_require_admin`.  
`GET /api/settings` and `GET /api/health` → any signed-in **member** of the org (secrets stripped, but mail host / model names are visible). Health connector list is org rows + *my* personal rows only.

### Integrations

| Action | Owner | Admin | Member |
|---|---|---|---|
| See org-shared connectors (GitHub, Notion, …) | yes | yes | yes |
| **Connect / disconnect / sync / patch** org-shared connector | yes | yes | no (UI + API) |
| Save / clear Composio API key | API admin-only | API admin-only | no (UI hidden) |
| Connect **personal** Gmail or Slack (`owned_by = me`) | yes | yes | yes |
| Connect personal GitHub / Drive / … | no (400) | no | no |
| See another person’s personal Gmail/Slack | **not** on `/api/connectors` | not | not |
| See others’ personal rows on `/api/health` banners | no | no | no |
| Live lookup / ingest uses *my* personal Slack/Gmail if I have one, else org | yes | yes | yes |

Personal providers allowlist: `gmail`, `slack` only (`PERSONAL_CONNECTOR_PROVIDERS`).

### Memory (ask)

| Action | Owner | Admin | Member |
|---|---|---|---|
| Ask in Chat (empty corpus allowed) | yes | yes | yes |
| Read **org**-stamped docs | yes | yes | yes |
| Read **own** Gmail (`user:gmail:{email}`) | yes | yes | yes |
| Read **private Slack channels they are actually in** (email match) | yes | yes | yes |
| Read someone else’s Gmail / private channels they’re not in | no | no | no |
| Forget a cited doc | **removed** (no HTTP, no citation control) | same | same |
| See other people’s chat threads | no (`conversations.user_id`) | no | no |

Web `AskContext` = org + that person’s Gmail alias + Slack channel stamps from `channel_memberships`. Same for MCP (via Actor on the key). Slack bot = same Actor resolved by Slack profile email.

---

## 3. Auth layers (so later SSO doesn’t scatter)

**HTTP (API)** — `api/joel/auth.py`

| Layer | Meaning | Examples |
|---|---|---|
| `public` | No cookie | login, setup, logout, invite peek/accept, Slack events, `/mcp`, healthz |
| `session` | Cookie person, org optional | list/create workspaces, switch workspace |
| `actor` | Cookie person **bound to an org** | ask, connectors, settings, keys |

**Web** — cookie coarse-gate in `web/middleware.ts`; real state from `GET /api/auth/status` via `authDestination()`.

States: `setup` | `login` | `pick_workspace` | `ok`.

---

## 4. Numbered paths

Each path is **who + starting condition → what happens**. Hooked = code does this today. **Gap** = missing, wrong UI, or leak.

### A. First arrival / signup (there is no open signup)

1. **Empty install, hit `/`** — middleware sees no cookie → `/login` → status `setup` → `/setup`. Extra hop. Hooked.
2. **Empty install, hit `/setup` directly** — stays; create company name + you + password → owner of org 1 → land **Chat** (`/`). Hooked.
3. **Empty install, hit `/login`** — redirects to `/setup`. Hooked.
4. **Empty install, hit `/join?token=`** — invite can’t exist yet (no admin). Peek 404. Hooked.
5. **Occupied install, hit `/setup`** — status `login` → `/login`. Hooked. Cannot steal first-owner.
6. **Occupied install, hit `/` unsigned** — `/login`. Hooked.
7. **Occupied install, “Need an account?”** — copy only; no self-serve signup. Must have invite. Hooked.
8. **Setup with company name, no domain** — slug from name, domain `{slug}.local`, initials avatar. Hooked.
9. **Setup with domain only (API)** — name derived from domain (legacy). Hooked.
10. **Second person tries `/api/auth/setup`** — 409. Hooked.

### B. Invitee join

11. **New email, open invite link** — join shows company + invited email + role; name + new password; join → Chat in that org. Hooked.
12. **Invite expired / already used** — 410, “Sign in” CTA. Hooked.
13. **Missing token, `/join`** — paste invite URL/token. Hooked.
14. **Existing account, signed out** — “enter current password” (does **not** reset hash) or go to login with `next=/join?token=`. Hooked.
15. **Existing account, signed in as invitee** — one button, no password; session rebound to new org. Hooked.
16. **Existing account, signed in as someone else** — “wrong account”, sign out, reopen link. Hooked.
17. **Already a member of that org** — 409. Hooked.
18. **Re-invite after soft-remove** — same `users` row; prove old password or sign in; membership restored. Hooked.
19. **Removed person with zero remaining orgs tries login** — 403 “No workspace membership found”. They can still **join via invite + password**. Hooked; awkward.
20. **Admin invites as owner** — UI invite role is member | admin only. API: “Cannot invite as owner — promote after joining”. Hooked.
21. **Mail configured** — invite emailed; links still shown to copy. Hooked.
22. **Mail not configured** — links only; Members “Resend” rotates token. Hooked.

### C. Login / remember / picker

23. **One membership** — login binds that org → `ok` → `next` or `/`. Hooked.
24. **Many memberships, `last_org_id` still a member** — login binds last org, skip picker. Hooked.
25. **Many memberships, last org revoked / null** — `pick_workspace` → `/workspaces`. Hooked.
26. **Picker: choose a company** — `POST /api/auth/workspace` → `/`. Hooked.
27. **Picker: create workspace** — name required, become **owner**, land Chat. Hooked.
28. **Picker: Join workspace** — `/join` (paste link). Hooked.
29. **In-app switcher (top-left)** — switch keeps same path kind (settings stays settings). Hooked.
30. **Switcher: create / join** — same as picker. Hooked.
31. **Hard reload after switch** — `window.location.assign` so org-scoped client state isn’t stale. Hooked (jarring but consistent).

### D. Owner in the product

32. **Owner opens Chat** — welcome; if nothing ingested, banner + composer still works. Hooked.
33. **Owner asks with empty memory** — ask is **not** 409-locked; agent can abstain. Hooked.
34. **Owner → Integrations** — sees all tiles; can connect org tools; can connect personal Gmail/Slack. Hooked.
35. **Owner saves Composio key** (Integrations or when key missing). Hooked (admin API).
36. **Owner connects GitHub (org)** — OAuth → org `connections` row `owned_by NULL`. Hooked.
37. **Owner connects own Gmail as personal** — checkbox → `owned_by = owner`. Hooked.
38. **Owner disconnects org Slack** — member chat loses that credential for live/org ingest; member personal Slack if any still theirs. Hooked.
39. **Owner → Settings → Models** — LLM URL/key/models. Hooked.
40. **Owner skips LLM at onboarding** — Chat + banner “LLM API key not set”. Hooked.
41. **Owner → Email** — SMTP/Resend, test send. Hooked.
42. **Owner → Slack bot** — signing secret. Hooked.
43. **Owner → Members** — invite many, change roles, remove, resend. Hooked.
44. **Owner promotes member → owner** — allowed. Hooked.
45. **Owner demotes self while sole owner** — rejected. Hooked.
46. **Owner → Danger wipe** — deletes docs/conversations/connectors for **this workspace**, people stay. Hooked.
47. **Owner creates a second company** — new org, they are owner there; last_org updates. Hooked.
48. **Owner MCP key** — create in this org; Claude asks with **owner’s** visibility. Hooked.
49. **Owner citation chips** — sources only; no forget control. Hooked.

### E. Admin (not owner)

50. **Admin sees same chrome as owner** (Chat, Integrations, Graph, most settings). Hooked.
51. **Admin cannot remove/change another owner** — 403. Hooked.
52. **Admin cannot promote anyone to owner** — 403. Hooked.
53. **Admin member-row role `<select>`** — Owner option only if the viewer is an owner. Hooked.
54. **Admin can wipe** — same as owner. Hooked (intentional today).
55. **Admin can change Models / Email / Slack bot / Composio**. Hooked.
56. **Admin invited as admin** — join as admin, not owner. Hooked.
57. **Last admin demotes self to member** — blocked if they’d leave zero admin/owner. Hooked.

### F. Member

58. **Member Chat** — same ask pipeline; org memory + own Gmail + private Slack rooms they’re in. Hooked.
59. **Member cannot read owner’s personal Gmail ingest** — personal docs stamped `user:gmail:…`; allowed_stamps only include *asker's* email. Hooked.
60. **Member Integrations** — sees org tiles (status of org GitHub, etc.). Hooked.
61. **Member clicks Connect on Notion** — no Connect in the modal; “Ask an admin to connect this.” Hooked.
62. **Member connects Gmail/Slack** — always personal; no org checkbox. Hooked.
63. **Member Gmail connect** — personal by default (no 403). Hooked.
64. **Member sees Composio key form** — hidden; copy asks them to get an admin to add a key. Hooked.
65. **Member Pause toggle** — read-only “Sync on/Paused”. Hooked.
66. **Member Settings nav** — no Models/Email/Slack/Danger. Hooked.
67. **Member hits `/settings/models` anyway** — `AdminOnly` → general. Hooked.
68. **Member `PUT /api/settings`** — 403. Hooked.
69. **Member General** — cannot rename. Hooked.
70. **Member Members** — list people, no invite/role/remove; pending invites omitted from payload. Hooked.
71. **Member Usage** — sees org-wide LLM spend. Hooked (maybe more than they need).
72. **Member Profile / password**. Hooked.
73. **Member API keys** — own keys, this org only; MCP asks as **member**. Hooked.
74. **Member Graph** — stats/health stub, not a real explorer. Hooked.
75. **Member creates their own workspace** from the switcher — they become **owner of a new tenant** on this install. Hooked (SaaS-normal; odd for a single-company self-host).
76. **Member citation chips** — no forget control; endpoint removed. Hooked.
77. **Member lists Slack channels** on an org Slack connection they can see — `_require_actor`, not mutate. They cannot start ingest (mutate). Mild.

### G. MCP

78. **Create key in org A, use against `/mcp/`** — Actor is that user + org A. Hooked.
79. **Same human’s key from org A cannot read org B**. Hooked (key row has `org_id`).
80. **Revoke key** — 401 on next MCP call. Hooked.
81. **MCP `ask`** — memory only (no follow-up rewrite / live lookup vs web). Documented narrower surface, not a permission hole.
82. **No cookie on `/mcp`** — bearer only; session middleware treats `/mcp` as public. Hooked.
83. **Member MCP vs owner MCP** — same retrieval stamps as that person’s web ask. Hooked.

### H. Slack bot

84. **@joel, Slack profile email = member email** — Actor for that org; reply in thread with their visibility. Hooked.
85. **@joel, email missing / no matching user** — no Actor, no company-brain answer (or silent fail path). Edge: contractors with different Slack email.
86. **@joel in a private channel the user isn’t in** — shouldn’t happen; if membership table stale, visibility still filters stamps. Hooked in principle; membership sync is best-effort.
87. **Slack events URL** — public, HMAC + replay window, not joel_session. Hooked.

### I. Multi-org / switching

88. **Owner of Acme, member of Agency** — switcher lists both; Chat/connectors/keys/settings are **the active org only**. Hooked.
89. **Switch Acme → Agency while on `/settings/models`** — if they’re only a member in Agency, they land on Models URL then `AdminOnly` kicks to General. Hooked (slightly clumsy).
90. **Conversation `?c=` after switch** — switcher strips to `/` so you don’t open another org’s thread id. Hooked.
91. **Display name change in Acme** — name changes in Agency too (one `users` row). Hooked; easy to surprise people.
92. **Password change** — all orgs. Hooked.

### J. Onboarding / empty brain

93. **Founder after setup** — Chat, not forced LLM wall; Skip on `/onboarding`. Hooked.
94. **Visit `/onboarding` later** — skippable checklist (workspace → models → Composio → sources → Slack → people → MCP → voice). Hooked.
95. **Invitee never sees onboarding** — Chat; `/onboarding` bounces members home. Hooked.
96. **OAuth return `return_to=onboarding`** — sources step. Hooked.

### K. Failures & abuse edges

97. **Wrong password login** — 401, no user enumeration beyond “email or password is wrong”. Hooked.
98. **Invite peek without token guess** — 404. Token is unguessable `token_urlsafe`. Hooked.
99. **Two people start personal Gmail OAuth at once** — `pending_connects` unique on `(org_id, toolkit, owner_key)`; callback carries `pending` id. Hooked.
100. **Session expired mid-ask** — 401. Hooked.
101. **Cookie on `/login` already `ok`** — bounce to `next`. Hooked.
102. **`/dev` gallery** — classified **product** (cookie required). Gallery/sim still `notFound()` in production. Hooked.
103. **Health banners** — other people’s personal connectors omitted. Hooked.
104. **GET `/api/composio`** — read-only. Members get `configured` only (no masked key, no accounts). Activation only on OAuth callback. Hooked.
105. **No rate limit on login / setup / invite accept**. **Gap (deferred).**
106. **No SSO / Google / allowed-domain auto-join**. Deferred.
107. **Access leasing** (time-boxed extra room) — not built (`PLAN.md` §17).
108. **Personal connectors for GitHub etc.** — schema could; product does not.

---

## 5. Integrations — what each persona can actually do

### Org-shared (all ten providers)

Connect, disconnect, sync, cancel, patch interval/lookback, Slack channel pick + start ingest: **owner/admin only** (`_require_connection_mutate` when `owned_by IS NULL`).

Members **see** the card (one row: org shared, unless they have their own personal Gmail/Slack which **replaces** the org card in *their* list for that provider).

### Personal (Gmail, Slack only)

Any signed-in member of the org may connect **their** mailbox/Slack user. They can sync/disconnect **their** row. Personal rows are **owner-only** to mutate (`owned_by == actor.user_id`); admins manage org rows only.

Read path: ingest visibility stamps don’t care who clicked Connect; Gmail bodies are `user:gmail:{mailbox}`. Slack private channels use membership table. Org-shared Slack public channels → `org` or channel stamps per adapter.

### Composio key

Workspace setting, admin PUT. Members need an admin to paste it before **any** connect works (personal included). UI hides the key form from members.

---

## 6. UI vs API mismatches

1. ~~Integrations Connect on org-only tools shown to members~~ **fixed**
2. ~~Personal checkbox defaults off for members~~ **fixed** (members always personal)
3. ~~Composio key form shown to everyone~~ **fixed**
4. ~~Invite dialog Owner option~~ **fixed** (member | admin only)
5. ~~Members table role select Owner for non-owner admins~~ **fixed**
6. ~~`GET /api/composio` mutates~~ **fixed** (read-only; members get `configured` only)
7. ~~`GET /api/health` leaks other people’s personal connector status~~ **fixed**
8. ~~Forget doc~~ **removed** (no HTTP, no citation control; storage tombstones kept)
9. ~~Danger/wipe copy “install”~~ **fixed** (“this workspace”)
10. ~~`/dev` unauthenticated~~ **fixed** (product cookie gate)
11. ~~`pending_connects` unique on toolkit~~ **fixed** (`(org_id, toolkit, owner_key)` + pending id on callback)
12. Any member can **create a new tenant** on the same deploy. Left as Mode B by design.

---

## 7. What “admin and member are fine” means in this codebase

Keep teaching:

- **Member** — use the company brain; connect *my* Gmail/Slack; my chats; my MCP keys; no company knobs.
- **Admin** — everything a member can, plus people, models, mail, org connectors, wipe, sync pause.

Implement **owner** as a hidden super-admin until you want a transfer-ownership flow: first creator, promote only from an owner, cannot invite as owner. Do not invent more roles until leasing/SSO.

---

## 8. Left for later

- Members creating another workspace on the same deploy (gap #12 / path 75)
- Guest / SSO / rate-limit / access leasing
- No user-facing forget; historical `docs.forgotten` and canonical `forgotten: true` lines still skip ingest/rebuild

---

## Sources (code)

- Roles / join / last org: `api/joel/identity.py`
- HTTP layers: `api/joel/auth.py`, `SessionMiddleware` in `api/joel/app.py`
- Admin vs actor vs connector mutate: `_require_admin`, `_require_actor`, `_require_connection_mutate`
- Web gate: `web/middleware.ts`, `web/lib/auth/destination.ts`, `web/components/auth-gate.tsx`
- Settings nav: `web/components/settings/settings-nav.tsx`, `admin-only.tsx`
- Integrations: `web/components/integrations/*`, `PERSONAL_CONNECTOR_PROVIDERS`, `_connectors_for_actor`
- Visibility: `api/joel/visibility.py`, `AskContext.web`, `membership.py`
- MCP: `api/joel/mcp_server.py`, `/api/api-keys`
- Slack: `_handle_slack_mention` in `app.py`
