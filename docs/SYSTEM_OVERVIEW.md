# joel — system overview

Short technical map of what exists today and what's genuinely left. `PLAN.md` is the
authoritative living spec (§0.3 has the up-to-date status table) — this doc is a faster
orientation read, not a replacement.

## What joel is

A self-hosted "company brain": one workspace, invited members, ten connectors feeding a
distillation → ontology → retrieval pipeline, answered through a signed-in chat UI, an MCP
server, and a Slack bot. Everything is scoped by who's asking and what rooms they're in — no
client-supplied visibility, always derived server-side from the actor.

## Architecture at a glance

```
connectors (Composio proxy)  →  distill (LLM, one artifact per thread)
                              →  ontology (extract → resolve → reconcile → graph edges)
                              →  store (SQLite FTS5 + vectors + HydraDB graph, 3 destinations
                                 written from one upsert call)
                              →  retrieve (6 lanes → RRF fuse → LLM rerank → answer w/ abstention)
                              →  surfaces (web chat SSE, MCP /mcp/, Slack bot)
```

- **SQLite** (`data/index/joel.db`) — canonical docs, FTS5, jobs, connections, identity/workspace
  tables, settings.
- **Vectors** — local sentence-transformers embeddings, hot-reloaded npz (`joel/store.py`
  `LiveIndex`), never a startup-only load.
- **HydraDB** — the graph: ontology entities/relations, `MENTIONS`, the reversal ledger
  (`(:Doc)-[:REVERSED]->(:Doc)`), WHO_KNOWS traversal. Local OpenCypher, Bolt/HTTP.

## What's built

**Identity & workspace** — `api/joel/identity.py`: multi-workspace Mode B. Global users,
memberships with `owner` / `admin` / `member`, sessions with `active_org_id`, invites
scoped by `org_id`, API keys per org. Cookie sessions; `/workspaces` picker when a user
belongs to more than one org. See [`SAAS_SKELETON.md`](SAAS_SKELETON.md) and
[`adr/0003-mode-b-multi-workspace.md`](adr/0003-mode-b-multi-workspace.md).
Workspace settings (LLM, mail, Composio, org connectors) are admin/owner-only; members
manage profile/password/API keys and personal connectors.

**Outbound email (optional)** — `api/joel/mail/`: none / SMTP / Resend. When configured,
invites are emailed; links are always recoverable via Resend on the Members page.

**Tenancy** — business data (`docs`, `connections`, `conversations`, `settings`, spend,
vectors `org-{id}.npz`, Hydra namespace `joel-org-{id}`) is scoped by active workspace.

**Visibility & permissions** (`api/joel/visibility.py`, `membership.py`) — every doc is stamped
`org` / `channel:slack:C…` / `user:gmail:…` at ingest. `POST /api/ask` builds the actor's
`AskContext` server-side: org + their own Gmail + every private Slack channel they're actually
a member of (matched by email, `joel/membership.py`). No lane ever sees an unstamped or
client-chosen room.

**Ten connectors** (`api/joel/connectors/`, `api/joel/adapters/`) — Slack, Gmail, GitHub, Jira,
Confluence, Fireflies, Linear, Notion, Google Drive, HubSpot. All go through Composio as the
sole auth broker (`composio_conn.py`) — joel never stores a raw OAuth token. Lookback re-fetch
+ `content_hash` change detection, a concurrency-capped background scheduler with a real
`Retry-After`-honoring 429 backoff ladder, zombie-job reclaim on boot, and a progressive
backward-walking deep-backfill pass for Slack/Gmail beyond the fast-pass window. Personal vs.
org-shared connectors are real for Gmail/Slack (`UNIQUE(provider, owned_by)`, personal-then-
org-shared read resolution) — the other eight providers stay org-only.

**Distillation** (`api/joel/distill/`) — burst-grouped threads → one structured artifact per
dirty thread via `prompts/distill_thread.md`, re-distilled whole (never delta) on later syncs.

**Ontology** (`api/joel/ontology/`) — `extract.py` (entities/relations via
`prompts/extract_ontology.md`), `resolve.py` (blocking → fuzzy score → LLM tie-break funnel,
cached forever by pair, `data/entities/registry.json`), `reconcile.py` (explicit supersession >
recency-unless-formal > source-authority ladder, incremental — only touched entity-predicate
pairs re-run, not the whole corpus).

**Retrieval** (`api/joel/retrieve/`) — all six lanes (VECTOR, VEC-ARTIFACTS, FTS, PHRASE,
GRAPH, WHO_KNOWS) run concurrently, each honoring `allowed_stamps(ask)`, fused with RRF(k=60),
LLM-reranked, answered with explicit abstention (`absent`/`partial`/`conflicted`/`answered`)
and citations.

**Agent tier** (`api/joel/agent/`) — `working_memory.py` does follow-up question rewriting
(pronoun/ellipsis resolution against recent turns, skips the call for already-standalone
questions or chitchat); `live.py` does whitelisted read-only live lookup — **GitHub PR/issue
state and Slack "latest message in a channel" only, so far** — capped, timed-out, and written
through the same `store.upsert_docs` path as ingest so a live fetch becomes durable memory
exactly like anything else.

