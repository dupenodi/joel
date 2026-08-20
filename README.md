# joel

A self-hostable company brain built on HydraDB.

Members are invited; there is no open signup into someone else's workspace.
One person can belong to many workspaces on the same install.

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

## First-run checklist

1. **Setup** — create the first workspace at `/setup` (company name, you, password). You land in Chat; the rest is skippable (`/onboarding` or Settings).
2. **Models** — Settings → Models (LLM base URL + key), or the onboarding Models step.
3. **Composio** — Integrations shows a Composio API key field for admins. Create a key at [dashboard.composio.dev](https://dashboard.composio.dev) and paste it, or set `COMPOSIO_API_KEY` in `.env`. joel does not ship a shared key.
4. **Sources** — Integrations: **Indexed** (sync into memory) vs **Live** (now-questions; GitHub/Linear). Connect one at a time.
5. **Slack bot** — Settings → Slack bot. Create an app from [`/slack-app-manifest.yaml`](./web/public/slack-app-manifest.yaml), paste signing secret + bot token, then `/invite @joel` in channels. Ingest (which channels to index) is separate, on Integrations.
6. **People** — Settings → Members. Comma-separate emails. Copy links, or configure Email to send them.
7. **MCP** — Settings → API keys. Mint a key and copy the Cursor/Claude snippet (`https://<this-origin>/mcp/` + `joel_sk_…`). One tool: `ask`.
8. **Voice** — Settings → General. Optional about text and how joel talks.
9. **HTTPS** — set `JOEL_HTTPS=1` and `JOEL_WEB_ORIGIN=https://your.domain` in production.

## Important env

| Variable | Purpose |
|---|---|
| `JOEL_DATA` | SQLite + index directory |
| `JOEL_SECRET` | Encrypts connector credentials |
| `JOEL_WEB_ORIGIN` | Public web origin (CORS, invite links fallback) |
| `JOEL_HTTPS` | `1` → session cookie `Secure` |
| `HYDRA_*` | Graph database |
| `COMPOSIO_API_KEY` | Optional env fallback; UI can store a key too |

Workspace settings (LLM, mail, Slack bot signing secret + bot token, voice, about, sync) are admin-only in the API.
User settings: profile, password, personal API keys, personal Gmail/Slack connectors.
