# Setup action items

Setup / onboarding / settings only. Not the agent, not the memory pipeline, not Hydra (keep Hydra; don’t change it in this pass).

Self-host: this install’s URL, the operator’s keys, their Slack. SuperMemory is a reference for the *problem*, not a UI to copy.

Decisions below match the 2026-08-21 pass. **This pass is implemented.** Struck work is still out of scope.

---

## 1. Slack bot is a real bot — done

**Problem:** Mentions only work if someone already built a Slack app and we have a signing secret. We still can’t post or DM without a bot token.

**Shipped:**
- Manifest at [`web/public/slack-app-manifest.yaml`](../web/public/slack-app-manifest.yaml) (also [`docs/slack-app-manifest.yaml`](./slack-app-manifest.yaml)). Operator creates *their* app from it.
- Settings → Slack bot takes signing secret **and** bot token. Events URL is this origin (`/api/slack/events`).
- Mentions resolve the Slack user via `users.info` (bot token) and post with `chat.postMessage`. No Slack *ingest* connection required.
- Channels: they `/invite @joel` in Slack. We don’t create channels or post a launch message.
- Slack ingest (which channels to index) stays on Integrations.

Reply path stays @mention. Unprompted replies later.

---

## 2. How people join — `/join` + Connect me from Slack — done

**Shipped:**
- `/join` invite link still works (name + password, or existing password).
- **Connect me:** if someone `@joel`s and their Slack profile email has a pending invite, they get an ephemeral Connect me card (no password form). Button hits `/api/slack/interactions` (HMAC). Unknown emails stay silent — no auto-create on mention.
- New Connect-me accounts get a random password hash; Slack answers work immediately. Web passwordless login is still later.

Manifest interactivity URL: `https://YOUR-JOEL-ORIGIN/api/slack/interactions` (re-install or update the Slack app if you created it before this).

Do **not** auto-create accounts on first Slack mention without an invite.

---

## 3. Onboarding — done

**Shipped:** `/setup` unchanged (empty install needs an owner password). `/onboarding/llm` and `/onboarding/tools` redirect to **models** and **sources**. First-run is one skippable checklist; every step writes the same APIs Settings uses. Skip = Chat.

Order:

1. **Workspace** — website URL → Research (same-origin crawl, no LLM) or hand-written about
2. **Models** — LLM base URL + key
3. **Connect broker** — Composio key
4. **Sources** — Integrations grid (Indexed vs Live)
5. **Slack** — manifest + secrets
6. **People** — invite emails
7. **MCP** — paste the URL snippet; Cursor signs in. Optional key.
8. **Voice** — how it talks

Chat stays usable with holes. Empty Chat has “Finish setup”. `checklist.ready` is not a gate. Members who hit `/onboarding` go to Chat. Settings nav stays the long-term home.

---

## 4. Index vs live — done (grouping; ingest kept)

**Shipped:** Integrations has two groups — **Indexed** (Notion, Drive, Slack, Gmail, …) and **Live** (GitHub, Linear). Live tiles still ingest in v1 (lookback/sync as before) until live-only is wired on purpose. Copy on the tile modal says so. No write actions.

---

## 5. Composio key — done

Admin form on Integrations is always visible (not hidden after save). Copy: create a key at Composio, paste it here or set `COMPOSIO_API_KEY` in `.env`. No joel-shared key.

---

## 6. MCP for Cursor / Claude — done (OAuth, 2026-08-21)

Cursor/Claude register against **this origin** (joel is the authorization server). Paste the URL; they open `/oauth/consent`. Allow binds an access token to the signed-in Actor — same visibility as Chat. API keys (`joel_sk_…`) stay for clients that cannot do OAuth. One tool `ask`. Next rewrites `/.well-known/oauth-*`, `/authorize`, `/token`, `/register`. Hosted and self-host both do this (unlike Slack).

---

## 7. Scheduled posts — not now

The bot **reads and answers**. No cron digests. Write tools first, later.

---

## 8. How it talks — done

Workspace field (free text + Direct / Warm / Formal presets) on Settings → General and onboarding. Stored as `voice` + `workspace_about` in settings, injected into the answer prompt. **About** can be seeded by Research (same-origin website crawl, no LLM); sources JSON in `workspace_profile_sources`.

---

## 9. Leasing — skipped

Don’t build this now.

---

## Out of scope (still)

- Agent quality, distillation, ontology, graph UI.
- Hydra: keep using it; no Hydra work here.
- Unprompted Slack replies, sandboxes, calendar, long research.
- Write tools and schedulers.
- Billing. A joel-hosted Composio.
- Replacing `/setup` password for the first owner.
- Join-on-Slack-mention (item 2).
- Leasing (item 9).
- Scheduled posts.

---

## This pass, in order — done

1. Slack bot token + manifest (1)
2. Onboarding = full settings checklist (3), including voice (8) and MCP snippet (6)
3. Composio copy so the key field is obvious (5)
4. Integrations: Indexed vs Live grouping (4), still read-only live

Stop. Agent / memory pipeline / Hydra / writes later.

---

## 10. Cloud vs self-host Slack install — done (2026-08-21)

**Shipped:** `api/joel/deployment.py` (`cloud` if origin is meetjoel.xyz, or `JOEL_DEPLOYMENT` override). Slack:

- **Self-host:** manifest + paste (unchanged).
- **Cloud with `SLACK_*` env:** Add to Slack. Events verified with the env signing secret, routed by `orgs.slack_team_id`.
- **Cloud without those env vars:** Slack UI says unavailable — no DIY manifest.

Not in this pass: channel bootstrap, unprompted replies, billing, subdomains.
