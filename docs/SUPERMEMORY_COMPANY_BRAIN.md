# Supermemory Company Brain — source dump

Fetched 2026-08-20 from the public docs index ([llms.txt](https://supermemory.ai/docs/llms.txt)) and each Company Brain page. This is a faithful product dump for comparing **setup / onboarding / configuration** with joel. Slack mock threads are reduced to intent, not reproduced as JSX.

Setup comparison vs joel (what to build next): [`SETUP_VS_SUPERMEMORY.md`](./SETUP_VS_SUPERMEMORY.md).

Index of pages: [Company Brain overview](https://supermemory.ai/docs/company-brain/overview) through [Meeting scheduling](https://supermemory.ai/docs/company-brain/use-cases/meeting-scheduling).

---

## What is Supermemory Company Brain?

Source: [overview](https://supermemory.ai/docs/company-brain/overview)

A **super agent with shared team memory** that you can **ask** and that can **act in tools**. It pulls from Slack, docs, GitHub, Linear, etc., and is meant to behave like a coworker, not a search bar.

Three demo modes:

1. **Ask** — e.g. “what did we decide about pricing?” → cited answer from a huddle.
2. **Act** — e.g. “is this Sentry timeout tracked?” → opens a Linear issue, assigns someone, links the Sentry issue.
3. **Speak unprompted** — e.g. “is prod down?” in `#eng` → answers from live Sentry without an @mention.

**Surfaces:** Slack is the default. Same knowledge via **coding agents** (Claude Code, Cursor) and **MCP**. Same permissions graph everywhere — asking from Claude Code does not get you more than Slack would.

**Admin knobs called out on this page:**

- **Any model, no markup** — bring your own LLM; no extra inference charge.
- **Tonality** — how it talks, from professional to unhinged.

Next reads they push: [permissions](https://supermemory.ai/docs/company-brain/permissions), [setup](https://supermemory.ai/docs/company-brain/setup).

---

## Setup and Onboarding

Source: [setup](https://supermemory.ai/docs/company-brain/setup)

**Two admin steps.** Everyone else joins later (see Greeting).

### 1. Create the team workspace

1. Account at [app.supermemory.ai](https://app.supermemory.ai).
2. **About** step: switch **Personal → Team**. Team workspaces are invite-only in private beta (email support, or start Personal and invite later).
3. Enter **company domain** (e.g. `acme.com`). Supermemory **researches the company from the domain** and **seeds a starting profile** before any connector finishes syncing.
4. Three things run **in parallel** with research; **none block it**:
   - **Add to Slack** — starts the install below.
   - **Connect apps** — Linear, Granola, Sentry, and more.
   - **Invite teammates** — now, not later. Docs say **no per-seat pricing**, invite everyone in Slack.
5. When research finishes, Slack DM walks the admin through what it can do.
6. Smoke test: `What does {your company} do?` should answer from the **seeded profile**.

Creating a workspace also creates shared **Team Brain** and private **My Brain** in one step.

### 2. Install into Slack (admin)

Company Brain installs into an **existing** Slack workspace; it does not create Slack for you.

1. **Install to Slack**. If the clicker is not a Slack admin, Slack’s own **request-to-install** flow runs instead.
2. Web app hands off: “we’ve DM’d you in Slack.”
3. Agent creates **`#company-brain`**, posts an intro there, and announces once in **`#general`**.
4. **You approve each channel with a tap** — it never joins a channel silently.
5. Invite people with a **picker**, a **workspace-wide toggle**, or **email**.

---

## The Permissions Graph

Source: [permissions](https://supermemory.ai/docs/company-brain/permissions)

Not “a shared brain plus a private brain.” Memory is written to the **narrowest room** the conversation happened in. Nothing is silent: every install, channel read, and temporary access grant needs an explicit accept.

### Three memories

| Memory | Scope | Who can see it |
|---|---|---|
| **Employee** | One per person. DMs with the bot + what it learns about you | Only from **your** DM |
| **Private channel** | One per private channel | Anyone **in that room**, nobody outside |
| **Organization / public channel** | Durable facts from public channels | Whole org |

A message writes to **exactly one**.

### What a conversation can read

Writing is narrow; reading widens as the room gets more private:

| Asking from | Can read |
|---|---|
| Public channel | Public channel memory |
| Private channel | That channel + public |
| DM with the bot | Your employee memory + public + **every private channel you belong to** |

If you are not in a private channel, that memory does not exist for you — not even by inference in a DM. The bot only reads with the **asker’s** access. Citations say which room the answer came from.

### Tool access

GitHub / Linear / etc. connect two ways, **on the same connections page**:

- **Organization (shared)** — admin, fallback the team can read from.
- **Personal (yours)** — your reads and your actions.

Results are still bounded by what **you** could see or do in that tool. No standing key to “everything Linear knows.”

| | Reads | Writes |
|---|---|---|
| Behavior | Personal first, then org-shared | **Always under your own connection** |
| Why | Fullest access you’re entitled to | Attribute the action to a real person |

Admins can also act through the org-shared connection when that is the point.

### Leasing

If neither you nor the org has a tool, but a teammate does, Company Brain can **post a Slack card** asking them to approve lending access **for that one request**. Not silent, not standing. Last resort when nobody connected the tool at org level.

### API keys

A scoped / agent API key can only reach what its **owner** could reach by asking. Same graph for people and keys.

---

## Connectors

Source: [connectors](https://supermemory.ai/docs/company-brain/connectors)

Two kinds, same connections page, different jobs:

| | Data connectors | Tool connectors |
|---|---|---|
| Job | Bring knowledge **in** | Let the agent **act** |
| Examples | Google Drive, Notion, OneDrive | GitHub, Linear, Sentry, Plain, PostHog, Granola |
| Result | Docs in **public channel memory**, searchable | Live reads/writes (list PRs, create issues, check errors) |
| When | Background sync on a schedule | In the moment you ask |

**Data connectors** are a **team-level** admin action. Indexed content is org-wide, like a public channel. Advice: start with the handful of sources people actually re-read.

**Tool connectors** are live (MCP under the hood). Also: **custom MCP servers** when the catalog doesn’t cover a tool.

Personal vs org + leasing: same rules as the permissions page.

Which to use:

- “What’s in our Q2 roadmap?” → data (Drive/Notion/OneDrive).
- “My open PRs” / “Create a Linear issue” → tool (GitHub / Linear).
- “What did we decide in the Acme call?” → Granola (tool that also brings knowledge) or Drive/Notion if notes live there.

You almost always want both.

---

## Automations and Proactiveness

Source: [automations](https://supermemory.ai/docs/company-brain/automations)

Both opt-in, rate-limited, same permissions graph. Neither is a backdoor.

### Automations

A **plain-language prompt on a schedule** that posts somewhere. Created by asking in Slack, or managed as a **full list in the web app**.

Runtime rules:

- Wakes on schedule; nobody triggers it.
- Reads using **org-shared connections and channel memory only** — never the creator’s personal credentials.
- Re-confirms it can still see the destination channel before posting.
- If a connection broke or visibility can’t be verified: **skip the run**. Silence beats a wrong digest.

| Destination | Who can create | Reads from |
|---|---|---|
| Public channel | Any member | Org-shared + public channel memory |
| Private channel | **Admins only** | Org-shared + that channel’s memory |
| DM to yourself | Owner of that DM | Personal + org + employee memory |

Anyone can manage **their** automations; admins can manage **everyone’s**.

Examples: Monday digest, daily Sentry recap in `#eng`, weekly “what changed.”

### Proactiveness (chime-in)

No schedule, nobody asked. The bot is present because an **admin invited it into the channel**. It speaks only when it adds a fact/correction/next step, from allowed sources, and is confident. Uncertainty → silence.

Guardrails:

- Rate-limited (won’t spam a thread).
- **Invite-only rooms** — never joins a channel on its own.
- Same graph as a normal answer.
- An explicit **@mention always skips the judgment call**.

Outputs write back to memory the same way as normal conversation (public → public memory, private → that channel).

---

## Using Outside Slack

Source: [outside-slack](https://supermemory.ai/docs/company-brain/outside-slack)

Same MCP server as general Supermemory MCP — **no separate Company Brain URL**:

```
https://mcp.supermemory.ai/mcp
```

- **OAuth by default** — client discovers the auth server and signs in.
- **API key** starting with `sm_` skips OAuth.

If the account belongs to an org with Company Brain, the client sees more than personal project spaces: **employee memory, private channels you’re in, public channel memory** — same role and access as Slack.

**Pick a workspace:** ask what’s available → container tags (employee / each private channel / public) → select one for the session. Everything after that scopes to it (same as asking from that Slack room).

| MCP tool | Job |
|---|---|
| `listContainerTags` | Everything you’re allowed to read, names and counts |
| `select-workspace` / `set-active-tag` | Active container for the session |
| `recall` | Search active workspace (+ profile summary in employee memory) |
| `save-memory` | Write back to active workspace |
| `memory-graph` | Visual map of a workspace’s memories |
| `whoAmI` | Role, access type, active workspace |

Admins can **restrict a member’s connection to specific container tags** the same way they’d scope a Slack channel invite.

---

## What You Can Do (use-case index)

Source: [use-cases/overview](https://supermemory.ai/docs/company-brain/use-cases/overview)

**Shipped today:** automatic support; incidents & digests; meeting recall; answering from docs; acting in tools; greeting new teammates; sandbox debugging.

**Coming soon:** long-horizon research; meeting scheduling.

Walkthroughs assume the concept pages (permissions, setup, connectors, automations).

---

## Automatic Support

Source: [support](https://supermemory.ai/docs/company-brain/use-cases/support)

Customer question in `#support`. Bot is already a **member of the channel** (admin invited it). **Chimes in unprompted** from help docs (public channel memory) + **Plain** tickets. Same channel-scope write-back as permissions.

Setup implication: invite the bot into `#support`; connect Plain; connect help docs as a data source.

---

## Incidents & Downtime Chatter

Source: [incidents](https://supermemory.ai/docs/company-brain/use-cases/incidents)

“Is prod down?” → live **Sentry** via tool connector (chime-in or @mention). Separate **automation**: daily error digest to a channel, **org-shared connections only**. Private channel automations: admin-only destination, fail closed if visibility can’t be verified.

Setup implication: connect Sentry (org-shared for digests); invite bot to `#eng`; optionally create the digest automation.

---

## From Support Ticket to Code Fix

Source: [support-escalation](https://supermemory.ai/docs/company-brain/use-cases/support-escalation)

Plain ticket unfurls in `#support` → chime-in with GitHub + product context → someone **@mentions Cursor** → Cursor is a **custom MCP tool connector** that **acts** (opens an agent thread, can push a PR). Writes only happen on **explicit @mention**, not chime-in. Connection is personal or org-shared, same permissions rules.

Setup implication: Plain + GitHub + **custom MCP (Cursor)** on the connections page.

---

## Meeting Recall

Source: [meeting-recall](https://supermemory.ai/docs/company-brain/use-cases/meeting-recall)

“What did we decide with Acme?” → **Granola** (or Drive/Notion if notes live there) synced into **public channel memory**, cited.

Setup implication: connect Granola and/or the docs store where notes land.

---

## Answering from Your Docs

Source: [knowledge-recall](https://supermemory.ai/docs/company-brain/use-cases/knowledge-recall)

“What’s in our Q2 roadmap?” → **data connector** (Notion / Drive / OneDrive) into public channel memory. Re-sync on a schedule; no re-upload.

Setup implication: admin connects the wiki/docs source and points it at the useful subset.

---

## Acting in Tools

Source: [acting-in-tools](https://supermemory.ai/docs/company-brain/use-cases/acting-in-tools)

Reads: “my open PRs” → GitHub, personal then org. Writes: “create a Linear issue” → **always under your account**. Lease if nobody has the tool.

Setup implication: personal GitHub/Linear for writes; org-shared as read fallback.

---

## Greeting New Teammates

Source: [greeting](https://supermemory.ai/docs/company-brain/use-cases/greeting)

This **is** the member join flow, told as a scenario. **No web signup** for the new hire. Admins still do workspace + Slack install on the web.

1. New hire joins the **Slack** workspace.
2. They get a **Connect me** card, tap it.
3. Welcome DM: what it knows, what it can access, what it keeps private. Three starter questions (e.g. What does Acme do? Who owns onboarding? Where do we track bugs?).
4. First answer comes from the **company profile the admin seeded at setup**.
5. After the first answer, prompt to **connect personal tools** (Linear, Notion).

Under the hood: tap creates a **passwordless account from Slack email**, provisions **employee memory**, **consumes a seat**. Starter questions are seeded so the first useful answer happens on the first tap.

---

## Sandbox Debugging

Source: [sandbox-debugging](https://supermemory.ai/docs/company-brain/use-cases/sandbox-debugging)

Ask it to reproduce a failing test. It spins an **isolated workspace**, checks out code, runs the command, reports. Guardrails: no `git push`, no deploys, no `sudo`, no arbitrary internal network, no long-running servers.

This is an **agent capability**, not a settings page — listed here because the docs treat it as a shipped surface.

---

## Long-Horizon Research

Source: [long-horizon-research](https://supermemory.ai/docs/company-brain/use-cases/long-horizon-research)

**Coming soon.** Multi-source briefs. Today: break the question into smaller ones. No extra setup surface documented beyond existing connectors.

---

## Meeting Scheduling

Source: [meeting-scheduling](https://supermemory.ai/docs/company-brain/use-cases/meeting-scheduling)

**Coming soon.** **No calendar connector in the catalog today.** Future: tool connector, writes under your account (or a lease). Until then, ask for context (“who’s the right person?”) and book normally.

---

## Catalog of setup surfaces (across all pages)

User- or admin-facing configuration the docs actually describe:

1. **Hosted account** at app.supermemory.ai (Personal vs Team).
2. **Domain → company research → seeded profile** (unblocks “what does Acme do?” before sync).
3. **Parallel first-run:** Add to Slack + Connect apps + Invite teammates (none block research).
4. **Slack OAuth install** (“Install to Slack” / request-to-install).
5. **Auto-create `#company-brain`** + one announce in `#general`.
6. **Per-channel join approval** (never silent).
7. **Invite:** picker, workspace-wide toggle, or email. (Docs also say no per-seat pricing; greeting page still says Connect me **consumes a seat**.)
8. **Member activation in Slack:** Connect me card, passwordless from Slack email, employee memory, starter questions, then personal-tool prompt.
9. **Connections page:** data connectors vs tool connectors; org vs personal; **custom MCP servers**.
10. **Catalog (docs):** Drive, Notion, OneDrive (data); GitHub, Linear, Sentry, Plain, PostHog, Granola, Cursor-as-custom-MCP (tools). Calendar **not** in catalog yet.
11. **Leasing:** Slack approve/deny card for one request.
12. **Automations:** create in Slack in plain language; **manage list in the web app**; destination rules (public / private-admin / self-DM).
13. **Chime-in:** admin invites the bot into a channel (the setup act); rate limits and silence-on-uncertainty are product behavior.
14. **MCP:** `https://mcp.supermemory.ai/mcp`, OAuth or `sm_` key; workspace/container picker; tools listed above; admin can restrict tags.
15. **Bring-your-own LLM** (no extra inference markup).
16. **Tonality** of the agent.
17. **API keys** inherit the owner’s graph.

---

## Sources

- [Overview](https://supermemory.ai/docs/company-brain/overview)
- [Setup](https://supermemory.ai/docs/company-brain/setup)
- [Permissions](https://supermemory.ai/docs/company-brain/permissions)
- [Connectors](https://supermemory.ai/docs/company-brain/connectors)
- [Automations](https://supermemory.ai/docs/company-brain/automations)
- [Outside Slack](https://supermemory.ai/docs/company-brain/outside-slack)
- [Use cases](https://supermemory.ai/docs/company-brain/use-cases/overview) and the eleven child pages linked from there
- Index: [llms.txt](https://supermemory.ai/docs/llms.txt)
