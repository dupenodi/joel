# joel

A self-hostable company brain built on HydraDB.

## Quick start (UI + basic API)

```bash
# API
cd api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
JOEL_DATA=../data .venv/bin/uvicorn joel.app:app --reload --port 8000

# Web (another shell)
cd web && npm install && npm run dev
```

Open http://localhost:3000 → onboarding → connect a tool → chat.

Empty corpus is fine: chat streams an honest **Not in the company's memory.** answer with lane + tool-call traces.

Or: `docker compose up --build`