**Surfaces**:
- Web chat (`web/app/(product)/chat`, `chat-surface.tsx`) — SSE stream of
  `status/rewritten/plan/lane/live/token/citations/reasoning_path/done`, all consumed
  (fixed 2026-08-20 — `lane`/`live` were previously parsed but silently dropped).
- MCP server (`api/joel/mcp_server.py`) — real Streamable HTTP at `/mcp/`, one `ask` tool,
  bearer API-key auth resolving to a normal `Actor`, same `AskContext`/`answer_question` path
  as web.
- Slack bot (`api/joel/slack_bot.py`) — `POST /api/slack/events`, real HMAC signature
  verification + replay-window check, `app_mention` → actor resolved by the mentioning Slack
  user's email → real in-thread reply.

**Ops** — `/api/health` (HydraDB reachability, schema version, index-consistency check across
SQLite/npz/graph counts, queue depth, LLM error surfacing), degraded-mode banners when a
connector needs reauth or is mid-sync, `rebuild_index.py` for a from-canonical rebuild,
`data/state/*.jsonl` retry ledgers for partial-write recovery, `traces.jsonl` for lane/rerank
debugging.

**Frontend** (`web/`) — Next.js app router: `/setup`, `/login`, `/join`, `/(product)/chat`,
`/integrations`, `/settings`, `/graph` (still a stats/health stub, not a real graph visualizer),
`/onboarding`. `web/components/integrations/*` handles connect/disconnect, personal-vs-org
checkbox, backfill-progress copy, reauth. `web/components/api-keys-panel.tsx` and the Slack
signing-secret field in `install-panel.tsx` are the MCP/Slack-bot settings UI.

## What's explicitly cut (not gaps — deliberate, documented in `PLAN.md` §17)

- **Access leasing** — the one remaining item on the permissions-graph roadmap; personal
  connectors shipped first as the higher-value increment. No timeline pressure to build it.
- **hnswlib swap** for the vector index — current flat/npz approach is fine under ~250K docs.
- Deeper job-history UI, multi-conversation sidebar beyond what exists — already minimal by
  design.

## What's a real, honestly-scoped partial (not cut, just narrower than ideal)

- **Live lookup** covers 2 of the 10 providers (GitHub, Slack). Extending it to more
  (e.g., Linear issue state, Notion page freshness, a Jira ticket status) is the same pattern
  already established in `agent/live.py::detect_live_targets`/`fetch_live_target` — each new
  provider is a small, additive branch, not a redesign.
- **Personal connectors** exist only for Gmail/Slack. The other eight providers could get the
  same `owned_by` treatment if a use case shows up (e.g., a personal GitHub token vs. an
  org-wide one) — schema already supports it (`UNIQUE(provider, owned_by)`), it's just unused
  for those providers.
- **`/graph` page** renders corpus/health stats, not an actual node/edge visualization — the
  real graph surface today is the "reasoning path" shown in chat answers, per `PLAN.md` §1.1.
  A real graph explorer (even read-only, a few hops around an entity) is a legitimate follow-up
  if the ontology work should become more discoverable than "trust the chat citations."

## What can genuinely still be added

1. **Access leasing** (§17 cut item 7) — time-boxed elevated access to a room beyond an
   actor's normal membership, for cases like "let support see this one private channel for an
   hour." Natural next increment of the permissions graph now that personal-vs-org read
   resolution is proven.
2. **More live-lookup providers** — Linear/Jira ticket status, Notion page last-edited, a
   HubSpot deal stage check. Same code shape as the existing two, no architecture change.
3. **A real graph explorer page** — read-only entity neighborhood view using the same HydraDB
   queries WHO_KNOWS/GRAPH lanes already run, surfaced visually instead of only as chat
   citations.
4. **Personal connectors for more providers** — schema is ready; wiring is per-provider.
5. **Digests** — mentioned in `PLAN.md` §1.1 as an explicit not-yet-built idea (a periodic
   "what changed" summary per room/channel), distinct from live chat.
6. **Agent write-actions** — also explicitly out of v1 scope in `PLAN.md` §1.1/§1.3 (Sentra's
   "action memory" layer) — e.g., joel filing a Linear issue or replying in a thread on its own
   initiative, not just answering when asked. Meaningful scope increase, not a small add-on.
7. **Billing** — noted as not-built in `PLAN.md` §1.1; only relevant if this moves toward a
   multi-tenant hosted product rather than a self-hosted single-org install.
8. **The manual ship-checklist items** (`PLAN.md` §15) that need a human, not more code: a
   clean-clone `docker compose up` run on pruned Docker, a real OAuth consent-screen pass for
   all ten providers in a browser, and an unattended overnight soak test.

## Where to look next

- `PLAN.md` §0.3 — always-current status table (source of truth over this doc if they ever
  drift).
- `PLAN.md` §22 — the full phase-by-phase checklist.
- `scripts/check_*.py` — one live-verification script per checkpoint; the convention this
  whole project follows is "real HydraDB, real LLM calls, real corpus data, real browser/API
  hits," not synthetic-only coverage.
