# Setup gap: joel vs Supermemory Company Brain

**Scope:** onboarding, Slack install, people, connectors-as-a-catalog, MCP wiring, and settings knobs. **Not** retrieval quality, distillation, graph, or how smart the agent is — those come later.

Supermemory source dump: [`SUPERMEMORY_COMPANY_BRAIN.md`](./SUPERMEMORY_COMPANY_BRAIN.md).  
joel sources: `README.md`, `web/app/setup/page.tsx`, `web/components/onboarding-flow.tsx`, `web/components/settings/*`, `web/lib/integrations.ts`, `api/joel/mcp_server.py`, [`PERSONA_PATHS.md`](./PERSONA_PATHS.md).

---

## How the two first-runs feel

### Supermemory (hosted, Slack-native)

Admin: sign up → Team → **type domain** → product researches the company and **seeds a profile** so Chat/Slack already has an answer. **In parallel** (nothing waits): Install Slack, connect apps, invite everyone. Slack install is **one OAuth button**. Bot creates `#company-brain`, announces in `#general`, then **asks before joining each channel**. New hires never open a web form: Slack **Connect me** card → passwordless account from Slack email → welcome DM with three starter questions → then “connect your Linear.”

Default surface is **Slack**. Web exists for admin setup and automations list. MCP is the same graph with OAuth.

### joel (self-host, web-native)

Operator: env + Hydra + API/web (or Docker) → `/setup` (company name, optional domain, **password**) → land in **web Chat**. Optional `/onboarding` is the same settings in one skippable checklist (about, models, Composio, sources, Slack bot, people, MCP snippet, voice). Teammates join via **Settings → Members** (copy link or outbound email). Slack bot: create your app from the repo manifest, paste Events URL + signing secret + **bot token**, `/invite @joel`. Mentions work if the Slack profile email matches a joel user. MCP is a **bearer API key** and one `ask` tool at this origin.

Default surface is **web Chat**. Slack and MCP are extras you wire by hand.

---

## What joel already has (don’t rebuild)

| Surface | joel today |
|---|---|
| First workspace | `/setup` — company name, optional domain, owner password |
| Skip LLM / tools | Onboarding checklist (workspace → voice), all skippable; Chat unlocked empty |
| Invite people | Settings → Members; comma emails; copy links; SMTP/Resend |
| Org vs personal connectors | Org tools admin-only; Gmail/Slack can be personal |
| Ingest catalog | **Indexed** vs **Live** on Integrations. Slack, Gmail, Notion, Drive, Jira, Confluence, HubSpot, Fireflies indexed; GitHub, Linear live (still ingest in v1) |
| Slack **mention** bot | Settings → Slack bot: manifest, events URL, signing secret, **bot token**; `/invite @joel` |
| MCP **ask** | Settings → API keys; snippet for `https://<this-origin>/mcp/`; key maps to that person’s AskContext |
| Models | Settings → Models (base URL + key) — closest to SM “bring your own LLM” |
| Voice / about | Settings → General (`voice`, `workspace_about`) injected into the answer prompt |
| Roles | owner / admin / member; invite is member\|admin |

---

## What’s missing — setup only

Ranked by how much it changes “a team actually turns this on,” not by agent cleverness.

### 1. Slack is not the install path

**SM:** Install to Slack (OAuth). Request-to-install if you’re not a Slack admin. Bot bootstraps `#company-brain` + `#general` announce. **Every channel join is an explicit tap.**

**joel:** Admin creates a Slack *app* from the repo manifest, pastes Request URL, signing secret, and bot token, then `/invite @joel`. No OAuth install, no channel-join UI, no bootstrap channel. Bot only answers **@mentions**, and only if Slack email ∈ `users.email`.

**Gap to close (setup):** one-click Slack install; channel picker / approve-to-join; stop requiring a custom Slack app tutorial for the happy path. Chime-in *behavior* can wait; **being in the room** is setup.

### 2. New hire activation is web-only

**SM:** Connect me in Slack → passwordless from Slack email → employee memory + starter questions from the seeded company profile → prompt to connect personal tools. Admins still use the web once.

**joel:** Invite link → `/join` → name + password (or existing password). No Slack card, no passwordless Slack identity, no seeded “what does this company do?” before connectors sync, no first-run personal-tool prompt.

**Gap to close:** Slack identity as join (email match already exists for mentions); a first-session script (welcome + 2–3 questions) that does not depend on ingest being done.

### 3. First-run is serial and empty

**SM:** Domain research **seeds a company profile in parallel** with Slack + apps + invites. Smoke test works before Drive finishes.

**joel:** Domain is an optional slug. Nothing is researched. Until an admin pastes an LLM key **and** a Composio key **and** a connector lookback, Chat has nothing company-shaped to say. Onboarding is LLM *then* tools, even though both are skippable.

