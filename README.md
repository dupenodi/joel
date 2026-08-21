# joel

A self-hostable company brain. Connect tools, distill them into shared memory, and answer questions scoped to **who is asking** and **which room they are in**. Visibility is always derived server-side — the client never chooses the readable set.

Members are invited; there is no open signup into someone else's workspace. One person can belong to many workspaces on the same install.

**Surfaces:** web chat, MCP (`ask`), Slack bot.

**Stack in short:** connectors (Composio) → distill-then-embed → entity resolution → HydraDB ontology + decision-reversal ledger → retrieval with abstention.

Deeper map: [`docs/SYSTEM_OVERVIEW.md`](./docs/SYSTEM_OVERVIEW.md). Domain language: [`CONTEXT.md`](./CONTEXT.md).

## Status & limitations

This is a usable local product, not a finished hosted deployment.

I prioritized onboarding, connectors, chat, and UX — how I'd actually want this to work. The trade-off: I did not get the full stack hosted end-to-end, and I did not run the benchmark eval. The pieces are in the code; they are not shown as a clean production deploy or as numbers I didn't produce.

Concretely:

- Implemented and visible in code: architecture, ingestion (distill-then-embed), entity resolution, HydraDB ontology + reversal ledger, retrieval/abstention, chat / MCP / Slack.
- No benchmark figures. I would rather omit them than invent them.
- Self-hosting still has rough edges (env, HydraDB, first-run). Local `docker compose` / the two-process quick start is the intended path.

If it is useful, I can walk through the code, the design decisions, or a live run of what works on a machine.

## Quick start

```bash
cp .env.example .env   # fill HYDRA_* / JOEL_SECRET / optional COMPOSIO_API_KEY

# API
cd api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
JOEL_DATA=../data .venv/bin/uvicorn joel.app:app --reload --port 8000

# Web (another shell)
cd web && npm install && npm run dev
```

Open http://localhost:3000 → `/setup` (first admin) → invite teammates → connect tools → chat.

Or: `docker compose up --build`

You need a reachable HydraDB (`HYDRA_HTTP` / `HYDRA_BOLT` / `HYDRA_TOKEN`) and an LLM configured in Settings after setup.

## First-run checklist

1. **Setup** — create the first workspace at `/setup` (company name, you, password). You land in Chat; the rest is skippable (`/onboarding` or Settings).
2. **Models** — Settings → Models (LLM base URL + key), or the onboarding Models step.
3. **Composio** — Integrations shows a Composio API key field for admins. Create a key at [dashboard.composio.dev](https://dashboard.composio.dev) and paste it, or set `COMPOSIO_API_KEY` in `.env`. joel does not ship a shared key.
4. **Sources** — Integrations: **Indexed** (sync into memory) vs **Live** (now-questions; GitHub/Linear). Connect one at a time.
5. **Slack bot** — Settings → Slack bot. Self-host: create an app from [`/slack-app-manifest.yaml`](./web/public/slack-app-manifest.yaml), paste signing secret + bot token. Hosted (`meetjoel.xyz`): Add to Slack. Then `/invite @joel` in channels. Ingest (which channels to index) is separate, on Integrations.
6. **People** — Settings → Members. Comma-separate emails. Copy links, or configure Email to send them.
7. **MCP** — Settings → API keys. Paste the URL snippet (`https://<this-origin>/mcp`). Cursor/Claude will ask you to sign in. Optional: mint a `joel_sk_…` key for clients that cannot do OAuth. One tool: `ask`.
8. **Voice** — Settings → General. Optional about text and how joel talks.
9. **HTTPS** — set `JOEL_HTTPS=1` and `JOEL_WEB_ORIGIN=https://your.domain` in production.

## Important env

| Variable | Purpose |
|---|---|
| `JOEL_DATA` | SQLite + index directory |
| `JOEL_SECRET` | Encrypts connector credentials |
| `JOEL_WEB_ORIGIN` | Public web origin (CORS, invite links fallback). `meetjoel.xyz` → cloud |
| `JOEL_DEPLOYMENT` | Optional `cloud` or `selfhost` override |
| `JOEL_HTTPS` | `1` → session cookie `Secure` |
| `SLACK_CLIENT_ID` / `SLACK_CLIENT_SECRET` / `SLACK_SIGNING_SECRET` | Hosted Slack app. Empty on self-host |
| `HYDRA_HTTP` / `HYDRA_BOLT` / `HYDRA_TOKEN` | Graph database endpoint and auth |
| `HYDRA_NAMESPACE` / `HYDRA_DATABASE` | Root graph scope. Must match HydraDB's own `GRAPH_NAMESPACE` / `GRAPH_DATABASE`. Each workspace gets its own scope underneath these — joel derives it, so never set a per-workspace value here |
| `COMPOSIO_API_KEY` | Optional env fallback; UI can store a key too |

Workspace settings (LLM, mail, Slack bot, voice, about, sync) are admin-only in the API.
Self-host Slack is signing secret + bot token; hosted Slack is Add to Slack (bot token stored per workspace).
User settings: profile, password, personal API keys, personal Gmail/Slack connectors.
