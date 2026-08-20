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

1. **Setup** — create the first workspace at `/setup` (company name, you, password). You land in Chat; models and tools are skippable.
2. **Invite** — Settings → Members. Comma-separate emails. Copy links, or configure Email to send them.
3. **Email (optional)** — Settings → Email: SMTP or Resend. Set App URL / `JOEL_WEB_ORIGIN` so invite links are correct.
4. **Models & Composio** — Settings → Models (LLM key) and Integrations (Composio) — admin only.
5. **HTTPS** — set `JOEL_HTTPS=1` and `JOEL_WEB_ORIGIN=https://your.domain` in production.

## Important env

| Variable | Purpose |
|---|---|
| `JOEL_DATA` | SQLite + index directory |
| `JOEL_SECRET` | Encrypts connector credentials |
| `JOEL_WEB_ORIGIN` | Public web origin (CORS, invite links fallback) |
| `JOEL_HTTPS` | `1` → session cookie `Secure` |
| `HYDRA_*` | Graph database |
| `COMPOSIO_API_KEY` | Optional env fallback; UI can store a key too |

Workspace settings (LLM, mail, Slack bot signing secret, sync) are admin-only in the API.
User settings: profile, password, personal API keys, personal Gmail/Slack connectors.