**Gap to close:** parallel “Slack / tools / people” on first run (not a forced LLM wall — that’s already skippable). Optional: seed a short company blurb from the name/domain the owner typed, so “what does {company} do?” isn’t empty. Full web-research-the-company can wait.

### 4. Connections page is ingest-only, not “data vs tools”

**SM** splits the same page:

- **Data** (Drive, Notion, OneDrive) → index into org memory, schedule sync.
- **Tools** (GitHub, Linear, Sentry, Plain, PostHog, Granola, **custom MCP**) → live read/write. Personal vs org. Writes always as you.

**joel** has one Integrations grid. Every connectable tile is **ingest** (lookback, sync, doc count). GitHub/Linear are treated like Notion: pull history, don’t “list my PRs / create an issue” as a live tool. No OneDrive, Sentry, Plain, PostHog, Granola (we have Fireflies instead). No **Add your MCP server**. Personal scope is only Gmail/Slack.

**Gap to close (setup/catalog, not agent quality):**

- Label tiles **Memory** vs **Live tool** (even if live tools are stubs at first).
- Org-shared **and** personal for GitHub/Linear (SM’s write path needs personal).
- A “custom MCP URL” row for Cursor-class tools.
- Decide whether Sentry / Plain / Granola / OneDrive are in v1 of the catalog.

Acting on Linear from Slack is later (agent). **Offering the connection type** is setup.

### 5. MCP is a key, not a sign-in

**SM:** `https://mcp.supermemory.ai/mcp` + OAuth (or `sm_` key). Then **pick a workspace** (employee / `#eng` / public). Tools: list tags, select workspace, recall, save-memory, memory-graph, whoAmI. Admin can restrict which tags a member’s client sees.

**joel:** mint `joel_sk_…` in Settings → API keys. One tool: `ask`. No OAuth, no container picker, no save-memory, no whoAmI. Key is org-scoped to that person — correct graph, but Cursor/Claude Code setup is “paste a key,” not “Sign in to joel.”

**Gap to close:** documented MCP URL in product UI; OAuth or at least a copy-paste client config; a picker for **org vs my Gmail vs this Slack channel** if we keep those as rooms. Extra MCP tools can wait; **getting Cursor attached** is setup.

### 6. No automations surface

**SM:** say a digest in Slack, or manage the list on the web. Destination rules (public / private-admin / self-DM). Scheduled runs use **org** credentials only.

**joel:** scheduler exists for **connector sync**, not for “every Monday post to `#eng`.” No automations settings page.

**Gap to close:** a settings (or Slack) place to create a named prompt + cron + destination. Runtime can be dumb at first; the **knob** is what’s missing.

### 7. No tonality / voice setting

**SM:** explicit control, overview page.

**joel:** Settings → Models is URL + key + model names. No “how it talks.”

**Gap to close:** one workspace string (and maybe a preset: professional / dry / unhinged) injected into the system prompt. Tiny setup; skip until Slack-first works if you have to cut.

### 8. Leasing has no UI (and no API)

**SM:** Slack card, one request, teammate taps yes/no. Fallback when org hasn’t connected the tool.

**joel:** `PERSONA_PATHS` / PLAN still list leasing as not built.

**Gap to close:** later than 1–5. Needs personal GitHub/Linear first or there’s nothing to lease.

### 9. Operator setup SM never asks for

joel is self-host. SM hosted. These are **ours**, not gaps vs SM — keep them, just don’t pretend SM has them:

- `.env` / Docker / Hydra
- `JOEL_SECRET`, `JOEL_WEB_ORIGIN`, HTTPS cookie
- **Composio API key** (all OAuth goes through it)
- Password login (SM members are passwordless from Slack)

The Composio key is the sharp edge: members cannot connect Gmail until an admin pastes it. SM never shows a third-party OAuth broker to the customer.

---

## Suggested setup sequence (when we implement)

Do **not** start with sandbox debugging, long-horizon research, calendar, or “smarter answers.”

1. **Slack install that a non-engineer can finish** — OAuth app, channel join approvals, bootstrap channel. Keep mention-to-answer working.
2. **Join from Slack** — Connect-me equivalent; bind Slack email to a membership without a password form.
3. **First-run parallel rail** — people + Slack + tools on one screen; optional company blurb so Chat isn’t mute.
4. **Connections page: Memory vs Live + custom MCP URL** — catalog honesty. Personal GitHub/Linear.
5. **MCP attach story** — URL + OAuth or one-click Cursor/Claude snippet; workspace/room picker.
6. **Automations list** (web).
7. Tonality. Then leasing.

Agent, memory depth, chime-in judgment, write-to-Linear, sandbox: **after** this list.

---

## Explicitly out of this comparison

- Quality of answers, citations, distillation, ontology.
- Whether chime-in is “smart enough.”
- Sandbox execution, Cursor handoff, calendar booking, long-horizon briefs.
- Billing / seats (SM docs contradict themselves: setup says no per-seat pricing; greeting says Connect me consumes a seat).
