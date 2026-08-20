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

## 2. How people join — keep it simple — unchanged

**Decision:** `/join` is the only way in. Invite link, set a password (or existing password). Done.

Do **not** auto-create or auto-accept accounts on first Slack mention. If @joel doesn’t match a user, stay silent.

---

## 3. Onboarding — done

**Shipped:** `/setup` unchanged (empty install needs an owner password). `/onboarding/llm` and `/onboarding/tools` redirect to **models** and **sources**. First-run is one skippable checklist; every step writes the same APIs Settings uses. Skip = Chat.

Order:

1. **Workspace** — optional about text
2. **Models** — LLM base URL + key
3. **Connect broker** — Composio key
4. **Sources** — Integrations grid (Indexed vs Live)
5. **Slack** — manifest + secrets
6. **People** — invite emails
7. **MCP** — mint a key, copy snippet
8. **Voice** — how it talks

Chat stays usable with holes. Empty Chat has “Finish setup”. `checklist.ready` is not a gate. Members who hit `/onboarding` go to Chat. Settings nav stays the long-term home.

---

## 4. Index vs live — done (grouping; ingest kept)

**Shipped:** Integrations has two groups — **Indexed** (Notion, Drive, Slack, Gmail, …) and **Live** (GitHub, Linear). Live tiles still ingest in v1 (lookback/sync as before) until live-only is wired on purpose. Copy on the tile modal says so. No write actions.

---

## 5. Composio key — done

Admin form on Integrations is always visible (not hidden after save). Copy: create a key at Composio, paste it here or set `COMPOSIO_API_KEY` in `.env`. No joel-shared key.

---

## 6. MCP for Cursor / Claude — done

API keys page: copy-paste snippet, `https://<this-origin>/mcp/` + the key they just created. Next rewrites `/mcp` to the API. One tool `ask`. No hosted MCP hostname.

---

## 7. Scheduled posts — not now

The bot **reads and answers**. No cron digests. Write tools first, later.

---

## 8. How it talks — done

Workspace field (free text + Direct / Warm / Formal presets) on Settings → General and onboarding. Stored as `voice` + `workspace_about` in settings, injected into the answer prompt.

---

## 9. Leasing — skipped

Don’t build this now.

---

## Out of scope (still)

- Agent quality, distillation, ontology, graph UI.
- Hydra: keep using it; no Hydra work here.
- Unprompted Slack replies, sandboxes, calendar, long research.
- Write tools and schedulers.
- Billing. A joel-hosted Slack app / MCP / Composio.
- Replacing `/setup` password for the first owner.
- Join-on-Slack-mention (item 2).
- Leasing (item 9).

---

## This pass, in order — done

1. Slack bot token + manifest (1)
2. Onboarding = full settings checklist (3), including voice (8) and MCP snippet (6)
3. Composio copy so the key field is obvious (5)
4. Integrations: Indexed vs Live grouping (4), still read-only live

Stop. Agent / memory pipeline / Hydra / writes later.
