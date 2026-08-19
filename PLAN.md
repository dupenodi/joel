# joel — Build Spec

**What:** a self-hostable company brain. Connect your tools, joel distills them into a knowledge graph on HydraDB, and you chat with your org's memory — with citations, a decision-reversal ledger, and honest "not in the data" answers.

---

## 0. The goal

**In my words:** the codebase is what matters. Not a demo, not a benchmark score. joel has to be a **real tool that anyone can connect their tools to and just use forever** — it keeps itself current without being asked, it survives a reboot and an expired token, and it gets more useful the longer it runs. If something only exists to look good in a three-minute video, it is not a feature.

What that rules *in*, that a demo build would skip:

- **It stays current on its own.** A background scheduler syncs every connector on an interval. "Sync now" is a convenience, not the mechanism.
- **It gets cheaper over time, not more expensive.** Unchanged documents are detected and skipped before any LLM touches them.
- **It survives.** Tokens refresh, rate limits back off, a killed sync resumes from its cursor, the schema migrates, every index rebuilds from canonical JSONL.
- **It tells you what it's doing.** Every sync is a job with a status, a duration, and a readable error.
- **It never silently drifts.** One write path, three stores, one consistency check.

Deliberately deferred until the product is complete: benchmark corpora, eval harnesses, ablation tables, demo scripts, launch posts. If numbers are wanted later they get bolted on then (§16.3).

### 0.1 How to use this document

§16 is the phase list — build in that order. **§22 at the end holds every checkpoint**, as granular checklists: one box per assertion, small enough to be plainly true or false. Do not start a phase with a red box behind you. Automate what you can in `scripts/check_*.py`; boxes marked 👁 need your eyes. Commit per checkpoint.

Each risky step carries a guardrail table — **the ❌ column is a mistake an implementing agent will plausibly make, and it usually fails silently** (wrong-case property values match nothing without erroring, a listening port isn't a working node, a fabricated citation looks like a real one). Treat ❌ rows as assertions to encode in checkpoints.

**Propose the plan, then wait for approval, before writing code.** Product rules live in `CONTEXT.md`; hard-to-reverse choices in `docs/adr/`.

### 0.2 Product decisions — settled, do not re-litigate

| Question | Decision |
|---|---|
| Who uses it | **One self-hosted workspace, many members.** First admin runs `/setup`; everyone else is invited. Session cookie, roles `admin` / `member`. |
| How memory is scoped | **Three rooms, not one knowledge base** — same graph as [Supermemory's permissions](https://supermemory.ai/docs/company-brain/permissions): employee / private channel / public. A doc is written to exactly one room. An ask reads as wide as the room it is asked from (§1.4). |
| How data stays fresh | **Background scheduler**, per-connector interval, plus a manual Sync now. |
| How much history | **Bounded first pass** so it's usable in minutes, then a low-priority job walks backwards through the whole archive. |
| Can the agent act | **Read-only for now.** Live lookup later; writes to tools are out until personal connections exist. |
| Live-fetched data | **Becomes memory** — but only through the same filter every other document passes. Nothing skips distillation and the noise filter. |
| Upstream deletes | **Ignored.** Memory is append-only. The one removal path is an explicit forget. |
| Connectors that ship | **Slack · GitHub · Gmail · Linear · Jira · Notion · Confluence · Google Drive · HubSpot · Fireflies.** Connect through Composio only. Custom OAuth is cut. |
| Connector scope | **Not built.** Today every connection is workspace-level. Target: org-shared (data) vs personal (tools), with reads preferring personal then falling back to org — [Supermemory](https://supermemory.ai/docs/company-brain/permissions). |
| What “shipped” means today | Connect + lookback ingest + login + visibility stamps + web chat that filters by ask context. Not CP-C green: no poll/backfill cursors, no channel-membership graph, no Slack/MCP surfaces, no personal vs org connectors. |

Consequences: append-only means **`validity='superseded'` is how things stop being true**, never deletion. Visibility is a stamp at ingest, never inferred at query time. The client does not choose the readable set — the server builds `AskContext` from the signed-in actor and the surface. Read-only means no confirmation UI and no audit trail of writes yet.

### 0.3 Current state — 2026-08-19

Honest snapshot of the repo, not the original v1 brief. Distillation/ontology/agent remain the later core track; this is the company-brain *skeleton* that those phases now sit on.

| Piece | State |
|---|---|
| Workspace | One `orgs` row (`id=1`). Created at `/setup` with domain/name/logo. `PATCH /api/workspace`. |
| Identity | `users`, `memberships`, `sessions`, `invites`. `joel/identity.py`. `scripts/check_identity.py` green. |
| Auth UX | `/setup`, `/login`, `/join?token=`. Product pages behind `AuthGate`. Cookie session; almost all `/api/*` require it. |
| Visibility stamp | `docs.visibility`: `org` · `channel:slack:C…` · `user:gmail:…`. Derived at ingest (`joel/visibility.py`). Migration `004`. Slack needs a re-sync to stamp private channels (old extra had no `channel_kind`). Gmail restamped on migrate. |
| Ask context | `POST /api/ask` uses the signed-in actor. Web = desk: `org` + `user:gmail:{actor.email}` + every private Slack channel the actor is a member of (§1.4, via `joel/membership.py`, matched by email). No client-supplied room. |
| Ingest | Ten connectors, lookback re-fetch, content_hash triage, background scheduler (concurrency-capped, errored connectors retry on a backoff ladder), zombie-job reclaim on boot. |
| Retrieval | All six lanes: VECTOR / VEC-ARTIFACTS / FTS / PHRASE / GRAPH / WHO_KNOWS, RRF, rerank, abstention. Lanes honour `allowed_stamps(ask)`. |
| Distill / ontology / agent | Distill, ontology (extract → resolve → reconcile → graph edges, §9), follow-up rewriting, and live lookup (§13, GitHub PR/issue + Slack channel only so far) all exist and are wired into `/api/ask`. |
| Slack bot, MCP, leasing, API keys | **Not built.** Same permissions graph will apply when they exist. |

**Channel membership is done** (2026-08-19) — a desk/DM now reads the private rooms the actor is actually in, matched by email. Remaining skeleton checkpoints, in order: **real personal connectors** (needs the `connections.provider` UNIQUE constraint removed, not just the `owned_by`/`kind` columns already added) → **Slack surface** then **MCP**, both constructing `AskContext` server-side.

---

## 1. Product definition

### 1.1 What joel is (and deliberately isn't)

joel is a **self-hosted workspace**: one company install, invited members, a shared employee that answers from memory scoped to who is asking and from where.

| Page | Purpose |
|---|---|
| `/setup` | first admin: email, password, company domain → workspace + admin account |
| `/login` · `/join` | sign in; accept an invite token |
| `/` (chat) | conversations, status-badged answers, citations, reasoning path |
| `/integrations` | connect/disconnect tools, live status + next run, **Sync now**, job history |
| `/settings` | workspace members + invites, LLM keys, spend, wipe |
| `/onboarding` | LLM key + first tool, after the workspace already exists |

**Not built yet (skeleton holes, not cut forever):** Slack bot / MCP surfaces · personal vs org-shared connectors · channel membership · access leasing · billing · agent write-actions · digests. The graph page is a stub; the reasoning path in chat is the graph surface.

Note what moved *in*: login, rooms, and the scheduler. A company brain that is one anonymous bucket, or that only updates when you click a button, is a demo.

### 1.2 "Ready to use" — defined precisely

Per-connector state machine — note that `ready` is a resting state, not a terminal one:

```
pending_auth → backfilling (n docs) → distilling (k threads) → linking (entities + ontology) → ready
                                                                                                 ⇅
                                                                                              syncing
ready | syncing ──► needs_reauth        (refresh failed — scheduler stops, card shows Reconnect)
ready | syncing ──► error(msg)          (retryable — scheduler backs off, card shows the reason)
```

Every interval the connector goes `ready → syncing → ready`. The card shows the state, the counts, the last run, and the next run.

**Chat opens when the FIRST connector reaches `ready`.** That is the only gate. After that chat is always available, with a banner while any connector is mid-sync ("still ingesting — answers may be incomplete") and a distinct banner when one needs re-auth.

Onboarding shows the live checklist for the **first connector only** (`fetched ✓ · distilled ✓ · people resolved ✓ · graph linked ✓ · indexes consistent ✓`) and forwards to `/chat` when it completes. There is no whole-org "READY" state — with a scheduler running forever, some connector is always mid-sync, so a global ready flag would be permanently false.

**Index consistency** is a health check, not a gate: SQLite doc count == npz row count == graph `:Doc` count, surfaced on `/api/health` and in the profile page. Drift is a bug to fix, not a state to wait out.

### 1.3 Design lineage (context for the agent, one paragraph each)

**Sentra's three layers** — factual memory (what/where/who) = doc rows + graph doc-nodes; interaction memory (why: decisions, commitments, objections) = the ontology edges in HydraDB; action memory is out of v1 scope.

**Cerebras' knowledge-base pipeline** — the ingestion/retrieval philosophy this build copies: *distill threads into one structured artifact before embedding* (chatter informs the artifact, then vanishes); retrieval = parallel lists (vector, full-text, artifacts, graph) fused with **RRF k=60** then LLM-reranked; four signals each catch what the others miss (full-text = exact tokens, embedding = paraphrase, IDF = rare beats filler, age decay = newer wins ties).

**Build vs. free:** local HydraDB is an OpenCypher graph database — Bolt + HTTP, snapshot-consistent, `algo.MSpaths` path procedures. It does NOT ship embeddings, BM25, or ingestion. So: **HydraDB owns the graph** (ontology, reversal ledger, WHO_KNOWS, multi-hop), SQLite FTS5 owns exact/BM25, a local sentence-transformers model owns vectors. Everything is local; there are no usage limits anywhere and no per-seat cost to running it for years.

**Supermemory's permissions graph** — [what memory is, who sees it, how tools are scoped](https://supermemory.ai/docs/company-brain/permissions). Joel copies the three rooms and the read-widens-as-the-room-gets-more-private rule. It does not copy hosting, billing, or silent grants: every install is self-hosted, and leasing (borrowing a teammate's connection for one request) is deferred until personal connectors exist.

### 1.4 Permissions graph

Company brain is not "a shared brain" plus "a private brain." It is one corpus whose **write is narrow** and whose **read depends on where the question is asked**. Joel's names: **Workspace**, **Actor**, **Room**, **Visibility**, **Ask context** (`CONTEXT.md`).

**Three memories — a message writes to exactly one:**

| Room | Stamp | Written from | Who can ever see it |
|---|---|---|---|
| Public / org | `org` | Public Slack, Drive, Notion, GitHub, Linear, … | Anyone asking from any room |
| Private channel | `channel:slack:C…` | A private Slack channel | Only that channel, or a desk/DM whose actor is in it |
| Employee | `user:gmail:ada@…` (later `user:slack:D…`) | Gmail, DMs, private notes | Only that person's desk/DM |

**What a conversation can read** (writing is narrow; reading widens the more private the seat):

| Asking from | Can read |
|---|---|
| Public channel / public MCP | Public / `org` only |
| Private channel | That channel + `org` |
| Desk (web) or DM with the bot | Employee memory the actor owns + `org` + every private channel they belong to |

A public room is the whole org, so it only draws on what the whole org may know. A DM/web desk is the widest seat because it is the most private — it answers with everything *that actor* could see, and cites which room the answer came from. If you are not in a private channel, its memory does not exist for you, not even by inference.

**Surfaces construct AskContext server-side.** Web chat is a desk (`AskContext.web`). Slack and MCP, when they exist, will build the same object from the event (channel vs DM), never from a client-chosen room field — a POST body that named `channel:slack:Cpriv` would be an ACL bypass (`docs/adr/0001-visibility-is-one-room.md`).

**Today vs the graph:** stamps and the public/channel/desk read table are implemented. Channel *membership* is not, so web cannot yet include `channel:slack:…` even for people who are in that Slack room. Gmail is visible on web only when the mailbox matches the actor's workspace email. Tool access "personal first, then org-shared" and one-request leasing are **not built**.

---

## 2. Architecture

```
   Connectors: Slack · GitHub · Gmail · Linear · Jira · Notion · Confluence · Drive · HubSpot · Fireflies
        (Composio hosted OAuth — joel never holds provider tokens)
        ▲ scheduler tick (§11) — in-process loop; lookback re-fetch (no cursors yet)
        │  raw docs via fetch_*_docs — tools.proxy for 7 providers,
        │  tools.execute for Jira/Confluence/Fireflies (§16.2 deviation)
        ▼
   ┌──────────────────────────────────────────┐
   │ Change detection: content_hash — skip    │  §6.1
   │ unchanged docs BEFORE any LLM runs       │
   └──────────────────┬───────────────────────┘
                      ▼
   ┌──────────────────────────────────────────┐
   │ Adapters: raw → CanonicalDoc (+threads)  │  §6
   │ Visibility stamp: org / channel / user   │  §1.4
   └──────────────────┬───────────────────────┘
                      ▼
   ┌──────────────────────────────────────────┐
   │ Distillation: bursts → filter → LLM →    │  §7
   │ ThreadArtifact (inherits the thread's    │
   │ visibility)                              │
   └──────────────────┬───────────────────────┘
                      ▼
   ┌──────────────────────────────────────────┐
   │ Store (one API, three destinations)      │  §8
   │  SQLite bodies+FTS5 · vectors.npz ·      │
   │  HydraDB :Doc nodes + edges              │
   └──────────────────┬───────────────────────┘
                      ▼
   ┌──────────────────────────────────────────┐
   │ Ontology: extract → resolve entities →   │  §9
   │ reconcile INCREMENTALLY → Cypher edges   │
   └──────────────────┬───────────────────────┘
                      ▼
 QUESTION + AskContext (who + room)                                §1.4
          → working memory: follow-ups                             §13.1
          → planner → lanes, each filtered by allowed_stamps       §10
          → RRF(k=60) → rerank → answer | partial | conflicted | absent
          → read-only live lookup when needed                      §13.2
                      ▼
   joel-api (FastAPI: auth, workspace, connectors, scheduler, jobs,
             /ask SSE, settings)  →  joel-web (setup/login + product)   §12
```

### 2.1 Data placement — decide once

| Store | Owns | Never holds |
|---|---|---|
| **canonical JSONL** (`data/canonical/*.jsonl`) | every doc ever ingested, append-only — **the source of truth** | derived state |
| **HydraDB** (`/store` volume) | `:Doc` nodes (metadata only), `:Entity`/`:Alias`, every ontology + structural edge | document bodies (graph stays traversal-fast) |
| **SQLite** (`data/index/joel.db`) | bodies, `visibility`, FTS5, plus `orgs/users/memberships/sessions/invites/connections/jobs/conversations/messages/settings` | graph structure |
| **vectors** (`data/index/joel.npz`) | doc_id → normalized embedding | anything else |

**One universe.** There is no benchmark dataset and no `JOEL_DATASET` switch: a single install, a single store dir, a single graph. (The old two-universe design contradicted the compose file, which only ever mounted one store volume.)

**The three indexes are disposable; the canonical JSONL is not.** `scripts/rebuild_index.py` regenerates SQLite, npz **and the graph** from canonical. That single fact is the backup story, the schema-migration story, and the "I want to change the embedding model" story.

| ✅ DO | ❌ DON'T |
|---|---|
| One `store.upsert_docs(rows)` fanning out to all three (SQLite → vectors → graph), per-destination retry ledgers | Let phases write to stores directly — three-way drift is unfindable |
| doc_id is the join key, identical across all three | Let SQLite rowids or graph-internal ids leak into app code |
| Append to canonical JSONL first, then index | Have an index row that no canonical line explains — it will not survive a rebuild |

---

## 3. Phase 0 — Environment + local HydraDB

### 3.1 HydraDB local setup (do FIRST — first compile is 10–25 min)

Prereqs: Rust 1.91+, C/C++ toolchain, `libcypher-parser`, SuiteSparse GraphBLAS.

```bash
# Ubuntu / WSL
sudo apt-get update && sudo apt-get install -y \
  build-essential clang libclang-dev cmake pkg-config \
  libcypher-parser-dev libgraphblas-dev curl git python3 python3-venv
# macOS
xcode-select --install
brew install just cmake pkg-config llvm suite-sparse
brew install cleishm/neo4j/libcypher-parser   # tap name required; not in homebrew-core
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh   # NOT brew's rustup

git clone https://github.com/hydra-db/hydradb.git && cd hydradb
just native-check && just smoke
```

Run a local single-node dev server:

```bash
mkdir -p .hydradb/store-bench .hydradb/cache
printf '%s\n' 'local-development-token-32-bytes' > .hydradb/auth-token

export CLOUD_PROVIDER=local
export LOCAL_PATH="$PWD/.hydradb/store-bench"     # store-main for the real-org universe
export GRAPH_NAMESPACE=default GRAPH_ID=default GRAPH_CELL_ID=cell-0 GRAPH_CELLS=cell-0
export GRAPH_NODE_ID=node-0
export GRAPH_BOLT_NODE_ADDRESSES=node-0=127.0.0.1:7687
export GRAPH_ADVERTISED_BOLT_ADDR=127.0.0.1:7687
export GRAPH_DATA_CACHE_DIR="$PWD/.hydradb/cache"
export GRAPH_AUTH_TOKEN_FILE="$PWD/.hydradb/auth-token"
export GRAPH_ALLOW_PLAINTEXT=true
export RUST_MIN_STACK=33554432   # else: serves /readyz, ABORTS on first query
if command -v brew >/dev/null; then   # macOS + direct cargo only
  export BINDGEN_EXTRA_CLANG_ARGS="-I$(brew --prefix)/include"
  export LIBRARY_PATH="$(brew --prefix)/lib"
fi
cargo run --locked --features server-runtime --bin graph-node
```

Node holds the foreground — **that's it working, not hanging.** Bolt `127.0.0.1:7687` · HTTP `127.0.0.1:8443` · admin `127.0.0.1:9090` (`/readyz`, metrics).

Prove it with a **round-tripped write** (a listening port proves nothing):

```bash
TOKEN='local-development-token-32-bytes'
curl -sS http://127.0.0.1:8443/v1/graphs/default/query \
  -H "Authorization: Bearer $TOKEN" -H 'X-Graph-Namespace: default' \
  -H 'Content-Type: application/json' \
  --data '{"cell_id":"cell-0","query":"CREATE (a {id: 1})-[:FOLLOWS]->(b {id: 2})"}'
curl -sS http://127.0.0.1:8443/v1/graphs/default/query \
  -H "Authorization: Bearer $TOKEN" -H 'X-Graph-Namespace: default' \
  -H 'Content-Type: application/json' \
  --data '{"cell_id":"cell-0","query":"MATCH (a {id: 1})-[:FOLLOWS]->(b) RETURN b.id AS id"}'
# → {"type":"vertex_id","value":2}
```

Troubleshooting (verbatim from the repo — pin it):

| Symptom | Fix |
|---|---|
| `No available formula "libcypher-parser"` | `brew install cleishm/neo4j/libcypher-parser` |
| `command not found: rustup-init` | official rustup installer, not brew |
| `invalid environment variable CLOUD_PROVIDER value 'null'` | it's unset; `local` also needs an **existing** `LOCAL_PATH` dir |
| `'cypher-parser.h' file not found` | macOS direct-cargo: export `BINDGEN_EXTRA_CLANG_ARGS` |
| `/readyz` ok then abort `has overflowed its stack` | `RUST_MIN_STACK=33554432` |
| `curl: (7) ... :9090` | node not running; it holds the foreground |

Consistency: `causal` (default) vs `strong` (refresh before pinning the snapshot). **Every checkpoint read-after-write uses `strong`** (`"consistency":"strong"` in the HTTP body) or you'll chase phantom missing rows.

License: HydraDB is AGPL-3.0; joel talks to it over the network, so joel stays MIT — attribute HydraDB in the README.

| ✅ DO | ❌ DON'T |
|---|---|
| Start this build first thing today; overlap the compile with corpus download | Save it for ingest day |
| Read the repo's `AGENTS.md` + `cypher-compat.md` before writing store code | Assume full Neo4j Cypher — **verify `MERGE`, `SET`, relationship-properties**; §4.4 has fallbacks |
| Two shells: node in one, work in the other | Background with `&` and lose the logs |
| Dev token exactly the 32-byte string shown | Invent a short token, fight auth |

### 3.2 Repo layout + env

```
joel/
├── README.md · LICENSE(MIT) · docker-compose.yml · .env.example · Makefile
├── data/  raw/ canonical/ graphs/ entities/ index/ state/     # gitignored
├── api/                      # FastAPI service (Dockerfile)
│   └── joel/
│       ├── config.py hydra.py store.py store_sql.py live_index.py models.py
│       ├── migrations/ 001_init.sql 002_store_layer.sql …   # §14.3, done
│       ├── pipeline.py # ingest -> distill -> store wiring, called once per sync from _run_ingest
│       ├── adapters/   base.py  manifests.py  code_chunk.py
│       │               # one adapt() + one SourceManifest per source. No per-provider adapter modules.
│       ├── distill/    bursts.py artifact.py df_index.py state.py   # §7, done and wired (pipeline.py)
│       ├── llm.py      # generic JSON-mode LLM caller + repair retry, shared by every prompted stage
│       ├── ontology/   extract.py resolve.py reconcile.py    # stubs
│       ├── retrieve/   planner.py lanes.py fuse.py rerank.py synthesize.py  # stubs
│       ├── connectors/ gate.py composio_conn.py oauth.py http.py
│       │               slack.py github.py gmail.py catalog.py
│       │               jira.py confluence.py fireflies.py   # tool-execute, not proxy — §6 deviation
│       ├── syncer.py   # background ingest scheduler (§11 interval ticks)
│       ├── agent/      # not created — live lookup is §13.2, chat still stubs it
│       ├── routes.py health.py
│       └── prompts/    *.md (7 — §18)
├── web/                      # 5 app pages + the landing page
└── scripts/ check_{0..11}_*.py rebuild_index.py
```

```bash
# .env.example
HYDRA_HTTP=http://hydradb:8443           # 127.0.0.1 outside compose
HYDRA_BOLT=neo4j://hydradb:7687
HYDRA_TOKEN=local-development-token-32-bytes
HYDRA_NAMESPACE=default
HYDRA_CELL=cell-0
EMBED_MODEL=BAAI/bge-small-en-v1.5       # local CPU, 384-dim, zero cost/limits
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=                             # the only key required to boot
LLM_MODEL_DISTILL=anthropic/claude-sonnet-4.5
LLM_MODEL_EXTRACT=anthropic/claude-sonnet-4.5
LLM_MODEL_ANSWER=anthropic/claude-sonnet-4.5
LLM_MODEL_RESOLVE=anthropic/claude-haiku-4.5
LLM_MODEL_RERANK=anthropic/claude-haiku-4.5
SYNC_ENABLED=true                        # master switch for the scheduler
SYNC_DEFAULT_INTERVAL_MIN=15             # per-connector override in settings
SYNC_MAX_CONCURRENT_JOBS=2               # across ALL connectors
DISTILL_MAX_CONCURRENCY=8                # LLM fan-out ceiling, global
COMPOSIO_API_KEY=                        # optional: hosted OAuth broker
JOEL_SECRET=                             # generated on first boot; encrypts oauth tokens
```

Every value above is also editable in `/settings` and stored in the `settings` table, which **overrides** the env var at runtime. Env is the bootstrap; the database is the truth. Changing a model in the UI must not require an edit-and-restart cycle.

### 3.3 `joel/hydra.py` — thin Cypher client

```python
import os, requests
from neo4j import GraphDatabase

class Hydra:
    def __init__(self):
        self.http = os.environ["HYDRA_HTTP"]; self.tok = os.environ["HYDRA_TOKEN"]
        self.ns = os.environ["HYDRA_NAMESPACE"]; self.cell = os.environ["HYDRA_CELL"]
        # Bolt auth scheme: verify against scripts/bolt_neo4j_driver_smoke.sh in the repo;
        # token-as-password is the working assumption.
        self.driver = GraphDatabase.driver(os.environ["HYDRA_BOLT"], auth=("hydradb", self.tok))

    def q(self, cypher: str, params: dict | None = None, strong: bool = False):
        body = {"cell_id": self.cell, "query": cypher}
        if params: body["params"] = params          # verify param syntax works over HTTP;
        if strong: body["consistency"] = "strong"   # else use Bolt for parameterized queries
        r = requests.post(f"{self.http}/v1/graphs/default/query",
            headers={"Authorization": f"Bearer {self.tok}",
                     "X-Graph-Namespace": self.ns, "Content-Type": "application/json"},
            json=body, timeout=120)
        r.raise_for_status(); return r.json()

    def bolt(self, cypher: str, **params):
        with self.driver.session() as s: return list(s.run(cypher, **params))
```

| ✅ DO | ❌ DON'T |
|---|---|
| Parameterized queries via Bolt for anything containing user/document text | String-interpolate bodies into Cypher — one apostrophe breaks ingest; also injection |
| Batch writes with `UNWIND $rows …` | One round-trip per node — 45K docs takes hours |
| `strong` reads in checkpoints | Chase causally-lagged "missing" rows |

---

## 4. Phase 1 — Graph data model

No schema API exists — **the model is conventions enforced in `store.py`.**

### 4.1 Nodes

| Label | Properties |
|---|---|
| `:Doc` | `id` (unique), `title`, `source_type`, `container`, `granularity` (`artifact\|burst\|document\|record\|code`), `artifact_class` (`decision\|commitment\|objection\|incident\|qa\|status_update\|reference\|document\|noise`), `validity` (`current\|superseded`), `resolved` (`true\|false\|na`), `ts` (ISO), `period` (`2026Q2`), `url` — **no body** |
| `:Entity` | `id` (`person_0041`), `name` (canonical), `etype` (`PERSON\|TEAM\|PROJECT\|CUSTOMER\|SERVICE\|POLICY\|METRIC\|INCIDENT`), `identifier` |
| `:Alias` | `name` (surface form, lowercased), `entity_id` |

### 4.2 Relationships

| Edge | From → To | Props | Purpose |
|---|---|---|---|
| `:MENTIONS` | Doc → Entity | — | doc↔entity index |
| `:AUTHORED` | Entity → Doc | — | actor queries |
| `:REPLY_TO` / `:COMMENT_ON` / `:LINKED_TO` | Doc → Doc | — | structure |
| `:DISTILLED_FROM` | Doc(artifact) → Doc(burst) | — | provenance |
| `:REVERSED` | Doc(winner) → Doc(loser) | `ts` | decision-reversal ledger |
| `:DECIDED :OWNS :COMMITTED_TO :OBJECTED_TO :RESOLVED :ASSIGNED_TO :DEPENDS_ON :BLOCKS :APPROVED :ESCALATED :AFFECTS :REPORTED` | Entity → Entity | `doc_id, ctx (≤200), ts` | the ontology — **the Best-Use-of-HydraDB exhibit** |

### 4.3 Write/read patterns

```cypher
UNWIND $rows AS r
CREATE (d:Doc {id:r.id, title:r.title, source_type:r.source_type, container:r.container,
               granularity:r.granularity, artifact_class:r.artifact_class,
               validity:r.validity, resolved:r.resolved, ts:r.ts, period:r.period, url:r.url})

MATCH (d:Doc {id:$id}) SET d.validity = 'superseded'                     // supersession flip

MATCH (a:Entity {id:$src}),(b:Entity {id:$dst})
CREATE (a)-[:DECIDED {doc_id:$doc, ctx:$ctx, ts:$ts}]->(b)               // ontology edge

MATCH (al:Alias) WHERE al.name IN $names                                 // WHO_KNOWS
MATCH (p:Entity {id:al.entity_id})-[r:RESOLVED|OWNS|DECIDED|ASSIGNED_TO]->(x:Entity)
RETURN p.name, type(r), x.name, r.doc_id

CALL algo.MSpaths({sourceLabel:'Entity', sourceProperty:'name',          // multi-hop
  sourceValues:$froms, targetValues:$tos, pairwise:true,
  relDirection:'both', maxLen:3, pathCount:5, resultLimit:100}) YIELD path RETURN path
```

### 4.4 Verify against the repo's `cypher-compat.md` (30 min on day 1)

| Assumption | Fallback if missing |
|---|---|
| `MERGE` | ids are deterministic → client-side create-if-absent: `written` table in SQLite, `CREATE` only new; "upsert" = `MATCH … SET` (§8.2) |
| `SET` | delete-and-recreate helper (re-create edges too) |
| **`DELETE` / `DETACH DELETE`** | **two features need it: de-kept bursts on re-sync, and the owner's explicit forget. If unsupported, the fallback is `SET d.deleted='true'` + every lane and traversal filters it out — decide this on day 1, because "filter everywhere" has to be threaded through all six lanes rather than bolted on later.** |
| relationship properties | reify: `(:Claim {predicate, doc_id, ctx, ts})` with `:FROM`/`:TO` |
| `IN` lists / `UNWIND` params | chunk client-side into OR-chains |

| ✅ DO | ❌ DON'T |
|---|---|
| Enforce id uniqueness in `store.py` | Assume the DB dedupes — double-ingest = duplicate nodes = double-counted retrieval votes |
| Lowercase/slug every filterable property at write; matching is exact | Write `Engineering`, match `engineering`, get zero rows and no error |
| Bound traversals (`[*..3]`, `resultLimit`) | Unbounded expansion on a hub entity — five years of Slack makes several |

---

## 5. Phase 2 — Canonical models — `joel/models.py`

```python
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime

class CanonicalDoc(BaseModel):
    doc_id: str                       # stable id, the cross-store join key
    source_type: str                  # slack|gmail|linear|jira|confluence|gdrive|github|hubspot|fireflies
    external_id: str                  # provider-native id of THIS item
    title: str
    body: str
    extra: dict[str, Any] = Field(default_factory=dict)
    author_raw: str | None = None     # RAW handle — resolution happens in §9
    participants_raw: list[str] = Field(default_factory=list)
    container: str | None = None      # channel/project/space/repo/mailbox/pipeline
    url: str | None = None
    timestamp: datetime | None = None # tz-aware or None, never a raw string
    thread_id: str | None = None
    parent_id: str | None = None
    linked_ids: list[str] = Field(default_factory=list)
    # lifecycle — how joel knows what changed without re-reading everything
    content_hash: str = ""            # sha256(title + "\n" + body). CHANGE DETECTION ONLY.
    ingested_via: str = "sync"        # sync | backfill | live
    first_seen: datetime | None = None
    last_seen: datetime | None = None  # last time a fetch returned this doc
    # filled by later phases
    actor_id: str | None = None
    artifact_class: str = "document"
    validity: str = "current"
    granularity: str = "document"     # artifact|burst|document|record|code
    resolved: str = "na"

class Burst(BaseModel):
    burst_id: str                     # f"{thread_id}_b{n}"
    thread_id: str
    author_raw: str
    text: str
    message_external_ids: list[str]
    start_ts: datetime
    end_ts: datetime
    has_reactions: bool = False
    role: str | None = None           # question|answer|context|resolution|noise (from distiller)
    kept: bool = False

class ThreadArtifact(BaseModel):
    artifact_id: str                  # f"art__{source_type}__{slug(thread_id)}"
    thread_id: str
    source_type: str
    container: str | None
    question: str
    summary: str
    resolution: str | None
    resolved: bool
    systems: list[str]
    code_refs: list[str]              # VERBATIM identifiers — exact-match fuel
    actors: list[dict]                # [{"name": raw, "role": "asker|resolver|participant"}]
    artifact_class: str
    supersedes: str | None
    confidence: float
    timestamp: datetime | None
    source_message_ids: list[str]

    def normalized_body(self) -> str:
        # question first (queries are question-shaped), verbatim refs last (BM25 fuel)
        p = [f"Q: {self.question}", f"Summary: {self.summary}"]
        if self.resolution: p.append(f"Resolution: {self.resolution}")
        if self.systems:    p.append("Systems: " + ", ".join(self.systems))
        if self.code_refs:  p.append("Refs: " + ", ".join(self.code_refs))
        return "\n".join(p)

def period_of(ts): return f"{ts.year}Q{(ts.month-1)//3+1}" if ts else "unknown"
```

**doc_id rules:** `{source_type}__{slug(external_id)}`, slug `[a-z0-9_.-]` · artifacts `art__{source_type}__{slug(thread_id)}` · GitHub **must include the repo**: `github__issue_{slug(owner/repo)}_N` / `github__pr_{slug(owner/repo)}_N` (issue vs PR prefixes are not enough — two repos both have a `#1`) · comments use the provider’s globally unique id · code `github__code_{slug(path)}_c{i}` · **the id is never derived from content** — `content_hash` is a separate column precisely so that an edited message keeps its identity instead of orphaning every edge pointing at it.

---

## 6. Phase 3 — Source adapters

**Status 2026-08-18 — adapter core is done; fetchers exist; the Connector ABC is not the shipped seam.**

| Layer | Where | State |
|---|---|---|
| `adapt()` / `triage()` / `group_threads()` | `adapters/base.py` | done |
| Manifests + `pre` hooks | `adapters/manifests.py` | done for all 10 sources |
| Fetch | `connectors/{slack,github,gmail}.py` + `catalog.py` | lookback window via Composio `tools.proxy` |
| Fetch (deviation) | `connectors/{jira,confluence,fireflies}.py` | proxy 401s/403s/doubles-the-path on these three — lookback window via Composio `tools.execute` instead (named tools, see §16.2) |
| Allowlist | `connectors/gate.py` ↔ `web/lib/integrations.ts` | done; keep these two in lockstep |
| Code chunks | `adapters/code_chunk.py` | class then function split; oversized functions stay whole |
| `poll` / `backfill` / cursors | — | **not built**. Every sync re-fetches the lookback window. Scheduler ticks due connectors. |
| `scripts/conformance.py` | — | **not built**. `scripts/check_3_adapters.py` covers synthetic manifests + fetch fakes. |
| Distill / retrieve / chat | pipeline + reduced-lane `/api/ask` | **not stubs.** Ontology (CP6) and live lookup (CP10) still open. |

Seams that actually exist:

1. **`RequestFn`** (`connectors/http.py`) — `(method, endpoint, params, body?) → (data, headers)`. Production injects Composio proxy. Tests inject a fake. **Not universal:** Jira, Confluence, and Fireflies take `(composio, account_id)` and call `tool_request()` (also in `http.py`) instead — the generic proxy fails for each of them in a different way. See the deviation note in §16.2 before assuming every fetcher takes a `RequestFn`.
2. **`fetch_*_docs(...)` → `list[CanonicalDoc]`** — fetchers enrich raw payloads, then call `adapt_many(manifest, raws)`.
3. **`SourceManifest` + `adapt()`** — the only normalization path.

Do not add `adapters/slack.py`-style modules. Provider-specific code is a `pre` hook in `manifests.py` or enrichment inside the fetcher.

One adapter = `raw dict → CanonicalDoc | list[CanonicalDoc]`; thread-emitting adapters also return `dict[thread_id, list[CanonicalDoc]]` for distillation. A thread-like container = anything with `thread_id` and ≥3 items: Slack thread, email thread, ticket+comments, PR+reviews, meeting.

### 6.0 Six archetypes, not N bespoke adapters

The goal is **as many connections as possible**, so the adapter layer is built as six shapes rather than one integration per tool. Every source anyone will ever want to connect is one of these, and each shape is implemented **once**:

| Archetype | Shape | Thread grouping | Sources |
|---|---|---|---|
| **conversation** | messages in a channel/thread | `thread_id` | Slack, Discord, Teams, Gmail, Outlook, Intercom |
| **tracker** | item + comments, with status fields | ticket key | Jira, Linear, GitHub issues/PRs, Asana, ClickUp, Zendesk |
| **document** | page/file with a hierarchy | none (split parts `LINKED_TO`) | Confluence, Notion, Google Drive, Dropbox, Box |
| **record** | a structured row rendered to a sentence | none | HubSpot, Salesforce, custom databases |
| **code** | language-aware chunks of a file | none | GitHub, GitLab |
| **transcript** | speaker turns with a date | whole meeting | Fireflies, Zoom, Granola, Otter |

A new connector supplies a **manifest** mapping its payload onto an archetype — it does not write a new adapter:

```python
SLACK = SourceManifest(
    provider="slack", archetype="conversation",
    external_id="ts", body="text", author="user", container="channel",
    timestamp=("ts", "epoch"), thread=("thread_ts", "ts"),   # thread field, fallback
    url=lambda d: permalink(d), extra=["reactions", "files"],
    participants="mentions", pre=[strip_slack_markup],
)
```

The archetype adapter reads the manifest, the manifest holds everything provider-specific, and provider-specific *code* is limited to what genuinely cannot be declared: Gmail's quote stripping, GitHub's code chunker, Fireflies' turn windowing. Every one of those is a `pre=[...]` hook.

**This is the mechanism that makes a long connector list realistic.** Connector #12 should be a manifest, an auth entry, two fetch functions, and a conformance run — a few hours, not a project. If you find yourself writing a seventh archetype, stop and check whether the source really is a new shape.

**Universal rules:**

| ✅ DO | ❌ DON'T |
|---|---|
| Inspect one real doc per source **before coding** (10 min each) — mappings below are target shapes, field names drift | Code them blind, debug during ingest |
| `external_id` = the individual item's id | Use the container (channel/project/space) id — relations then point at the container |
| Skip bodies < 20 chars | Index stubs — ranking noise, real cost |
| Preserve raw handles exactly (`@soham`, `S. Ratnaparkhi`) | Normalize names in adapters — destroys the entity-resolution signal |
| tz-aware datetimes (`fromtimestamp(x, timezone.utc)`, `fromisoformat`) | Pass raw strings/floats — burst gaps + `period_of` break quietly |
| Keep genuine near-duplicates — two people saying the same thing in two channels is real signal about consensus | "Helpfully" dedupe near-matches — only byte-identical dupes drop |
| Compute `content_hash` in the adapter, from the **normalized** body | Hash the raw payload — provider metadata churns (view counts, reaction totals) and every doc looks changed every sync |

### 6.1 Change detection — the thing that makes "forever" affordable

Every sync re-fetches documents joel has already seen. Without a cheap way to notice that nothing changed, a connector on a 15-minute interval re-distills the same threads ~96 times a day and the LLM bill grows without a single new fact entering the system.

```python
def triage(doc: CanonicalDoc, known: dict[str, str]) -> str:
    """known: doc_id -> content_hash, loaded once per job from SQLite."""
    prior = known.get(doc.doc_id)
    if prior is None:            return "new"        # full pipeline
    if prior != doc.content_hash: return "changed"   # full pipeline + mark thread dirty
    return "unchanged"                               # touch last_seen, STOP
```

- **unchanged** → one SQLite `UPDATE docs SET last_seen=?`. No embed, no distill, no graph write, no LLM. This is the overwhelmingly common case and it must cost microseconds.
- **new** → normal pipeline.
- **changed** → normal pipeline, plus its `thread_id` goes into the dirty set for re-distillation (§7.5).

| ✅ DO | ❌ DON'T |
|---|---|
| Load the whole `doc_id → content_hash` map once per job (a few MB even at 500K docs) | One `SELECT` per fetched doc — that's the actual bottleneck at scale |
| Hash after quote-stripping and normalization | Hash before, so an unchanged email whose quoted tail re-renders looks changed |
| Count new/changed/unchanged into the job record — it's the single most useful diagnostic you have | Log nothing and wonder why the bill grew |

**Per-source specs:**

- **Slack:** one doc per message. `thread_id = thread_ts or ts`; roots have `thread_ts` **missing OR equal to `ts`**. `parent_id = thread_ts` iff ≠ `ts`. Keep `reactions` in `extra` (burst-filter fuel) and `<@U…>` mentions in `participants_raw`. Container = channel slug.
- **Gmail:** one doc per email. **Strip quoted reply chains** (else message N embeds messages 1…N-1 and the same text ranks N times); **keep signatures** — they carry canonical full names + emails, the best entity-resolution evidence in the corpus.
  ```python
  QUOTE_MARKERS = [re.compile(r'^On .{10,80} wrote:\s*$', re.M),
                   re.compile(r'^-{2,}\s*Original Message\s*-{2,}', re.M|re.I),
                   re.compile(r'^From: .+\nSent: .+\n', re.M)]
  def strip_quoted(body):
      cut = min([m.search(body).start() for m in QUOTE_MARKERS if m.search(body)] + [len(body)])
      return "\n".join(l for l in body[:cut].splitlines()
                       if not l.lstrip().startswith(">")).strip()
  ```
*Of the six below, Linear, Google Drive, and HubSpot have fetchers in `connectors/catalog.py`. Jira, Confluence, and Fireflies have their own `connectors/{provider}.py` and go through `tool_request()`, not the proxy — see §16.2. Specs below are still the target shape — 250-item cap, no poll/backfill cursors. They are **not** CP-C green.*

- **Linear / Jira:** ticket + each comment as separate docs; comments carry `parent_id = ticket key`, `thread_id = ticket key`. Jira `external_id` = the **issue key** (`AUTH-123`) — questions cite keys, never the numeric internal id. `status/priority/assignee` live in `extra` (they churn); only distiller-set `resolved` is a hot property. Container = project/team.
- **Confluence:** HTML → markdown with a real parser (`markdownify`/bs4), preserve headings + code blocks. Keep page hierarchy via `parent_id`. Infer `doc_type` (runbook|spec|policy|notes) into `extra` — feeds conflict precedence (§9.4). Split >3K-token pages on H2 boundaries into `_s{i}` parts with `linked_to` between.
- **Google Drive:** corpus ships extracted text (expected) → normal doc. PDFs extracted locally with pypdf. Binary Office files still skipped.
- **GitHub:** issues/PRs as docs (`github__issue_{slug(repo)}_N` / `github__pr_{slug(repo)}_N` — repo is part of the id), review/issue comments as comment docs (`parent_id` = qualified thread key). Empty PR/issue bodies fall back to the title (otherwise they vanish). **Code files:** default-branch blobs, language-aware chunks, never split a function body — an oversized function becomes one oversized chunk, never a bisected one. Live “is PR 118 merged?” is §13.2, not ingest:
  ```python
  BOUNDARIES = [re.compile(r'^(class|struct|interface|impl)\s+\w+', re.M),
                re.compile(r'^\s{0,4}(def |fn |func |function |[A-Za-z_:<>~]+\s+\w+\s*\()', re.M)]
  MAX_LINES = 120
  def chunk_code(path, src):
      units = split_at(src, BOUNDARIES[0]) or [src]; out = []
      for u in units:
          out += [u] if line_count(u) <= MAX_LINES else (split_at(u, BOUNDARIES[1]) or [u])
      return out          # title: f"{path} — {first_symbol}", granularity="code"
  ```
- **HubSpot:** body = a **rendered sentence** ("Deal 'Acme renewal' — stage negotiation, amount 50000, owner morgan. Notes: …"), structured copy in `extra.data`. Pick ~8 human-relevant properties, not all 200. Amounts as strings. Container = pipeline.
- **Fireflies:** speaker-turn chunks of ~40 turns, cut **between** turns (mid-turn cuts break attribution). **Parse `date` into a datetime** — never assign the ISO string to `timestamp`. Full turn list = thread grouping → one artifact per meeting (meetings hold the "why"). Shipped summaries/action_items are distiller *hints*, never the artifact.

---

## 7. Phase 4 — Distillation (the heart of the build)

> **Distill, then embed.** A four-message thread whose answer is "set `CKPT_PREFETCH=4`" becomes ONE record saying exactly that. Chatter informs the artifact, then never becomes a retrievable row.

Pipeline per thread: group **bursts** → LLM-distill the full thread → noise-filter bursts → emit 1 artifact row + N kept-burst rows.

### 7.1 Burst grouping — `distill/bursts.py`

```python
GAP_MINUTES = 7
def group_bursts(msgs):
    msgs = sorted(msgs, key=lambda m: m.timestamp); bursts, cur = [], None
    for m in msgs:
        new = (cur is None or m.author_raw != cur.author_raw
               or (m.timestamp - cur.end_ts).total_seconds() > GAP_MINUTES*60)
        if new:
            if cur: bursts.append(cur)
            cur = Burst(burst_id=f"{m.thread_id}_b{len(bursts)}", thread_id=m.thread_id,
                        author_raw=m.author_raw or "unknown", text=m.body,
                        message_external_ids=[m.external_id],
                        start_ts=m.timestamp, end_ts=m.timestamp,
                        has_reactions=bool(m.extra.get("reactions")))
        else:
            cur.text += "\n" + m.body; cur.message_external_ids.append(m.external_id)
            cur.end_ts = m.timestamp; cur.has_reactions |= bool(m.extra.get("reactions"))
    if cur: bursts.append(cur)
    return bursts
```

### 7.2 `prompts/distill_thread.md` — the most-tuned prompt in the repo

```
You distill one complete conversation thread into a structured knowledge artifact.

Return ONLY a JSON object. No prose, no markdown fences.

## Schema
{
  "message_roles": [{"index": <0-based>, "role": "question|answer|context|resolution|noise"}],
  "question": "<the question this thread ANSWERS, phrased as someone would ask it later>",
  "summary": "<what happened, <=2 sentences>",
  "resolution": "<the specific fix/decision/outcome, or null if unresolved>",
  "resolved": true|false,
  "systems": ["<components/projects/services touched>"],
  "code_refs": ["<identifiers VERBATIM: env vars, flags, error strings, ticket keys, fn names>"],
  "actors": [{"name": "<exactly as written>", "role": "asker|resolver|participant"}],
  "artifact_class": "decision|commitment|objection|incident|qa|status_update|noise",
  "supersedes": "<verbatim reference to the prior statement this overturns, or null>",
  "confidence": 0.0-1.0
}

## Rules
1. QUESTION: write the question a FUTURE reader would ask that this thread answers —
   not the first message verbatim. "Restore stalls after manifest load on the larger
   cluster" → "Why does restore stall after manifest load?" Future queries are
   questions; this line powers retrieval.
2. RESOLUTION is specific and actionable: "Set CKPT_PREFETCH=4 for the NFS mount",
   never "they fixed it". No concrete outcome → resolution null, resolved false.
   Do NOT invent closure.
3. ROLES: label every message.
   "context" = tangents/me-toos adding no durable knowledge
     ("My laptop also stalls when it sees Monday.")
   "noise" = greetings/acks/thanks ("sounds good, thanks! will try that")
   Context/noise contribute NOTHING to question/summary/resolution — use them only
   to disambiguate the real content.
4. CODE_REFS verbatim: CKPT_PREFETCH, ERR_MANIFEST_TIMEOUT, AUTH-123. Never
   paraphrase, lowercase, or translate — these power exact-match retrieval.
5. NAMES exactly as written ("@soham", "S. Ratnaparkhi"). Do NOT normalize or
   merge — a later stage does that.
6. CONDITIONALS: "we ship Friday if legal signs off" → class "commitment",
   resolution states the condition, resolved=false until confirmed in-thread.
7. SUPERSEDES only when the thread explicitly overturns a prior position
   ("actually let's not", "we're reverting X"). Quote how THIS thread refers to it.
8. Whole thread is chit-chat → artifact_class "noise" (it won't be indexed).
9. Ambiguity lowers confidence. Never resolve ambiguity by guessing.

## Thread
Source: {source_type}   Container: {container}   Items: {n}
---
[0] {author_0} ({ts_0}): {body_0}
[1] ...
---
```

**`artifact_class` note:** this 7-value list is an intentional subset of §4.1's 9-value `:Doc.artifact_class` enum (`decision|commitment|objection|incident|qa|status_update|reference|document|noise`) — `reference` and `document` are dropped here because a *thread* never produces them; those two only come out of `extract_ontology` (§9.1) running on singleton documents. §9.1's own `artifact_class` field must use the full 9-value enum, not a third variant — this was previously inconsistent (had `question` instead of `qa`, and was missing `document`) and is fixed there.

### 7.3 Noise filter

```python
CODE_TOKEN = re.compile(r'[A-Z][A-Z0-9_]{3,}|\w+\(\)|[a-z_]+\.[a-z_]{2,}|ERR\w*|=\s*\d|--\w+')
def has_rare_tokens(text, df):
    if CODE_TOKEN.search(text): return True
    toks = [t.lower() for t in re.findall(r'\w{4,}', text)]
    return any(df.frequency(t) < 0.02 for t in toks)      # <2% of corpus docs
def keep_burst(b, df):
    if b.role in ("resolution","answer","question"): return True   # distiller says it matters
    if b.has_reactions:                              return True   # humans voted
    if len(b.text.split()) >= 30 and has_rare_tokens(b.text, df): return True
    return False    # short + common + unreacted → "sounds good, thanks!" → drop
```

`df_index.py`: one corpus pass → doc-frequency Counter → `data/canonical/df.json` (this is the IDF signal, applied at ingest). Burst `role` = majority of member messages; any `resolution` message ⇒ burst role `resolution`.

| Burst | kept? | why |
|---|---|---|
| `ERR_MANIFEST_TIMEOUT: restore hangs after manifest load.` | ✅ | rare tokens |
| `Setting CKPT_PREFETCH=4 makes it complete.` | ✅ | role=resolution |
| 200-word design argument | ✅ | length + rare tokens |
| `sounds good, thanks! will try that` | ❌ | short, common, unreacted |
| `My laptop also stalls when it sees Monday.` | ❌ | role=context |

### 7.4 Row emission

Artifact (skip if class=`noise` or confidence < 0.3): `doc_id=artifact_id` · `title=question[:300]` · `body=normalized_body()` · `granularity="artifact"` · `resolved` · edges `DISTILLED_FROM` → each kept burst, `LINKED_TO` → thread root. Kept bursts: `granularity="burst"`, `REPLY_TO` → root. Dropped bursts are never stored.

**Burst text carries its thread's context** — embed `f"Thread: {artifact.question}\n{burst.text}"`, not the bare burst. A tangent answer whose vocabulary never reached the thread summary is exactly what bursts exist to catch, and it only stays findable if the topic rides along. (Anthropic's contextual retrieval; Cerebras does the same.) Store the bare text as `body` for display and FTS; prepend only for the embedding.

### 7.5 Re-distillation — what happens on the 400th sync

A thread is **dirty** when any of its messages was new or changed this job (§6.1). Dirty threads, and only dirty threads, re-run distillation.

```
dirty thread → re-group bursts → one distill call → new artifact + new kept-set
  ├─ artifact:      same artifact_id → upsert (content_hash changes → all three stores update)
  ├─ kept now, kept before      → upsert if the burst text changed, else untouched
  ├─ kept now, NOT kept before  → insert
  └─ kept before, NOT kept now  → DELETE from all three stores (§4.4's DELETE row)
```

The prior kept-set lives in SQLite (`thread_state` table: `thread_id, kept_burst_ids JSON, artifact_hash, last_distilled_at`), not a JSON file — a file gets clobbered when the scheduler and a manual Sync now overlap.

| ✅ DO | ❌ DON'T |
|---|---|
| Re-distill the WHOLE thread, not the delta — the resolution often changes meaning when a later message corrects it | Distill only the new messages and append; you'll get two contradictory artifacts for one thread |
| Iterate the prompt on 15 real threads before scaling | Scale to thousands on the first draft |
| One JSON-repair retry, then `failed_distill.jsonl` and leave the previous artifact in place | Retry-loop malformed outputs, or delete a good old artifact because the new call failed |
| Feed the distiller the WHOLE thread including noise (rule 3 needs to see it) | Pre-filter messages before distillation |
| Spot-check every `resolved:true` early on | Trust `resolved` — invented closure is the signature hallucination |

---

## 8. Phase 5 — Store layer

### 8.1 Schema

```python
class Store:
    def __init__(self):
        self.db = sqlite3.connect("data/index/joel.db", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")     # scheduler writes while chat reads
        run_migrations(self.db)                        # §14.3 — never executescript-on-boot
        self.vec_path = "data/index/joel.npz"
        self.model = SentenceTransformer(settings.embed_model)
        self.hydra = Hydra()
        self.index = LiveIndex(self.vec_path, self.db)  # §8.3
```

```sql
-- migrations/001_init.sql (abridged; the columns that matter)
CREATE TABLE docs(id TEXT PRIMARY KEY, title TEXT, body TEXT,
  source_type TEXT, container TEXT, granularity TEXT, artifact_class TEXT,
  validity TEXT, resolved TEXT, ts TEXT, period TEXT, url TEXT,
  author_raw TEXT, thread_id TEXT, extra JSON,
  content_hash TEXT NOT NULL, ingested_via TEXT, first_seen TEXT, last_seen TEXT,
  forgotten INTEGER NOT NULL DEFAULT 0);          -- owner-initiated forget, §14.5
-- 004_visibility.sql
ALTER TABLE docs ADD COLUMN visibility TEXT NOT NULL DEFAULT 'org';  -- org | channel:… | user:…
CREATE INDEX docs_thread ON docs(thread_id);
CREATE INDEX docs_hash   ON docs(id, content_hash);   -- the triage lookup
CREATE VIRTUAL TABLE docs_fts USING fts5(id UNINDEXED, title, body, content='');
CREATE TABLE thread_state(thread_id TEXT PRIMARY KEY, kept_burst_ids JSON,
  artifact_hash TEXT, last_distilled_at TEXT);
CREATE TABLE graph_written(id TEXT PRIMARY KEY, content_hash TEXT NOT NULL);
```

### 8.2 `upsert_docs` — one call, three destinations

```python
def upsert_docs(self, docs):
    # 0) APPEND to data/canonical/{source}.jsonl first — the source of truth
    # 1) SQLite: INSERT OR REPLACE into docs
    #    FTS5 is contentless, so a re-upsert MUST delete the old row first:
    #      INSERT INTO docs_fts(docs_fts, rowid, title, body) VALUES('delete', rid, old_t, old_b)
    #      INSERT INTO docs_fts(rowid, title, body)           VALUES(rid, new_t, new_b)
    #    Skipping the delete silently duplicates the row and the doc votes twice in the FTS lane.
    # 2) vectors: embed title+"\n"+body[:2000] (artifacts: normalized_body,
    #    bursts: thread-question prefix per §7.4), batches of 256, NORMALIZE at write
    # 3) HydraDB: for each id, compare against graph_written.content_hash —
    #      absent        → UNWIND-batched CREATE, then structural edges
    #      hash differs  → MATCH (d:Doc {id}) SET <every mutable property>
    #      hash same     → skip
    #    then upsert graph_written. THIS is the client-side MERGE.
    # 4) self.index.apply(upserted_ids, deleted_ids)   # §8.3 — no restart required
    # per-destination retry ledgers: data/state/pending_{sqlite|vec|graph}.jsonl
```

The graph step used to be "skip anything already written," which meant an edited or re-distilled doc kept stale properties in HydraDB forever while SQLite moved on — counts still matched, so nothing caught it. Comparing hashes instead of presence is the fix.

### 8.3 `LiveIndex` — the vector index must not require a restart

Vector search is a brute-force dot product over the npz matrix, with numpy boolean masks over doc metadata for the §10.2 filters. Both the matrix and the metadata arrays live in memory. **A scheduler that ingests every 15 minutes into an index loaded once at startup means new documents are invisible until the process restarts** — the single worst bug available in this design, because retrieval keeps working and just quietly lags reality.

```python
class LiveIndex:
    # matrix: float32 (N, 384) normalized · ids: list[str] · row_of: dict[str,int]
    # meta:   parallel numpy arrays for granularity, validity, period, source_type, forgotten
    def apply(self, upserted: dict[str, np.ndarray], deleted: set[str]):
        # under a writer lock: overwrite rows for known ids, append unknown ones,
        # mark deleted/forgotten rows in a boolean tombstone mask (never resize on delete),
        # refresh the metadata arrays for touched rows, bump self.version
    def search(self, q, mask=None, k=20):
        # readers take the current (matrix, meta) tuple by reference — a swap is atomic,
        # so a search in flight finishes against a consistent snapshot
```

Compact (drop tombstoned rows, rewrite the npz) when tombstones exceed 20% of rows, or on demand from settings. Persist to `.npz` after each apply; on boot, load and verify `len(ids) == SELECT count(*) FROM docs WHERE forgotten=0`, else rebuild.

| ✅ DO | ❌ DON'T |
|---|---|
| Hot-apply every upsert to the in-memory index | Load once at startup — the scheduler makes this a permanent staleness bug |
| FTS5 contentless (`content=''`) + explicit rowid↔id map, with delete-before-insert on every re-upsert | Duplicate bodies into the FTS shadow table, or re-insert without deleting |
| Quote user text in FTS queries (`"…"`) | Raw questions into `MATCH` — FTS5 operators (`OR NEAR *`) in a question crash it |
| `PRAGMA journal_mode=WAL` — the scheduler writes while chat reads | Default rollback journal, then watch `/ask` block behind a sync |
| `scripts/rebuild_index.py` regenerates SQLite + npz **+ graph** from `canonical/*.jsonl` | Treat indexes as the source of truth — canonical JSONL is |
| Per-destination retries | All-or-nothing batches stranding good rows |

At scale: 384-dim brute force is milliseconds to ~200K docs and roughly 150ms at 1M on one core. **Switch to hnswlib when `len(ids) > 250_000`** — same interface, same masks applied post-search with an inflated `k`. Do not build it before then; do write `LiveIndex.search` so the swap touches one file.

---

## 9. Phase 6 — Ontology + entity resolution (the track's named hard part)

Pipeline: extract (LLM, on **artifacts** for threads — shorter, noise-free; on full text for singleton docs) → resolve (3-stage funnel) → reconcile (conflicts + supersession) → write Cypher edges.

### 9.1 `prompts/extract_ontology.md`

```
You extract organizational memory from one business document.
Return ONLY a JSON object. No prose, no markdown fences.

## Schema
{
  "entities": [{"key":"<local key>","name":"<surface form AS WRITTEN>",
    "type":"PERSON|TEAM|PROJECT|CUSTOMER|SERVICE|POLICY|METRIC|INCIDENT",
    "identifier":"<email/handle/ticket-key if present, else null>"}],
  "relations": [{"source":"<key>","target":"<key>","predicate":"<UPPER_SNAKE>",
    "context":"<one sentence, <=200 chars, grounded in the text>",
    "temporal_details":"<'since 2021'|'2026-05-20'|null>"}],
  "artifact_class": "decision|commitment|objection|incident|qa|status_update|reference|document|noise",
  "supersedes": "<verbatim quote of the prior statement this overturns, or null>",
  "confidence": 0.0-1.0
}

## Rules
1. GROUNDING: every entity/relation traces to explicit text. Never infer a relation
   the document does not state or clearly imply.
2. SURFACE FORMS exactly as written ("@soham", "S. Ratnaparkhi", "Sam"). Do NOT
   normalize or merge — a later stage does that.
3. ENTITY TYPE is what the thing IS (a person, team, project…), never what
   happened to it. A decision, commitment, or objection is never an entity —
   it's this document's artifact_class, or a relation between two entities below.
4. PREDICATES — prefer: OWNS, DECIDED, COMMITTED_TO, OBJECTED_TO, DEPENDS_ON, BLOCKS,
   ASSIGNED_TO, REPORTED, ESCALATED, APPROVED, RESOLVED, AFFECTS (§4.2's Entity→Entity
   edge set). Never emit MENTIONS (that's the automatic Doc→Entity edge, not something
   to extract) or REVERSED (that's a Doc→Doc edge written by §9.3's supersession
   logic, never asserted directly by extraction).
5. CONDITIONALS: "ship Friday if legal signs off" = COMMITMENT + DEPENDS_ON, not DECISION.
6. SUPERSEDES only on explicit overturning; quote this document's reference to it.
7. Ambiguity lowers confidence; do not guess.
8. Limits: <=25 entities, <=40 relations.

## Document
Source: {source_type}  Container: {container}  Time: {timestamp}  Author: {author_raw}
Title: {title}
---
{body}
---
```

For thread artifacts: distillation's `artifact_class`/`supersedes` **win** — extraction contributes entities+relations only; artifact `actors[]` seed the registry.

### 9.2 Resolution funnel (cheap → expensive)

**A. Blocking:** group by normalized-email local part, metaphone of last token, first-initial+last-name, container co-occurrence. **B. Fuzzy:**

```python
def pair_score(a, b):
    s = max(fuzz.token_set_ratio(na:=norm(a), nb:=norm(b)), fuzz.partial_ratio(na, nb)) / 100
    if initials(na) == initials(nb): s += 0.10
    if same_email_localpart(a, b):   s += 0.35
    if shared_containers(a, b) >= 2: s += 0.08
    return min(s, 1.0)
# >=0.92 auto-merge · <0.55 auto-reject · else stage C
```

**C. `prompts/resolve_entity.md`** (ambiguous band only; cache verdicts by sorted pair):

```
Decide whether two name mentions refer to the SAME real person/entity.
Return ONLY JSON: {"same": true|false, "confidence": 0.0-1.0, "reason": "<=120 chars"}

Evidence:
A: "{a_name}"  contexts: {a_ctx}  identifiers: {a_ids}
B: "{b_name}"  contexts: {b_ctx}  identifiers: {b_ids}

Rules:
1. Matching identifiers (same email/user id) → same, confidence 0.95+.
2. CONFLICTING identifiers (two different emails, both present) → NOT same, even with
   identical names. Different people share names.
3. Nickname/initial form + overlapping containers + no conflicting identifier → likely same.
4. Same name, disjoint containers, no shared project, no identifier → insufficient
   evidence: false, LOW confidence. Do not guess.
5. Never merge a PERSON with a TEAM, SERVICE, or PROJECT.
6. Bias toward NOT merging: a false merge corrupts every downstream answer; a missed
   merge loses recall on one entity.
```

Registry `data/entities/registry.json`: `{"person_0041": {canonical_name, type, identifier, aliases[], evidence{}}}` → graph: one `:Entity` per id, one `:Alias` per lowercased surface form, `:AUTHORED` edges backfilled.

### 9.3 Conflict + supersession

For contradictory claims on the same `(entity, predicate)`:

```
1. Explicit `supersedes` wins — always.
2. Later timestamp wins — UNLESS earlier is a formal doc (confluence/gdrive,
   doc_type runbook|spec|policy) and later is chat with confidence < 0.7.
3. Same window → authority: confluence/gdrive > jira/linear > fireflies > gmail
   > slack > hubspot notes.
4. Unresolvable → BOTH stay current + logged to data/graphs/conflicts.json.
   Surfacing disagreement IS the feature.
```

Loser: `SET validity='superseded'` in the graph **and** SQLite (both lanes filter on it) + `(:Doc)-[:REVERSED {ts}]->(:Doc)`. Superseded rows are kept forever — "what was the plan before it changed" is a question people actually ask, and with append-only memory this flag is the *only* mechanism by which anything stops being true.

Canonicalize entity names through the registry **before** writing ontology edges — raw surface forms as nodes = two Sams = dead multi-hop.

### 9.4 Incremental reconciliation — the part that makes updates work

Reconciliation is a comparison *between* claims, so it can't run only over new documents. When a Slack message arrives today reversing a decision from March, the new doc alone contains no conflict — the conflict only exists relative to the old claim, which this job never looked at.

After each sync's extraction pass:

```
new/changed docs → their extracted relations → collect the touched (entity_id, predicate) pairs
for each touched pair:
    load EVERY current claim on that pair from the graph (not just this job's)
    run the §9.3 precedence rules across the whole set
    flip losers to validity='superseded' in graph + SQLite, write :REVERSED
    log the decision with both doc_ids and the rule that fired
```

Bounded by touched pairs, so a 20-document sync reconciles a handful of pairs, not the corpus. A **full reconciliation pass** (every pair) runs from `scripts/rebuild_index.py` and from a settings button, for when precedence rules change.

Entity resolution is incremental the same way: new surface forms get blocked and scored against the existing registry, not against a from-scratch clustering. Cache LLM verdicts by sorted pair so a name seen a thousand times is judged once. **A merge decision is never silently revisited** — once two aliases are one entity they stay merged until the owner splits them, because a registry that reshuffles itself every sync makes every historical answer irreproducible.

| ✅ DO | ❌ DON'T |
|---|---|
| Reconcile the touched pairs across all their claims | Reconcile only the docs in this batch — the reversal never fires |
| Keep the loser retrievable, flagged | Delete the superseded claim — the history question dies with it |
| Log which rule decided, with both doc_ids | Flip validity with no audit trail; you cannot debug a wrong flip later |

---

## 10. Phase 7 — Retrieval

### 10.1 `prompts/plan_query.md`

```
Classify a question against a company knowledge system and emit a retrieval plan.
Return ONLY JSON:
{
  "intent": "lookup|multihop|conflict|temporal|aggregate|absent_check|who|live",
  "entities": ["<names exactly as the question writes them>"],
  "exact_tokens": ["<identifiers/error strings/quoted phrases worth exact search, else []>"],
  "temporal": {"period": "<2026Q2|null>", "wants_history": true|false},
  "needs_current_only": true|false,
  "rewrites": ["<2 alternates varying VOCABULARY, not word order>"]
}
Rules: exact_tokens = CAPS_SNAKE, error codes, quoted strings, ticket keys.
intent "live" = asks about RIGHT-NOW state of a connected tool ("latest message in #eng",
"is PR 118 merged", "anything new today") — memory alone cannot answer these.
Never answer. Only plan.
```

### 10.2 Lanes — run concurrently (thread pool); each returns an ordered doc list

| Lane | Implementation | Catches |
|---|---|---|
| VECTOR (always) | npz dot product, top-20 (+ once per rewrite) | paraphrase |
| VEC-ARTIFACTS (always) | vector masked to `granularity='artifact'`, top-15 | distilled resolutions |
| FTS | FTS5 MATCH bm25, top-15 | rare tokens (IDF) |
| PHRASE | FTS5 `"exact phrase"` per exact_token | pasted errors, identifiers |
| GRAPH | aliases→entities→expand ontology+MENTIONS ≤2 hops→doc_ids ranked by hop distance then ts (≤200 docs) | multi-hop, relations |
| WHO_KNOWS (intent=who) | the §4.3 Cypher; people + evidence doc_ids | ownership |

Modifiers: `temporal` → mask `period`, **no recency preference** (you want the old state) · `conflict` → don't mask `validity` (need both sides) · `needs_current_only` → mask `validity='current'` on vector lanes. Masks are numpy boolean filters over `LiveIndex.meta` (§8.3), which the store refreshes on every upsert — **never a snapshot taken at startup.** Every lane also excludes `forgotten=1`. When an `AskContext` is passed (production `/api/ask` always does), every lane further restricts to `allowed_stamps(ask)` so a public-room question cannot surface a private-channel or employee doc (§1.4).

### 10.3 Fusion — `retrieve/fuse.py`

```python
RRF_K, PER_SOURCE_CAP, EPS = 60, 3, 0.005
def rrf_fuse(lists: dict[str, list], top_n=20):
    score, best = defaultdict(float), {}
    for name, docs in lists.items():
        contributed = defaultdict(int)
        for rank, d in enumerate(docs, 1):
            if contributed[d.id] >= PER_SOURCE_CAP: continue
            contributed[d.id] += 1
            score[d.id] += 1.0 / (RRF_K + rank)          # Σ 1/(60+rank_L)
            best.setdefault(d.id, d)
    ranked = sorted(score, key=score.get, reverse=True)
    out, i = [], 0                                        # age decay: newer wins TIES only
    while i < len(ranked):
        j = i
        while j+1 < len(ranked) and score[ranked[i]] - score[ranked[j+1]] < EPS: j += 1
        out += sorted(ranked[i:j+1], key=lambda s: best[s].ts or "", reverse=True)
        i = j + 1
    return [best[s] for s in out[:top_n]]
```

Why k=60: rank-1 in one list = 0.0164; rank-4 in **three** lists = 0.0469 — consensus beats a single strong vote. Age decay applies only inside tie windows, never as a blanket boost.

### 10.4 `prompts/rerank.md` (top-20 in → keep 8–10)

```
Score how well each candidate helps ANSWER the question. Answering ≠ being about the topic.
Return ONLY JSON: [{"id":"...","score":0-10,"reason":"<=80 chars"}]
Rules:
1. States the fact/fix/decision → 8-10.
2. Exact identifier overlap with question tokens → +2.
3. granularity=artifact with an on-point resolution outranks raw chatter.
4. Topically related but non-answering → <=3. Be harsh — this is THE failure mode.
5. Question asks CURRENT state + candidate old/likely superseded → cap 4, reason "stale".
6. Score only what the snippet shows. Never invent.
```
Input rows: `id · title · granularity · ts · 300-char snippet`.

### 10.5 `prompts/answer.md`

```
You are joel, a company brain. Answer strictly from the retrieved context below.

Return ONLY JSON:
{
  "status": "answered|partial|conflicted|absent",
  "answer": "<the answer, or why not>",
  "citations": ["<doc_id>", ...],
  "reasoning_path": ["<P1>", "<P2>"],
  "conflict": {"positions":[{"claim":"...","doc_id":"...","when":"...","source_type":"..."}],
               "assessment":"<which is likely current and why, or 'unresolved'>"} | null,
  "confidence": 0.0-1.0
}

## Status selection
- answered: complete, unambiguous answer in context.
- partial: part answered — say exactly which part is missing. Do NOT pad the gap.
- conflicted: sources make incompatible claims the question depends on. Populate
  `conflict`. Never silently pick one.
- absent: the context does not contain the answer.

## The absent rule (most important)
Absent is a CORRECT, VALUABLE outcome. Specifically:
- No world knowledge. If the context doesn't say it, you don't know it.
- No inference from adjacency: "doc mentions the billing team AND a migration" does
  not mean the billing team owns the migration.
- Relevance is not containment — a related chunk is not an answer.
- If you're writing "likely / presumably / it appears / would suggest" — STOP.
  That is absent or partial, not answered.
- A confident wrong answer is far worse than "not in the data."

## Citations
Every claim traces to a cited doc_id · cite the doc that STATES the fact, not one
that mentions the topic · can't cite it → don't claim it.

## Conflicts: explicit supersession > recency > formality (policy page > chat) >
else "unresolved". Temporal: distinguish "true then" from "true now"; stale-only
evidence for a current-state question → say it's stale.

## Style: answer first, no preamble · specific (names, dates, ticket ids) ·
<=150 words unless a list is required.

---
RETRIEVED CONTEXT:
{context}
GRAPH PATHS:
{paths}     ← [P1] Sam Ratnaparkhi --DECIDED--> Postgres migration ("…", 2026-03-14, doc …)
QUESTION: {question}
```

Deterministic gate on top. **Note the scale**: this runs on reranker scores (0–10), not RRF scores. Fused RRF values top out near 0.09, so a 0.30 threshold against them would abstain on literally every question — an easy and completely silent way to build a system that never answers.

```python
RERANK_FLOOR = 5.0        # reranker scale is 0-10; tune on real traces, never on RRF scores

def should_abstain(reranked, ans):
    if not reranked:                                        return True
    if reranked[0].rerank_score < RERANK_FLOOR:             return True
    if ans["status"] == "answered" and not ans["citations"]: return True
    if set(ans["citations"]) - {d.id for d in reranked}:    return True   # fabricated citation
    return False
```

Log `(question, rewritten_question, plan, per-lane ranks, rerank scores, status, citations)` → `data/state/traces.jsonl`, capped by rotation. These traces are how the floor gets tuned, and later they're the free evaluation set (§16.3) — real questions someone actually asked beat any synthetic benchmark.

When the gate fires, or the planner's intent is `live`, the read-only live lookup (§13.2) runs before `absent` is returned.

---

## 11. Phase 8 — The sync engine (freshness without a human)

This section is the difference between a demo and a tool. Everything above describes ingesting a document once; this describes doing it every fifteen minutes for two years.

### 11.1 Model

**The `jobs` table already exists** (built in Phase 3, verified against real syncs on 2026-08-18) with columns `id, connection_id, started_at, finished_at, status, new_count, changed_count, unchanged_count, duration_ms, error`. CP8 does **not** redefine it — it's a migration adding columns, not a fresh `CREATE TABLE` with different names for the same things:

```sql
-- connections: new columns for the sync engine (extends §12.2's existing table)
ALTER TABLE connections ADD COLUMN interval_min INTEGER DEFAULT 15;
ALTER TABLE connections ADD COLUMN next_run_at TEXT;
ALTER TABLE connections ADD COLUMN last_run_at TEXT;
ALTER TABLE connections ADD COLUMN cursor TEXT;              -- provider pagination/delta token, forward direction
ALTER TABLE connections ADD COLUMN backfill_cursor TEXT;     -- separate, walks BACKWARD through history
ALTER TABLE connections ADD COLUMN backfill_done INTEGER DEFAULT 0;
ALTER TABLE connections ADD COLUMN consecutive_failures INTEGER DEFAULT 0;
ALTER TABLE connections ADD COLUMN paused INTEGER DEFAULT 0;

-- jobs: new columns on the EXISTING table (id/connection_id/started_at/finished_at/
-- status/new_count/changed_count/unchanged_count/duration_ms/error already there)
ALTER TABLE jobs ADD COLUMN kind TEXT DEFAULT 'sync';         -- sync|backfill|reconcile
ALTER TABLE jobs ADD COLUMN threads_distilled INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN llm_calls INTEGER DEFAULT 0;
-- status already uses running|ok|error, not queued|running|ok|failed — keep using
-- the existing values, don't introduce a second vocabulary for the same column
```

### 11.2 The loop

One asyncio task inside joel-api. No cron, no Celery, no Redis — a self-hosted workspace should be one API process plus a graph database.

```
every 30s:
  if not SYNC_ENABLED: continue
  due = SELECT * FROM connections
        WHERE paused=0 AND status IN ('ready','error') AND next_run_at <= now()
        ORDER BY next_run_at
  for c in due:
      if running_jobs >= SYNC_MAX_CONCURRENT_JOBS: break
      if has_running_job(c.id): continue          # never two jobs on one connector
      enqueue(sync_job(c))
  if idle capacity and no sync work:
      enqueue(one page of the oldest incomplete backfill)   # strictly lowest priority
```

**Catch-up rule:** `next_run_at = now + interval` computed when a job *finishes*, never `previous + interval`. A laptop closed for a week wakes up and runs each connector **once**, not 672 times.

**Backoff on failure:** `1m → 5m → 15m → 1h → 6h`, capped, reset on success. `consecutive_failures ≥ 5` moves the card to `error` with the last message visible and keeps retrying at 6h. Auth failures skip the ladder entirely and go straight to `needs_reauth` — retrying a revoked token 5 times helps nobody.

**Rate limits:** honour `Retry-After` exactly; on Slack 429 sleep the stated seconds and resume from the same cursor. Never drop a page on a rate limit — resume, because a dropped page is a permanent hole in memory that nothing will ever notice.

### 11.3 Progressive deep backfill

First connect must be usable in minutes, and complete eventually.

1. **Fast pass** — last 30 days, forward cursor stored. Connector reaches `ready` and chat opens.
2. **Deep pass** — a background job walks *backwards* one page at a time from the oldest doc held, storing `backfill_cursor`, until the account's beginning or a user-set floor. Runs only when no incremental sync is pending, yields immediately when one becomes due, and survives restarts by construction.
3. `backfill_done=1` → the card reads "full history indexed", with the date of the oldest document.

This is why `content_hash` and cursors are per-document and per-direction: the two passes overlap in the middle and must not re-distill the seam.

### 11.4 Token lifecycle

The most common way a self-hosted tool dies silently: a refresh token expires and nothing says so.

| ✅ DO | ❌ DON'T |
|---|---|
| Refresh on 401 once, retry the request once, then give up | Retry-loop a 401 into a rate-limit ban |
| Refresh proactively when `expires_at` is within 5 minutes | Wait for the failure on every single call |
| Refresh failure → `needs_reauth`, scheduler stops that connector, card shows **Reconnect** | Keep hammering a dead credential and bury it in logs |
| Store `access_token`, `refresh_token`, `expires_at` Fernet-encrypted with `JOEL_SECRET` | Log a token, ever, at any level |
| Surface re-auth in the chat banner too | Let someone ask questions for a week against a connector that stopped syncing in silence |

### 11.5 Cost control

Distillation is the recurring spend, so it is bounded on four sides: unchanged docs never reach an LLM (§6.1); only dirty threads re-distill (§7.5); `DISTILL_MAX_CONCURRENCY` caps global fan-out so two backfills can't stampede the key; and `noise`-class threads are distilled once and never re-embedded.

Per-job `llm_calls` rolls up into a running counter on `/profile`. **Pause ingestion** in settings stops the scheduler without disconnecting anything.

| ✅ DO | ❌ DON'T |
|---|---|
| One global LLM semaphore shared by every job | Per-job concurrency — two connectors then fan 200 parallel calls |
| Show new/changed/unchanged per job | Report "synced ✓" and hide that it re-distilled the whole workspace |

---

## 12. Phase 9 — The app (web + API)

### 12.1 Deployment — one command

```yaml
# docker-compose.yml
services:
  hydradb:
    image: ghcr.io/dupenodi/hydradb-node:hackhydra   # PREBUILT — see below
    environment: [CLOUD_PROVIDER=local, LOCAL_PATH=/store, GRAPH_NAMESPACE=default,
                  GRAPH_ID=default, GRAPH_CELL_ID=cell-0, GRAPH_CELLS=cell-0,
                  GRAPH_NODE_ID=node-0, GRAPH_BOLT_NODE_ADDRESSES=node-0=hydradb:7687,
                  GRAPH_ADVERTISED_BOLT_ADDR=hydradb:7687, GRAPH_DATA_CACHE_DIR=/cache,
                  GRAPH_AUTH_TOKEN_FILE=/run/secrets/hydra_token,
                  GRAPH_ALLOW_PLAINTEXT=true, RUST_MIN_STACK=33554432]
    volumes: [hydra-store:/store, hydra-cache:/cache]
    secrets: [hydra_token]
  joel-api:
    build: ./api
    ports: ["8000:8000"]
    env_file: .env
    volumes: [joel-data:/app/data]
    depends_on: [hydradb]        # healthcheck: wait for hydradb /readyz before serving
  joel-web:
    build: ./web
    ports: ["3000:3000"]
    environment: [NEXT_PUBLIC_API=http://localhost:8000]
volumes: {hydra-store: {}, hydra-cache: {}, joel-data: {}}
secrets: {hydra_token: {file: ./secrets/hydra_token}}
```

**The prebuilt image is mandatory, not an optimization:** build the HydraDB repo's own `Dockerfile` once, push `ghcr.io/dupenodi/hydradb-node:v1`. Without it every single user pays a 20-minute Rust compile before seeing a screen. Bake the embedding model into the joel-api image (`RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"`) so first boot doesn't hang on a 130MB download.

Install path: `git clone … && cp .env.example .env` (one LLM key) `&& docker compose up` → localhost:3000.

| ✅ DO | ❌ DON'T |
|---|---|
| Test compose from a clean clone on a pruned Docker (`docker system prune`) | Ship a compose that works only because your host has state |
| Pin image tags; document every env var in `.env.example` | `latest` + undocumented env |
| Persist everything under named volumes; kill-and-up must survive | Store state in container FS |
| `restart: unless-stopped` on all three services | Let a transient crash silently end syncing until someone notices weeks later |
| Verify `docker compose pull && up` after a version bump runs migrations cleanly on an **existing** volume | Only ever test upgrades on an empty database |

### 12.2 API — FastAPI (`joel/app.py`; `routes.py` was never the module)

Public (no session): `GET /api/auth/status`, `POST /api/auth/setup`, `POST /api/auth/login`, `GET/POST /api/auth/invite/{token}`. Everything else requires a valid session cookie.

| Endpoint | Does |
|---|---|
| `GET /api/auth/status` | `setup` \| `login` \| `ok` + me + workspace |
| `POST /api/auth/setup` | first admin + workspace (409 if users already exist) |
| `POST /api/auth/login` · `POST /api/auth/logout` | session cookie |
| `GET /api/workspace` · `PATCH /api/workspace` | workspace row; members + invites for admins |
| `POST /api/workspace/invites` · `DELETE …/invites/{id}` | invite / revoke (admin) |
| `PATCH /api/workspace/members/{id}` · `DELETE …` | role / remove (admin) |
| `GET/PUT /api/profile` | signed-in display name |
| `GET /api/org` | workspace + first-connector readiness (compat shape) |
| `GET/POST /api/connectors` · `DELETE /api/connectors/{id}` | connector CRUD |
| `POST /api/connectors/{id}/sync` | enqueue a job now (409 if one is already running) |
| `PATCH /api/connectors/{id}` | interval, pause, history floor |
| `GET /api/connectors/{id}/jobs` | job history: counts, duration, error |
| `GET /oauth/{provider}/start` · `GET /oauth/{provider}/callback` | OAuth flow (also used for re-auth) |
| `GET/POST /api/conversations` · `GET /api/conversations/{id}` | conversation list / messages |
| `POST /api/ask {conversation_id, question}` | streams `status → rewritten → lanes → tokens → citations → reasoning_path`. AskContext is the signed-in actor's web desk — **not** a room field on the body. |
| `GET/PUT /api/settings` | settings kv (admin) |
| `GET /api/health` | hydra reachable · index consistency triple · per-connector last success · queue depth · schema version |
| `POST /api/docs/{id}/forget` | the only removal path (§14.5) |
| `POST /api/org/wipe` | danger zone: truncate corpus (admin; identity rows stay) |

**Streaming caveat:** `EventSource` is GET-only, so a POST cannot be consumed as SSE by the browser's built-in client. Use `fetch` with a `ReadableStream` (shipped).

SQLite tables: `orgs` (workspace, `id=1`), `users`, `memberships`, `sessions`, `invites`, `connections` (§11.1), `jobs`, `conversations`, `messages`, `settings` (kv), `docs` (+ `visibility`), `schema_version`.

### 12.3 Web — pages (Next.js)

**`/setup`** — empty install: admin email/password + company domain → workspace. One-shot.

**`/login` · `/join`** — session; join requires an invite token from an admin.

**`/onboarding`** — after sign-in: LLM key → first tool → live checklist → chat when that connector is ready. Domain/org is **not** collected here anymore.

**`/integrations`** — one card per tool: logo, status pill (§1.2 state machine), **last sync + next sync**, doc count, [Connect] [Sync now] [Pause] [Disconnect], inline error, **Reconnect** when `needs_reauth`. Expandable job history.

**`/` (chat)** — conversations sidebar · message stream with status badges ✅🟡⚠️🚫 · citations · reasoning path · ingestion / re-auth banners. Retrieval is filtered by the signed-in desk AskContext.

**`/settings`** — workspace name/domain, **members + invites** (admin), LLM keys, spend, wipe (typed confirmation).

Every page is a thin view over queries this spec already builds — the product layer is presentation, connectors and scheduling, not new intelligence.

### 12.4 Connectors — Composio proxy, one fetch interface

The original `Connector` ABC (`poll` / `backfill` / `refresh` / `auth_status`) is **not implemented**. Do not introduce it until cursors exist. The shipped contract for 7 of the 10 connectors is:

```python
RequestFn = Callable[..., tuple[Any, dict[str, str]]]
# fetch_*_docs(..., request: RequestFn) -> list[CanonicalDoc]
```

`app._provider_request` wraps `composio.tools.proxy`. Fetchers never see an access token. `oauth.py` only Fernet-encrypts `{composio_account_id}` at rest.

**Jira, Confluence, and Fireflies are the exception.** The generic proxy fails for each in a different way — Jira 401s, Confluence 403s ("not permitted to use Confluence"), Fireflies double-posts to `/graphql/graphql`. Their fetchers instead take `(composio, account_id)` and call `tool_request()` (`connectors/http.py`), which wraps `composio.tools.execute()` against named tools (`JIRA_SEARCH_ISSUES`, `CONFLUENCE_GET_PAGES`, `FIREFLIES_GET_TRANSCRIPTS`). Same auth broker, different transport for these three. See §16.2 for the full story.

**Composio is the auth broker AND the fetch transport** for every connector — via `tools.proxy` for most, `tools.execute` for the three above. The earlier plan (“retrieve the token, hit provider APIs directly”) is wrong against Composio: `connected_accounts.get()` masks tokens and Slack returns `invalid_auth`. Rate-limit / `Retry-After` handling is weaker than a direct client; live with it until proven otherwise. Slack still honours `Retry-After` on its leftover direct-token branch (tests); production always uses `caller=`.

**Custom OAuth is cut.** One connect path: paste Composio API key → hosted OAuth per toolkit → callback stores the connected account id.

**Incremental fetch today** — lookback window, full re-fetch, `content_hash` triage. Not provider cursors:

| Provider | What a sync actually does | Catches edits? |
|---|---|---|
| Slack | `conversations.history` + replies for picked channels, `oldest=` lookback | Yes, via re-fetch window |
| Gmail | `messages.list` `after:YYYY/MM/DD` then `messages.get` | Yes for new mail; not Gmail `historyId` |
| GitHub | `/user/repos` (skip fork/archived, cap 80) then issues + comments + `/pulls/{n}/reviews` `since=`, plus default-branch code chunks (8 repos / 30 files) | Yes for those endpoints |
| Linear / Notion / Drive (proxy) | lookback + **hard cap 250** | Yes if `updated` moved |
| Jira / Confluence / Fireflies (tool-execute, not proxy) | lookback + **hard cap 250** | Yes if `updated` moved |
| HubSpot (proxy) | lookback + **hard cap 100** | Yes if `updated` moved |

| ✅ DO | ❌ DON'T |
|---|---|
| Live progress on the card (`backfilling 340 docs → distilling 12 threads → linking → ready`) | A silent 15-minute first sync — people assume it's broken and kill it |
| One shared LLM queue with a concurrency cap across all connectors | Let two backfills fan 200 parallel distill calls into your key |
| Surface the last error verbatim on the card, with Retry | Bury sync failures in logs |
| Treat "connector complete" as: pagination + rate limits + cursor resume + token refresh + incremental re-sync | Ship a happy-path fetch and call the connector CP-C done — **today's fetchers are lookback ingest, not complete** |

### 12.5 Live lookups

Moved to §13.2 — it's part of the agent, not the connector layer.

---

## 13. Phase 10 — The agent: three tiers of memory

The distinction this section exists for: **not every message is a knowledge question, and not everything joel fetches deserves to live forever.** Missing this is why chat assistants feel dumb on the second turn and expensive on the hundredth.

| Tier | Holds | Lifetime | Indexed? |
|---|---|---|---|
| **Long-term memory** | the corpus — docs, artifacts, entities, edges | forever (append-only) | yes, all six lanes |
| **Live lookup** | right-now state fetched on demand | answers one question, then enters ingest through the normal filter | eventually, via the pipeline |
| **Working memory** | the current conversation | until the conversation is deleted | **never** |

### 13.1 Working memory — follow-ups and small talk

"What about the other one?" retrieves nothing, because it isn't a question — it's a pointer at the previous turn. The spec had no answer for this, which means every follow-up would have failed.

Before planning, rewrite the message into something standalone. `prompts/rewrite_question.md` — the 7th prompt:

```
Rewrite the user's latest message into a standalone question understandable with no
conversation history. Resolve pronouns and references using the turns provided.
Return ONLY JSON: {"question": "<standalone>", "kind": "knowledge|meta|chitchat"}

Rules:
1. Change nothing else. Do not expand scope or add detail the user did not give.
2. Already standalone → return it verbatim.
3. kind "meta" = about this conversation or about joel ("what did you just say",
   "summarise this chat", "which sources did you use"). Answerable from the turns alone.
4. kind "chitchat" = greetings, thanks, small talk.
5. Never answer the question.

## Recent turns
{last_n_turns}
## Latest message
{message}
```

- `knowledge` → the full §10 pipeline, on the rewritten question.
- `meta` / `chitchat` → **answered from the conversation alone. No lanes, no rerank, no ingest.** One cheap call, sub-second. This is the "small task that doesn't need long-term memory" path, and it should be visibly faster than a real question.

Working memory is the last 6 turns, trimmed to a token budget, passed to the rewriter and appended to the answer prompt. Persisted in `messages` so conversations survive a reload.

**Conversations are never indexed** — not into FTS, not into vectors, not into the graph. joel's own output must never become a retrievable "fact", because that is exactly how one hallucination turns into a permanently citable source with a real-looking doc_id, and nothing downstream could ever tell the difference. Data *fetched from your tools* becomes memory; text *generated by joel* does not.

### 13.2 Live lookup — read-only, then remembered

Memory-first, always: §10 runs first. Live fires on exactly two conditions — planner intent is `live`, or the abstention gate fired and at least one connector is authorized.

**Read-only whitelist:** latest N messages in a channel · current state of a PR or issue · an issue by key · a mail thread by id. Nothing else, and nothing that writes. Because the agent cannot act, there is no confirmation UI to design, no audit log of writes to keep, and no path by which a bad plan modifies your Jira.

Then what it fetched **enters memory through the front door**: same adapter, same `content_hash` triage, same distillation and noise filter, tagged `ingested_via='live'`. Nothing bypasses the filter — a "hey, you around?" pulled live is discarded exactly as it would have been during a scheduled sync. The loop closes: the next sync would have found it anyway; the question just got there first.

| ✅ DO | ❌ DON'T |
|---|---|
| Hard cap: **2 lookups per question, 10s timeout each, read-only whitelist** | Open-ended tool loops — this is a lookup, not an autonomous agent |
| Label live citations with the LIVE chip; the answer says "as of just now" | Blend live facts into memory citations indistinguishably |
| Stream a "checking live…" event so the UI shows the stall has a reason | Eight silent seconds |
| Push live results through the *normal* ingest filter | Insert raw fetched rows straight into the index because "we already have them" |
| Abstain honestly: "Not in the company's memory — a live check of Slack found nothing either" | A plain 🚫 that hides the live attempt |

---

## 14. Phase 11 — Running forever (the operations the spec was missing)

Everything here exists because the product is meant to run for years on someone else's machine, unattended, while you are not watching.

### 14.1 Health and observability

`GET /api/health` is the one place to look when something feels wrong:

```json
{ "hydra": "ok", "schema_version": 7, "sync_enabled": true, "queue_depth": 0,
  "index": {"sqlite": 48213, "vectors": 48213, "graph": 48213, "consistent": true},
  "connectors": [{"provider":"slack","status":"ready","last_success":"…","next_run":"…",
                  "consecutive_failures":0,"backfill_done":true}],
  "corpus": {"oldest_doc":"2019-04-02","artifacts":3311,"entities":842},
  "spend_30d": {"distill": 1204, "extract": 1180, "answer": 96} }
```

The index triple is the drift detector. If the three numbers disagree, something wrote outside `upsert_docs` — find it, don't paper over it with a rebuild.

### 14.2 Growth

| Scale | What changes |
|---|---|
| < 250K docs | nothing. Brute-force numpy, SQLite FTS5, HydraDB as-is. |
| > 250K docs | swap `LiveIndex.search` to hnswlib (§8.3). One file. |
| > 2M docs | revisit SQLite (fine) and graph traversal bounds (tighten `maxLen`, cap fan-out on hub entities). |
| any scale | bound every traversal; a five-year Slack export has entities connected to everything. |

Growth is one-directional because memory is append-only. That is a deliberate trade: unbounded disk in exchange for never losing history. Disk is cheap; a company brain with amnesia is worthless.

### 14.3 Schema migrations

Numbered SQL files in `api/joel/migrations/`, a `schema_version` row, applied in order on boot inside a transaction. Never `CREATE TABLE IF NOT EXISTS` at runtime — that silently diverges across installs and you cannot reason about anyone's database.

The graph has no migration tool, and does not need one: **its migration path is a rebuild from canonical JSONL.** If the node model changes, bump a `graph_model_version` in settings; on boot, if it doesn't match the code, rebuild the graph in the background and show a banner. This is only tolerable because canonical is the source of truth — protect that property.

### 14.4 Backup and portability

`data/` is the whole product. Copy that directory and you have moved the install. Document it in the README as one sentence, because self-hosters will ask.

`scripts/rebuild_index.py` regenerates SQLite + npz + graph from `data/canonical/*.jsonl`. It is the recovery path, the migration path, the change-your-embedding-model path, and the "I think the index is wrong" path. **Run it in CI on a small fixture** — a rebuild script that has never been run is not a backup story.

### 14.5 Forgetting (the one deletion path)

Memory is append-only, so nothing disappears because a source deleted it. But a real tool must be able to forget on request: a message with a pasted credential, something posted in the wrong channel, an ex-employee's request.

`POST /api/docs/{id}/forget` → `forgotten=1` in SQLite, tombstone in `LiveIndex`, `DETACH DELETE` (or `SET d.deleted='true'`, per §4.4) in the graph, **and the canonical JSONL line rewritten to a tombstone** so a rebuild doesn't resurrect it. Cascades to the artifact if the doc was its only source. Surfaced as a small control on every citation chip, because the moment you notice something shouldn't be there is the moment it's cited at you.

### 14.6 First-run and degraded modes

| Situation | Behaviour |
|---|---|
| No connectors yet | `/chat` locked with a plain explanation and a link to connect one. Never an empty chat box that answers everything with 🚫. |
| LLM key missing or rejected | Banner at the top of every page with the provider's actual error. Ingestion pauses rather than burning retries. |
| HydraDB unreachable | Chat degrades to five lanes with a banner ("relationship search unavailable"), rather than 500ing. Ingestion queues graph writes to the retry ledger. |
| Disk full | Sync stops, banner, no partial writes. |

Degrading loudly beats failing silently, and both beat pretending.

---

## 15. Ship checklist (a real install, not a submission)

- `docker compose up` from a **clean clone on pruned Docker** reaches onboarding with only an LLM key set
- Connect a real Slack/GitHub/Gmail account end to end, from OAuth to a cited answer, without touching a terminal
- Leave it running overnight: next morning, new messages are answerable and no connector is stuck
- `docker compose down && up` — state survives, scheduler resumes, no duplicate documents
- Upgrade path tested: bump the image on an **existing** volume, migrations run, data intact
- README: what it is · one-command install · connect a tool · **how your data is stored and where** · backup = copy `data/` · how to forget a document · architecture · attribution (HydraDB AGPL-3.0, Cerebras article as design reference)
- MIT `LICENSE` · `.env` untracked · `.env.example` complete and commented
- No secret ever logged; verify by grepping a full backfill's logs for the token

## 16. Phases

No dates. Order matters, days don't. Two tracks: **Core** runs strictly in sequence because each phase consumes the one before; **Connectors** is a loop that opens after Phase 12 and never really closes — the goal is to get through as many waves as possible.

Landing page is **done** (§20) — content tweaks only, not a workstream. Every phase's exit criteria are the checklists at the end of this document (§22); do not start phase N+1 with a red box in phase N.

**Correction (2026-08-18):** an earlier revision of this section claimed Phase 0/1 (HydraDB environment, graph model) were skipped in favor of Phase 3 (adapters), based on the §22 checkboxes for CP 0/CP 1 being unchecked. That was wrong — it confused "checklist never ticked" with "work never done." Git history and a live re-verification both confirm CP 0 and CP 1 were built and passed against a real local HydraDB node on 2026-08-16, a day *before* the adapter work in Phase 3. The phases were done in the right order; the §22 checkboxes just weren't updated at the time, which made the plan lie about its own status. Both are now corrected in §22. No ordering deviation actually happened here — the lesson is procedural, not architectural: **tick the §22 boxes in the same commit as the work**, or a plan audit like this one is the only way to find out they're stale.

### 16.0 Phase −1 — Fix what's already specified and wrong

Small, and everything downstream inherits them, so they come before new work:

~~abstain floor on the rerank scale (§10.5)~~ done in CP7 (`synthesize.py::RERANK_FLOOR`, explicitly the 0-10 reranker scale, not RRF's ~0.09) · ~~FTS5 delete-before-insert (§8.2)~~ done in CP5 (`store_sql.py::_upsert_sqlite_and_fts`) · ~~graph upsert by `content_hash` instead of skip-if-present (§8.2)~~ done in CP5 (`store_sql.py::_upsert_graph`, `graph_written` table) · ~~`LiveIndex` hot reload (§8.3)~~ done in CP5 (`live_index.py`) · ~~incremental reconciliation (§9.4)~~ done in CP6 (`ontology/reconcile.py`, bounded to the touched `(entity, predicate)` pairs — see CP6 status note in §22) · ~~`DELETE` added to the Cypher compat pass (§4.4)~~ done in CP1 (`store.py::delete_edge`/`delete_node`) · ~~single store, no `JOEL_DATASET` (§2.1)~~ done 2026-08-19 (`config.py::Settings` no longer has a `dataset` field; `.env.example` no longer documents it) · ~~pick the SSE-over-POST approach (§12.2)~~ done — `fetch` + `ReadableStream` on the client, `StreamingResponse` on `/api/ask`.

### 16.1 Core track

| Phase | Name | § | Done when | Checks |
|---|---|---|---|---|
| 0 | Environment + local HydraDB | §3 | a write round-trips over HTTP and Bolt | CP 0 |
| 1 | Graph data model | §4 | every Cypher assumption verified or a fallback chosen | CP 1 |
| 2 | Canonical models | §5 | hashes stable, ids collision-free | CP 2 |
| 3 | Adapter archetypes + change detection | §6 | the same docs twice cost zero LLM calls | CP 3 |
| 4 | Distillation + re-distillation | §7 | appending one message causes exactly one distill call | CP 4 |
| 5 | Store: three destinations, hot index, migrations | §8 | edit a doc → all three update, no restart | CP 5 |
| 6 | Ontology + incremental reconciliation | §9 | a later reversal supersedes an earlier decision across two jobs | CP 6 |
| 7 | Retrieval + answer + abstention | §10 | the ten probes pass on your own data | CP 7 |
| 8 | Sync engine | §11 | it runs overnight unattended and is still correct | CP 8 |
| 8a | Identity + workspace | §1.1 · §12.2 | setup, login, invite, roles | `check_identity.py` |
| 8b | Visibility + ask context | §1.4 | stamp at ingest; public cannot read private | `check_visibility.py` |
| 9 | The app | §12 | connect a tool and get a cited answer without a terminal | CP 9 |
| 10 | Agent: rewriting, meta/chitchat, live lookup | §13 | follow-ups work; "hi" costs one call | CP 10 |
| 11 | Operations | §14 | pull HydraDB's plug and chat still answers | CP 11 |

**8a, 8b, 6, and 10 are done (2026-08-19).** 8a/8b were not in the original core track (the brief was single-user, no login); they are now prerequisites for Slack/MCP surfaces, which reuse `AskContext` rather than inventing a second ACL. Phase 6 (ontology) and Phase 10 (agent: follow-ups, meta/chitchat, live lookup) shipped in the same pass — see their status notes in §22 for what's real vs. simplified relative to the original pseudocode (entity resolution's blocking, reconciliation's authority-ladder scope, and live lookup covering 2 of 4 whitelisted operations so far).

**Still open on the skeleton (before treating Slack bot / MCP as in-scope):** data vs tool connectors (`owned_by`, org-shared vs personal) · channel membership so a desk can read private rooms the actor is in. Leasing a teammate's connection for one request is explicitly later — [Supermemory](https://supermemory.ai/docs/company-brain/permissions) only uses it when nobody has connected the tool at org level.

**Phase 3 needs real data**, so Slack lands as a minimal fetch during Phase 3 (enough to pull real messages) and is hardened to full conformance in Phase 12. Building the pipeline against invented data is how you discover in Phase 8 that your `thread_id` mapping was wrong the whole time.

### 16.2 Connector track — waves

| Phase | Wave | Connectors | Fetchers | Conformance |
|---|---|---|---|---|
| 12 | Harness | Slack | [x] channels + threads, real data | **no** — no `conformance.py`, no cursors |
| 13 | 1 | GitHub, Gmail | [x] real data. **Deviation:** GitHub shipped WITH code chunks + `GET /pulls/{n}/reviews` bodies, not deferred as originally planned | no |
| 14 | 2 | Jira, Linear, Notion | [x] real data, lookback + 250 cap. **Deviation:** Jira is tool-execute (`JIRA_SEARCH_ISSUES` / `JIRA_LIST_ISSUE_COMMENTS`), not the generic proxy — see below | no |
| 15 | 3 | Confluence, Google Drive, Fireflies | [x] real data. Drive = Google Docs + text + PDF extract. **Deviation:** Confluence and Fireflies are tool-execute, not the generic proxy — see below | no |
| 16 | 4 | HubSpot | [x] real data, deals only (Zendesk/Intercom not started) | no |
| 17 | 5 | Discord, Teams, Outlook, GitLab, … | not started | — |

Waves 1–4 **fetch** and are now verified against real data end to end. They are still not shipped in the CP-C sense (no cursors, no `conformance.py`). Do not add wave 5 until Slack/GitHub pass CP-C or you are explicitly expanding the allowlist.

**Deviation from §16.3's "one fetch function `fetch_{provider}_docs(*, since|after, request: RequestFn)`":** Jira, Confluence, and Fireflies do not use the generic Composio REST/GraphQL proxy — it fails for each in a different way (Jira 401, Confluence 403 "not permitted to use Confluence", Fireflies posts to a doubled `/graphql/graphql` path). Their fetchers instead take `composio` + `account_id` and call first-class Composio tools (`JIRA_SEARCH_ISSUES`, `CONFLUENCE_GET_PAGES`, `FIREFLIES_GET_TRANSCRIPTS`) through a shared `tool_request()` helper in `connectors/http.py`. Linear, Notion, Drive, HubSpot, Gmail, GitHub, and Slack still use the plain `RequestFn` proxy. Live in `connectors/jira.py`, `connectors/confluence.py`, `connectors/fireflies.py` (not `catalog.py`, and not `adapters/{provider}.py` — manifests are still the only per-provider file in `adapters/`).

**GitHub ingest now includes** language-aware code chunks and `GET /pulls/{n}/reviews` bodies. **Not ingest (live §13.2):** current PR/issue state — whitelist those reads when the agent is built; do not ingest merge-state for that.

**Next after adapters:** retrieval and chat are wired. Remaining connector work is CP-C (cursors, `conformance.py`), not "wire chat." Company-brain skeleton remaining: connector ownership, then channel membership, then Slack/MCP surfaces.

**Real-data verification pass — done (2026-08-18):** ran sync twice across all ten allowlisted connectors against live accounts. All ten `connections.status='ready'`, all latest jobs `status='ok'`, and the second pass on every provider reported `new=0, changed=0` with the full doc count in `unchanged` (content_hash triage is honestly working, not just on fixtures). Doc counts at verification time: Gmail 255, GitHub 619, Jira 15, Notion 10, Confluence 6, Google Drive 5, Linear 4, HubSpot 1, Slack 1, Fireflies 0 (empty account within the 30-day lookback, not a failure). `scripts/check_pending_adapters.py --sync --all --timeout 600` reproduces this; GitHub and Gmail each take several minutes so the wait was bumped from 120s to 600s.

**Fixed along the way (not planned, discovered during real-data testing):**
- Google Drive: endpoints were double-prefixed (`/drive/v3/files` against a proxy base that already includes `/drive/v3`) → 404. Fixed to bare `/files`.
- Gmail/Drive OAuth: a custom Google-specific auth-config/scope-shaping path in `composio_conn.py` triggered Google's "This app is blocked" screen. Removed; both now use the plain documented `composio.create()` + `session.authorize()` flow with only `gmail.readonly` / `drive.readonly` scopes.
- Jira: generic proxy to `/rest/api/3/...` returned 401 even with an ACTIVE connected account → moved to tool execution (see deviation note above).
- Confluence: generic proxy to `/wiki/rest/api/content` returned 403 "Current user not permitted to use Confluence" despite ACTIVE scopes → moved to tool execution.
- Fireflies: generic proxy posted to `/graphql` against a toolkit whose base URL is already `/graphql`, doubling the path → moved to tool execution.

**Remaining deferred adapter follow-ups (come back later, not blocking distillation):**
- Add a small conformance / smoke layer for Composio proxy endpoint shapes so path mismatches like Google Drive's fail fast instead of at sync time.
- Keep Google auth on the plain documented Composio session flow; do not re-introduce custom Gmail / Drive scope shaping on managed auth without a dedicated repro, because that was the path that triggered the blocked-app screen.
- Revisit Google Drive coverage: consider exporting Sheets/Slides and making file-type / size limits configurable once CP 3 is stable on real data.
- Do a second real-data quality pass (👁 eyeball, not automatable) on Gmail / Slack / GitHub bodies and thread grouping — CP 3's §22 items 3.3 (real Slack handles), 3.5 (real code file, real email) are still open.

### 16.3 Adding connector N — the recipe

1. Pick the archetype (§6.0). If none fits, stop and think hard before adding a seventh.
2. Write the manifest in `adapters/manifests.py` — field mapping, thread rule, container, url builder, `pre` hooks. No new `adapters/{provider}.py`.
3. Allowlist: `connectors/gate.py` **and** `web/lib/integrations.ts` (same id/toolkit/ingest).
4. One fetch function, normally `fetch_{provider}_docs(*, since|after, request: RequestFn)`. If the generic Composio proxy 401s/403s or mangles the endpoint path for this provider (it has for 3 of 10 so far — see §16.2), fall back to `fetch_{provider}_docs(*, since|after, composio, account_id)` calling `tool_request()` against named Composio tools instead. Note whether the API surfaces edits or needs a Slack-style re-fetch window.
5. Run `scripts/check_3_adapters.py`. When `scripts/conformance.py --provider X` exists, that is the ship bar (CP-C).
6. Icon in `web/icons/`, card copy, default interval.
7. Ship it. Then the next one.

### 16.4 Last: measurement

Once the product is real, evaluation is nearly free — `traces.jsonl` already holds real questions with real retrieved sets and real outcomes. Label a few hundred of your own traces and you have a better evaluation set than any public corpus, because it's your data and your questions. Ablations (vector-only → +artifacts → +RRF → +rerank/graph) run against that. No benchmark corpus, no dual-dataset plumbing, no eval-shaped detours before the tool exists.

## 17. Cut list (bottom-up)
1 connector waves 4–5 (stop wherever you stop; each shipped connector stands alone) · 2 live lookups (memory-first chat survives without them) · 3 job-history UI (keep the `jobs` rows, drop the panel) · 4 conversations sidebar → single conversation · 5 progressive deep backfill (the fast pass alone is usable) · 6 hnswlib swap (not needed under 250K docs) · 7 access leasing (personal connectors first) · 8 Slack bot / MCP (web desk must keep working) · **NEVER CUT: one-command install · login + workspace members · visibility stamps + AskContext · the background scheduler · change detection · the conformance suite (cut it and every later connector costs double) · chat with abstention + citations · distillation · entity resolution · the ontology in HydraDB · RRF fusion · rebuild-from-canonical.**

A wave is never half-shipped: a connector is either passing CP-C and visible, or it's a coming-soon card. A connector that half-works is worse than one that isn't there, because it puts holes in memory that nothing reports.

## 18. Risks + prompt index
HydraDB build fails locally → day-1 task, Ubuntu/WSL best-documented · Cypher subset missing MERGE/SET/DELETE/rel-props → §4.4 fallbacks, verified day 1 · Bolt auth differs → HTTP is the verified path · Composio token retrieval unavailable → branch ② (loop actions), verify on day 1 because every connector is written against the answer · distill cost → change detection is the control; measure `llm_calls` per job from the first sync · over-merge in entity resolution → bias rule + CP6 eyeball; merges are sticky by design so a bad one is expensive · lanes rank poorly → tune top-k and the abstain floor on `traces.jsonl` · **silent staleness** (the scheduler stops and nobody notices) → `/api/health` + the re-auth banner exist for exactly this.

**Prompts (7):** `rewrite_question` (cheap, 1/turn) · `distill_thread` (DISTILL, 1/dirty thread, most-tuned) · `extract_ontology` (EXTRACT) · `resolve_entity` (RESOLVE, ambiguous pairs, cached forever) · `plan_query` (RESOLVE, 1/q) · `rerank` (RERANK, 1/q) · `answer` (ANSWER, 1/q). All: JSON-only + one repair retry · rules after schema · negatives carry their reason · long input last.

## 19. Master gotcha checklist (pin it)
`RUST_MIN_STACK=33554432` or the node aborts on first query · unset `CLOUD_PROVIDER` reads as literal `null` · `LOCAL_PATH` must pre-exist · `GRAPH_ALLOW_PLAINTEXT=true` for dev · node holds the foreground = working · **a listening port proves nothing; a round-tripped write does** · macOS direct-cargo needs `BINDGEN_EXTRA_CLANG_ARGS` · venv for Python deps (PEP 668) · `strong` reads in checkpoints · verify MERGE/SET/**DELETE**/rel-props before coding store.py · bound all traversals · never interpolate raw text into Cypher · ids identical across SQLite/npz/graph · bodies in SQLite, never graph props · **FTS5 contentless needs delete-before-insert or rows silently duplicate** · quote user text in FTS5 · normalize embeddings at write · **graph upsert compares `content_hash`, never presence** · **the vector index is hot-reloaded, never loaded once at startup** · **the abstain floor is on the 0–10 rerank scale, not the ~0.09 RRF scale** · `next_run_at` computed at job finish, so a week offline is one catch-up run not 672 · auth failures skip the backoff ladder and go straight to `needs_reauth` · re-distill the whole thread, never the delta · reconcile the touched entity-predicate pairs, not just the new docs · conversations are never indexed · `PRAGMA journal_mode=WAL` · lowercase/slug every filterable value · AGPL attribution, joel stays MIT.

---

## 20. Landing page — BUILT ✅ (reference only)

*The landing page ships in `web/`. This section is the original brief, kept for the brand rules and copy source. Content tweaks only — it is not a workstream and does not appear in §16. One copy fix to make: the footer line "Made for Hack Hydra" should read "Built on HydraDB (AGPL-3.0)."*

### 20.0 Original brief — copy, animations, and the Claude Design prompt

**Brand (from the kit):** the mark is a chunky 3D-extruded asterisk/gear with an eye at the center — *the eye in the machine*. Palette: `#FF2D2D` red, `#000000`, `#F5F5F5` (off-white). Style: neo-brutalist — hard offset shadows (no blur), thick black strokes, flat fills, heavy grotesque type (Archivo Black / Space Grotesk headlines, Inter or IBM Plex Mono for body/code). Logo rules: never stretch, recolor beyond the palette, add soft effects, or rotate the lockup (the *animated hero petals may rotate — the wordmark never does*). Respect clearspace ≈ one petal-width.

### 20.1 Copy (final, paste-ready)

**Hero**
- H1: **Your company forgets. joel doesn't.**
- Sub: joel turns Slack, Jira, email, docs and meetings into a living graph of decisions, people and promises — self-hosted, open source, and honest enough to say **"not in the data."**
- Primary CTA (styled as a terminal chip): `docker compose up` — Get started
- Secondary CTA: ★ Star on GitHub
- Micro-trust line under CTAs: MIT licensed · runs on your machine · built on HydraDB

**Feature trio**
1. **Distill, then remember.** Every thread becomes one clean record — the question, the resolution, the exact refs. "sounds good, thanks!" never becomes a search result.
2. **A graph, not a pile.** Who decided, what overturned it, who actually knows. joel keeps a decision-reversal ledger, so stale answers die instead of resurfacing.
3. **Honest by default.** Every claim cites its source. When the answer isn't in your data, joel says so — in red, proudly.

**How it works (4 steps):** Connect *(your tools via OAuth)* → Distill *(threads → structured artifacts before anything is embedded)* → Graph *(people resolved across tools, decisions linked in HydraDB)* → Ask *(cited answers, conflict callouts, honest abstention)*.

**The honest-AI block (dark section):**
H2: **The most useful thing an AI can say is "I don't know."**
Body: joel refuses to guess. Conflicting sources get shown side by side. Superseded decisions get marked, not repeated. Missing answers get a straight 🚫 — not a hallucination.

**Self-hosted block:** H2: **Your data never leaves your machine.** Body: local graph database, local embeddings, your own LLM key. One `docker compose up`. No accounts, no telemetry, no limits.

**Footer CTA:** H2: **Give your company a memory.** · `docker compose up` · GitHub link.

### 20.2 Animation ideas (all code — CSS/SVG/Framer Motion, no video assets)

1. **Hero mark, alive:** the asterisk petals rotate slowly (20s loop, CSS transform on the petal `<g>`) while the **eye stays level and blinks** every ~6s (scaleY keyframe). On pointer move, the pupil tracks the cursor (tiny JS, ±3px translate). This one interaction makes the logo unforgettable.
2. **Distillation funnel (feature 1):** messy chat bubbles ("sounds good, thanks!", "my laptop also stalls…", `ERR_MANIFEST_TIMEOUT…`) drift into a funnel; noise bubbles get struck through and fade; one clean card pops out the bottom with a hard-shadow *thunk* (Framer Motion timeline, scroll-triggered).
3. **Graph grow-in (feature 2):** SVG nodes pop in with springy scale, edges draw via `stroke-dashoffset`; then a red `REVERSED` edge snaps in and the old node flips to grey/dashed. Loops.
4. **The abstention stamp (feature 3 / honest block):** a chat bubble shows a typing indicator… then a red rubber-stamp **NOT IN THE DATA** slams down at a slight angle (scale 1.4→1 with overshoot). The brand's signature micro-moment — also use it as the 404 page.
5. **Terminal boot (self-hosted block):** monospace card types `docker compose up`, then the readiness checklist ticks line by line (`fetched ✓ distilled ✓ people resolved ✓ graph linked ✓`), cursor blinking.
6. **RRF consensus strip (optional, nerd-bait):** three ranked lists slide in; a row appearing in all three glows red and lifts to the top of a merged list. Caption: *consensus over confidence.*
7. **Connector marquee:** monochrome tool chips (Slack, Jira, Gmail, Confluence, Drive, GitHub, HubSpot, Linear, Fireflies) in a slow infinite marquee; chips flip to red on hover.
8. **Scroll texture:** section dividers use the offset-shadow motif — blocks arrive with the shadow landing a beat after the fill (two elements, staggered spring).

### 20.3 The Claude Design prompt (paste this whole block)

```
Build a single-page marketing landing page for "joel" — an open-source, self-hosted
"company brain". React + Tailwind + Framer Motion only; every visual and animation is
code (CSS/SVG/canvas) — no images, no videos, no stock assets.

BRAND
- Logo: a chunky 3D-extruded 8-petal asterisk/gear with an eye in the center
  ("the eye in the machine"). Recreate it as inline SVG: flat black petals with a hard
  offset extrusion (offset ~8px, NO blur), white eye outline, black pupil.
- Palette, strictly: #FF2D2D (red), #000000, #F5F5F5. No other hues. No gradients
  except an optional subtle red-tinted background wash in the hero.
- Type: Archivo Black (or Space Grotesk 700) for headlines — tight, uppercase-friendly;
  Inter for body; IBM Plex Mono for code/terminal elements.
- Aesthetic: neo-brutalist. Hard offset shadows (solid, no blur) on cards and buttons,
  2px black borders, generous whitespace on #F5F5F5, one full-black section.
- Logo rules: never stretch, never recolor outside the palette, never soft-shadow.
  The wordmark "joel" is lowercase, heavy, set tight next to the mark.

PAGE SECTIONS, in order:
1. Nav: mark + "joel" left; links Docs · GitHub; right-aligned red button "Get started".
2. HERO: H1 "Your company forgets. joel doesn't." Sub: "joel turns Slack, Jira, email,
   docs and meetings into a living graph of decisions, people and promises —
   self-hosted, open source, and honest enough to say 'not in the data.'"
   Primary CTA is a terminal-styled chip reading `docker compose up`; secondary
   "★ Star on GitHub". Micro-line: "MIT licensed · runs on your machine · built on HydraDB".
   HERO ANIMATION: the big logo mark — petals rotate slowly (20s), the eye stays level,
   blinks every ~6s, and the pupil follows the cursor a few pixels.
3. FEATURE TRIO (cards with hard shadows):
   a) "Distill, then remember." — every thread becomes one clean record; 'sounds good,
      thanks!' never becomes a search result. ANIMATION: chat bubbles fall into a funnel,
      noise bubbles get struck through and fade, one clean card pops out with overshoot.
   b) "A graph, not a pile." — who decided, what overturned it, who actually knows;
      a decision-reversal ledger. ANIMATION: SVG graph nodes spring in, edges draw via
      stroke-dashoffset, then a red REVERSED edge snaps in and an old node turns
      grey/dashed.
   c) "Honest by default." — every claim cites its source; missing answers get a
      straight refusal. ANIMATION: chat bubble with typing dots, then a red rubber
      stamp slams down reading "NOT IN THE DATA" (rotate -6deg, scale 1.4→1 overshoot).
4. HOW IT WORKS: 4 numbered steps — Connect → Distill → Graph → Ask (one line each,
   from the copy above), connected by a drawn line that animates on scroll.
5. DARK SECTION (full black, white text, red accents):
   H2 "The most useful thing an AI can say is 'I don't know.'"
   Body: "joel refuses to guess. Conflicting sources get shown side by side. Superseded
   decisions get marked, not repeated. Missing answers get a straight refusal — not a
   hallucination." Include a mock chat exchange showing a ⚠️ conflicted answer with two
   dated positions, then a 🚫 abstention.
6. SELF-HOSTED SECTION: H2 "Your data never leaves your machine." Terminal card that
   TYPES `docker compose up` then ticks a readiness checklist line by line
   (fetched ✓ · distilled ✓ · people resolved ✓ · graph linked ✓), blinking cursor.
   Below: a slow monochrome marquee of tool chips (Slack, Jira, Gmail, Confluence,
   Drive, GitHub, HubSpot, Linear, Fireflies) that flip red on hover.
7. FOOTER CTA: H2 "Give your company a memory." + the terminal chip CTA + GitHub link.
   Tiny footer: "joel is MIT licensed. Built on HydraDB (AGPL-3.0). Made for Hack Hydra."

MOTION RULES: scroll-triggered, once, with springs (no linear easings); shadows land a
beat after fills (staggered). Respect prefers-reduced-motion (freeze loops, keep
opacity fades). Everything responsive down to 360px; hero mark scales, marquee wraps.
TONE: confident, dry, zero SaaS-purple, zero glassmorphism, zero gradient-blob clichés.
```

## 21. References
hydra-db/hydradb repo (README, AGENTS.md, architecture.md, cypher-compat.md) · Sentra Company Brain essays · [Supermemory Company Brain — overview](https://supermemory.ai/docs/company-brain/overview) · [Supermemory — permissions graph](https://supermemory.ai/docs/company-brain/permissions) · Cerebras "How we built our knowledge base" — full notes in [`docs/cerebras-knowledge-base.md`](docs/cerebras-knowledge-base.md) · Composio docs (verify token retrieval and action names at build time) · Slack / GitHub / Gmail API references for incremental fetch (§12.4).

---

## 22. Checkpoints

How to use these: each box is one assertion, small enough to be unambiguously true or false. Automate what's automatable in `scripts/check_*.py`; the ones marked 👁 need eyes and a judgement call. **Do not start the next phase with a red box in the current one** — every one of these exists because the failure it catches is silent.

---

### CP 0 — Environment (§3)

**Status 2026-08-18 — done, re-verified live against a real running HydraDB node during this session** (originally built 2026-08-16 per git history; the §22 checkboxes below were just never ticked at the time, which read as CP0 being unstarted — it wasn't). `scripts/check_0_env.py` passed end to end: storage smoke test, HTTP+Bolt round-trip, a live call to all 5 model aliases, and a real local embedding. One real gap found and fixed while re-verifying: `sentence-transformers` was missing from `api/requirements.txt` despite CP0 depending on it — added.

**0.1 HydraDB builds**
- [x] `just native-check` passes — *covered by `just smoke` below in `check_hydra_smoke`; both are `just`-recipe build gates and smoke is the one CP0 actually runs*
- [x] `just smoke` passes — *`check_0_env.py::check_hydra_smoke`, live: "graph object-store smoke passed at epoch 10"*
- [x] the node starts and holds the foreground (that's working, not hanging) — *`graph-node` process confirmed running and serving on :7687/:8443/:9090 throughout this session*

**0.2 A write round-trips**
- [x] `CREATE` a `FOLLOWS` edge over HTTP, `MATCH` it back, get the expected value — *`check_0_env.py::check_hydra_protocols`*
- [x] the same read with `"consistency":"strong"` returns the same thing — *same check, `strong=True`*
- [x] admin `/readyz` responds on :9090 — *confirmed directly: `curl -i http://127.0.0.1:9090/readyz` → `200 OK`*

**0.3 Bolt path**
- [x] `RETURN 1` over Bolt with the token-as-password auth scheme — *covered by `check_hydra_protocols`'s Bolt edge read, which only succeeds if Bolt auth is working*
- [x] one parameterized query with a value containing an apostrophe succeeds — *exercised indirectly throughout `check_1_graph_model.py` (e.g. `ctx="raised prices 8% for enterprise tier"` round-trips via Bolt params, not string interpolation)*

**0.4 Models reachable**
- [x] one live call per model alias (distill, extract, answer, resolve, rerank) returns — *`check_0_env.py::check_llm_aliases`, real OpenRouter calls, all 5 aliases*
- [x] the embedding model loads locally and encodes a string to 384 dims — *`check_0_env.py::check_embedding`, `BAAI/bge-small-en-v1.5`*
- [x] no key is printed in any log line — *checked `check_0_env.py`'s own output and `hydra.py`/`llm.py`: keys only ever go into an `Authorization` header, never `print`/`log`*

---

### CP 1 — Graph data model (§4)

**Status 2026-08-18 — done, re-verified live** (also originally built 2026-08-16). `scripts/check_1_graph_model.py` passed end to end against the same live node. One real gap found and fixed: `DELETE`/`DETACH DELETE` was implemented nowhere and tested nowhere, despite §4.4 flagging it as a day-1 decision — probed directly against the live node (both forms work, no `deleted='true'` fallback needed), then `HydraStore.delete_edge`/`delete_node` and a `check_delete_and_detach_delete` assertion were added.

**1.1 Nodes and edges**
- [x] probe `:Doc` + 2 `:Entity` + `:Alias` + one `DECIDED` edge written and strong-read back — *`check_1_graph_model.py::check_doc_entities_alias_edge`*
- [x] relationship properties (`doc_id`, `ctx`, `ts`) come back intact — or the reification fallback is in place — *come back intact; no reification needed*

**1.2 Property filters are exact**
- [x] for every filterable property, a MATCH on the right value hits — *`check_property_filters`*
- [x] for every filterable property, a MATCH on a wrong-case value **misses and does not error** — *same check, `{correct}__wrong` for every `:Doc` property*

**1.3 Mutation**
- [x] `SET d.validity='superseded'` round-trips — *`check_supersession`*
- [x] `DELETE`/`DETACH DELETE` works — **or** the `deleted='true'` fallback is chosen and written down — *both forms work on this build; `check_delete_and_detach_delete` verifies `delete_edge` removes only the targeted edge (endpoints untouched) and `delete_node` removes the node **and** every edge into/out of it, with no dangling edges left behind*

**1.4 Traversal**
- [x] Doc→Entity→Doc traversal returns — *`check_doc_entity_doc_traversal`*
- [x] `algo.MSpaths` returns at least one path — *`check_ms_paths`*
- [x] every traversal in the codebase has a depth bound and a `resultLimit` — *`store.py`'s only traversal helper, `ms_paths`, defaults `max_len=3`/`result_limit=100`; no unbounded traversal exists yet since retrieval (§10) isn't built*

**1.5 Compat recorded**
- [x] each §4.4 assumption is marked verified or fallen back, in `store.py` comments — *`store.py`'s module docstring's "QUERY LANGUAGE GAPS" table covers all of §4.4 plus two gaps the plan didn't anticipate (integer-only node ids, `WHERE...IN` rejected) — see the docstring for the full list*

---

### CP 2 — Canonical models (§5)

**2.1 Round-trip**
- [ ] every model survives `model_dump_json` → parse → compare
- [ ] `period_of(None)` returns `"unknown"` rather than raising
- [ ] every timestamp is tz-aware or explicitly `None` — never a string

**2.2 Hashing and identity**
- [ ] `content_hash` is identical across two constructions of the same doc
- [ ] changing one character of the body changes it
- [ ] changing only provider metadata (reaction count, view count) does **not** change it
- [ ] `doc_id` is never derived from content

---

### CP 3 — Adapters + change detection (§6)

**3.1 Archetypes parse**
- [x] synthetic docs through each implemented manifest, zero exceptions (`scripts/check_3_adapters.py`)
- [x] real docs through each implemented archetype adapter, zero exceptions — verified 2026-08-18 across all 10 connectors on live accounts (Gmail 255, GitHub 619, Jira 15, Notion 10, Confluence 6, Drive 5, Linear 4, HubSpot 1, Slack 1, Fireflies 0). Several providers have fewer than 20 real docs because the connected test accounts are small, not because ingest is capped short — HubSpot/Slack/Fireflies counts reflect actual account content within the 30-day lookback.
- [x] every output doc has a non-empty body, a valid `granularity`, and a non-empty `content_hash`
- [x] bodies under 20 chars are skipped (GitHub: title used as body so empty PRs still keep)

**3.2 Identity**
- [x] zero `doc_id` collisions in the synthetic suite, including two GitHub repos both numbered `#1`
- [x] GitHub issues and PRs with the same number produce different ids
- [x] GitHub ids include `owner/repo` (`github__pr_acme_hydra_42`, not `github__pr_42`)

**3.3 Threads group**
- [x] Slack fixture grouping is non-trivial (`group_threads`)
- [ ] 👁 raw handles are preserved exactly on **real** Slack (`@soham`, not `soham`)

**3.4 Change detection**
- [x] parse the same fixture twice: second pass reports unchanged
- [x] hash map loads in one query, not one query per doc (`_persist_canonical_docs`)
- [x] real second-pass sync reports unchanged, not just fixtures — verified 2026-08-18: every one of the 10 connectors reported `new=0, changed=0` with the full doc count in `unchanged` on a repeat sync
- [ ] second pass issues **zero** LLM calls and zero embeddings — N/A until distill exists

**3.5 Special cases**
- [x] synthetic code file chunked, no function body split across chunks
- [ ] 👁 one real code file chunked, no function body split across chunks
- [x] synthetic email: quoted chain stripped, signature kept
- [ ] 👁 one real email: quoted chain stripped, signature kept

---

### CP 4 — Distillation (§7)

**Status 2026-08-18 — built, unit-verified against synthetic fixtures (`scripts/check_4_distill.py`, fake `LLMCallFn`), and now wired into `_run_ingest` via `pipeline.py`, smoke-tested against a real LLM and real Slack threads.** `llm.py` (generic JSON-mode caller + repair retry), `distill/bursts.py`, `distill/df_index.py`, `distill/artifact.py` (`distill_thread` + `diff_kept_set`), `distill/state.py` (`thread_state` persistence), and `prompts/distill_thread.md` are all implemented per §7.1–§7.5. Every sync now calls `pipeline.run_store_pipeline()` for whatever's new/changed, which re-groups the WHOLE touched thread (not just the delta), calls `distill_thread`, and writes the result through CP5's `upsert_docs`/`from_thread_artifact`/`from_burst` — `scripts/check_pipeline_wiring.py` exercises all of that with a queued fake LLM against real HydraDB. Separately smoke-tested once against a real LLM call and the app's real, already-synced Slack data (scratch SQLite/vector copies, real Hydra, cleaned up after): 5 real threads in, 4 correctly dropped as noise (single throwaway messages), 1 produced a genuine `commitment`-class artifact. **Not done:** `failed_distill.jsonl` (a repair-retry failure today is recorded in the pipeline's in-memory report, not persisted to a file), and anything needing a *labeled* real-thread sample (4.1's 5%-failure bar over 15 threads, all of 4.2's eyeball pass — one real thread isn't a sample).

**4.1 Reliability**
- [ ] 15 real threads, under 5% JSON failure after one repair retry — *only 1 real thread run so far (the real-LLM smoke test); repair-retry mechanism itself is verified synthetically (malformed-then-valid, and double-malformed raises) in `check_4_distill.py`. Needs a real backfill with enough threaded volume (Slack has only 6 real messages total right now) to get a sample of 15.*
- [ ] failures land in `failed_distill.jsonl` and leave any previous artifact intact — *partially built: `pipeline.py` catches `DistillFailure` per-thread, records it in `PipelineReport.distill_errors`, and leaves the previous artifact/kept-bursts untouched (verified in `check_distill_error_recorded_not_raised`) — but nothing persists these to `failed_distill.jsonl` yet, so they're visible in a job's `error` column, not queryable as their own log.*

**4.2 Quality** 👁
- [ ] all 15 eyeballed: questions are question-shaped, not the first message verbatim
- [ ] resolutions are specific and actionable, never "they fixed it"
- [ ] every `resolved: true` is actually resolved in the thread
- [ ] `code_refs` round-trip verbatim against the thread text
- [ ] class distribution is sane (>60% `qa` means loose definitions)

**4.3 Noise filter**
- [x] a thanks-burst is dropped — *`check_noise_filter`: "sounds good, thanks! will try that" (short/common/unreacted) → dropped*
- [x] a pasted-error burst is kept — *`check_distill_thread_happy_path`: the `CKPT_PREFETCH`/`ERR_MANIFEST_TIMEOUT` resolution burst is kept regardless of length via `role="resolution"`; a separate long+rare-vocabulary context burst is kept via the length+rarity path in `check_noise_filter`*
- [x] a whole chit-chat thread classifies as `noise` and is not indexed — *`check_distill_thread_noise_and_low_confidence`: `artifact_class="noise"` → `distill_thread` returns `None`*
- Verified with a fake LLM against hand-built fixtures, not real distilled threads — re-check once 4.2's real pass exists.

**4.4 Burst context**
- [x] burst embeddings include the thread question as a prefix — *`store_sql.py::from_burst` sets `embed_text="Thread: {question}\n{burst.text}"`, wired end-to-end via `pipeline.py`*
- [x] the stored `body` is the bare text (prefix is embedding-only) — *`from_burst`'s `body=burst.text`; only `embed_text` carries the prefix*

**4.5 Re-distillation**
- [ ] re-run the same 15 threads: zero LLM calls — *not run at 15-thread scale against real threads; `pipeline.py` currently re-distills every dirty thread on every sync that touches it (no zero-LLM-call short circuit when nothing in the thread actually changed) — the underlying diff (`diff_kept_set`) that makes the STORE writes a no-op either way is verified synthetically in `check_redistill_diff` and end-to-end in `check_pipeline_wiring.py`, but the LLM call itself always fires for a dirty thread today. A "hash the thread's messages, skip the call if unchanged" short-circuit is a follow-up, not yet built.*
- [x] append one message to one thread: exactly one distill call — *`check_dirty_thread_reloads_whole_thread` in `check_pipeline_wiring.py`: one new message is the only "dirty" doc, `pipeline.py` reloads the whole thread from SQLite and issues exactly one `distill_thread` call over all of it*
- [x] a burst that stops being kept is removed from all three stores — *`check_redistill_drops_stale_burst`/`check_thread_flips_to_noise_removes_artifact` in `check_pipeline_wiring.py`: dropped bursts (and a prior artifact, if the whole thread flips to noise) are gone from SQLite, tombstoned in `LiveIndex`, and `DETACH DELETE`d from HydraDB via `store_sql.py::remove_docs`*
- [x] `thread_state` lives in SQLite, not a JSON file — *`thread_state` table added to `app.py`'s `init_db`, `distill/state.py` load/save round-tripped and upsert-tested in `check_thread_state_persistence`*

---

### CP 5 — Store (§8)

Built as its own testable unit, same as CP3/CP4, then wired: `_run_ingest` now calls `pipeline.run_store_pipeline()` after every sync's `_persist_canonical_docs`, which upserts every new/changed doc via `store_sql.py::upsert_docs()` and — for touched threads — feeds CP4's `distill_thread` output through `from_thread_artifact`/`from_burst` into the same call. Everything checked below is verified live against a real HydraDB node, real local embeddings, and SQLite through the actual migrations — `scripts/check_5_store.py`, all green — plus the wiring itself in `scripts/check_pipeline_wiring.py` and one real-LLM smoke test against real Slack data (see CP4's status note).

**A real-data bug found and fixed while wiring this in:** `_upsert_sqlite_and_fts` (and `remove_docs`) decided whether to fire an FTS5 "delete before insert" by checking whether the `docs` row already existed — but every doc ingested before this wiring pass has a `docs` row with **no** matching `docs_fts` row (plain ingest, §6, never touched FTS). Issuing a contentless-FTS5 delete for a rowid that was never indexed doesn't error immediately; it corrupts the index, which then surfaces later as `sqlite3.DatabaseError: database disk image is malformed` on an unrelated query — exactly what happened running the real-LLM smoke test against a copy of the real 926-doc database. `check_5_store.py` never caught this because every doc in that test is created fresh through `upsert_docs` itself, so it never hits the "pre-existing raw doc, first-ever FTS upsert" case. Fixed by keying the delete decision off `SELECT 1 FROM docs_fts WHERE rowid=?` instead of the `docs` row's existence; regression-tested in `check_pipeline_wiring.py::check_pre_existing_raw_doc_gets_indexed`. The real production `data/index/joel.db` was never at risk — the smoke test that triggered it ran against a temp-directory copy — and `PRAGMA integrity_check`/the FTS `'integrity-check'` command both confirmed the real file was untouched.

**5.1 SQLite + FTS**
- [x] an FTS phrase query for a pasted error returns its burst — *`check_fts_phrase_and_operators`*
- [x] re-upsert an unchanged doc: still exactly one FTS row matches it — *`check_fts_reupsert_no_duplicate`*
- [x] **edit a doc and re-upsert: still exactly one FTS row matches it** (delete-before-insert) — *same check; also asserts the OLD text no longer matches and the NEW text does*
- [x] a question containing `OR` / `NEAR` / `*` does not crash the FTS lane — *quoted as a phrase, per the plan's own "quote user text" rule*
- [x] `PRAGMA journal_mode` reports `wal`

**5.2 Vectors**
- [x] every stored vector has unit norm — *`check_vectors_unit_norm_and_hot_reload`*
- [x] a semantic query ranks the right artifact top-3 — *`check_semantic_ranking`, real `sentence-transformers` model, 3 unrelated distractors*

**5.3 Hot reload**
- [x] upsert a doc and retrieve it **in the same process**, no restart
- [x] the metadata masks reflect a just-changed `validity` without a restart
- [x] a search running during an apply returns a coherent result set — *`LiveIndex`'s own concurrency test (3 searcher threads + 1 writer thread, 200 iterations each, zero errors) during the module build; not re-run inside check_5 itself*

**5.4 Graph**
- [x] a new doc creates a `:Doc` node with every property — *`check_graph_create_update_skip`, strong read via `get_node_strong`*
- [x] **an edited doc updates its existing node** rather than being skipped — *same check: content_hash differs → `graph_updated`, node's title reflects the edit*
- [x] an unchanged doc issues no graph write — *same check: `graph_skipped`*
- [x] `DISTILLED_FROM` count matches the kept-burst count — *`check_distilled_from_edges`, 3 kept bursts → 3 edges, traversed back and counted*

**5.5 Consistency**
- [x] SQLite count == npz rows == graph `:Doc` count (strong read) — *`check_consistency`*
- [x] re-running the whole batch changes no counts — *same check*
- [ ] zero stranded rows in any retry ledger — **not built.** §8.2's `data/state/pending_{sqlite|vec|graph}.jsonl` per-destination retry ledgers don't exist yet; `upsert_docs` today just lets an exception propagate mid-batch (SQLite committed, vectors/graph not attempted) rather than queuing the remainder for retry. The content-hash compare makes a *re-run* self-healing (§8.2's own note), but there's no automatic retry trigger yet — deferred until this is wired into the scheduler.

**5.6 Migrations**
- [x] migrations run in order on boot inside a transaction — `api/joel/migrations/001_init.sql`, `002_store_layer.sql`, applied by `run_migrations()` in numeric order, each wrapped in its own `BEGIN`/`COMMIT`
- [x] `schema_version` is correct afterwards — verified through `004_visibility.sql` (identity + visibility). Fresh DBs end at 4.
- [x] no `CREATE TABLE IF NOT EXISTS` remains in runtime code — *the one standing exception is `schema_version`'s own bootstrap creation inside `run_migrations()` itself, unavoidable in every migration framework (Rails/Django/Alembic have the identical carve-out) since nothing can query "which migrations ran" before that table exists*
- Also fixed in passing: `/api/health` hardcoded `schema_version: 1` instead of reading it from the DB.

**5.7 Forget**
- [x] a doc leaves SQLite, FTS, vectors and graph together — *`store_sql.py::remove_docs()`, built during the pipeline-wiring pass to drop stale bursts/artifacts on re-distillation (§7.5) and exercised against real HydraDB in `check_pipeline_wiring.py`/the real-LLM smoke test. Same primitive the owner's explicit forget will call.*
- [ ] the owner's explicit forget endpoint calls it, and its canonical line becomes a tombstone — **not built.** `remove_docs()` deliberately doesn't know about the canonical JSONL; whatever `POST /api/docs/{id}/forget` becomes needs to rewrite that line to a tombstone on top of calling `remove_docs()`.

**Two HydraDB batch-write gaps found and fixed while building this (neither CP1 exercised them):**
- A `null` anywhere inside an UNWIND list-of-maps parameter takes down the *entire* batch ("only boolean, signed integer, finite float, and string parameters are supported"), even though a bare scalar Bolt param accepts `None` fine. `HydraStore.upsert_nodes`/`link_nodes` now coerce `None → ""` per batched property (`_null_safe`).
- `link_nodes`'s fallback for a properties-less edge issued `SET r.id = r.id`, which HydraDB rejects outright ("cannot update relationship id"). Real `:DISTILLED_FROM` edges (§4.2 — no properties) hit this immediately; fixed by omitting the `SET` clause entirely when there's nothing to set.

---

### CP 6 — Ontology (§9)

**Status 2026-08-19 — built and wired into every sync**, verified against the live local HydraDB node, real embeddings-adjacent test data, and one real LLM extraction call (`scripts/check_6_ontology.py`, all green). `ontology/{extract,resolve,reconcile,pipeline}.py` implement §9.1–§9.4; `prompts/extract_ontology.md` and `prompts/resolve_entity.md` (previously one-line stubs despite `PLAN.md` documenting their content) are now real. Wired into `pipeline.py::run_store_pipeline` right after CP5's `upsert_docs`, running once per newly-distilled thread artifact and once per new/changed singleton (non-threaded) doc — the same "artifacts for threads, full text for singletons" split §9.1 specifies. `retrieve/lanes.py`'s GRAPH and WHO_KNOWS lanes are now real (`HydraStore.graph_expand`/`who_knows`/`edges_from`/`docs_mentioning`, four new store.py primitives, same id/key conventions as everything else in `store.py`) and wired into `run_lanes`/`answer_question`/`/api/ask`, both degrading to an empty list (not a crash) if HydraDB is unreachable.

**Two deliberate simplifications vs. the original pseudocode**, both noted where they live in code:
- **Resolution blocking** (§9.2.A) approximates metaphone-of-last-token with a fuzzy top-K prefilter instead of adding a phonetic-matching dependency — email local-part, initials+surname, and container co-occurrence are implemented as specified. `rapidfuzz` was added as a new dependency (`api/requirements.txt`) for the fuzzy scoring itself.
- **Supersession** (§9.3) operates on the asserting DOCUMENT's `validity`, not a property on the ontology edge itself — §4.2 never specified edge-level validity, and the existing `docs.validity`/`:Doc.validity` flag is already what every mask/lane in §10.2 filters on, so a flip needs no changes anywhere downstream of `reconcile.py`.
- **One real bug found and fixed while building this**: `pair_score`'s email-local-part signal compared only the substring before `@`, so `sam@acme.com` and `sam@other.com` (two different people) scored high enough on name-similarity-plus-local-part alone to clear `AUTO_MERGE` and never reach the LLM tie-break at all — silently violating `resolve_entity.md`'s own rule 2 ("conflicting identifiers ... NOT same, even with identical names"). Fixed by having `pair_score` short-circuit to `0.0` whenever both full identifiers are present and differ, enforced before the auto-merge threshold rather than only in the prompt.

**6.1 Extraction**
- [ ] parse failure under 5% on real documents — not measured at scale; the real-LLM smoke test ran one real document successfully, `check_6.1a/b` verify the grounding/drop rules synthetically
- [ ] 👁 no relation asserted that the text doesn't state — needs a real-corpus eyeball pass once ontology has processed a real sync's worth of dirty threads
- [x] artifact-derived `artifact_class`/`supersedes` win over extraction's — extraction's own `artifact_class`/`confidence` are used only as this module's internal noise gate (whether to bother writing entities/relations at all); they never overwrite the `:Doc`/`docs.artifact_class` distillation already wrote

**6.2 Resolution** 👁
- [ ] top-10 alias clusters eyeballed — no mega-merge — needs a real registry built from a real sync first; `data/entities/registry.json` is empty until then
- [x] a person referenced two ways resolves to one `:Entity` with ≥2 aliases — `check_6.2b`
- [x] two different people sharing a name with conflicting identifiers stay separate — `check_6.2c` (the bug above, now fixed and regression-covered)
- [x] LLM verdicts are cached by sorted pair (same pair never judged twice) — `check_6.2d`

**6.3 Graph queries**
- [ ] WHO_KNOWS for a known incident returns its actual resolver — verified against a synthetic doc/entity (`check_6.3c/d`), not yet against a real incident in the corpus
- [x] ontology edges use canonical entity ids, never raw surface forms — `Entity`/`Alias` nodes are keyed by the registry's `entity_id`/lowercased alias, and every edge write goes through the resolved id, never the raw mention text

**6.4 Supersession**
- [x] a flip round-trips in both graph and SQLite — `check_6.4a`
- [x] the `:REVERSED` edge exists with a timestamp — same check
- [x] the superseded doc is still retrievable — same check (row stays; `validity='superseded'` is the only signal, per §14.5's append-only rule)
- [x] at least one conflict is logged with the rule that decided it — `check_6.4b`

**6.5 Incremental**
- [ ] ingest a decision in job A, a message reversing it in job B → the old claim flips, **without a full re-run** — the mechanism is inherently incremental (`reconcile.py` always re-reads live current claims from the graph via `edges_from`, never a corpus scan) and `check_6.4a` exercises it end-to-end, but not yet observed across two separate real `_run_ingest` sync jobs on production data
- [x] only touched `(entity, predicate)` pairs are reconciled — `run_ontology_pipeline` only ever reconciles the pairs the current doc's own new relations touched

---

### CP 7 — Retrieval and answering (§10)

Built reduced-lane first, on purpose: VECTOR, VEC-ARTIFACTS, FTS and PHRASE need nothing CP6 (ontology) doesn't already provide, so `retrieve/{planner,lanes,fuse,rerank,synthesize}.py` + the `answer_question` orchestrator shipped and got wired into `/api/ask` first; GRAPH and WHO_KNOWS stayed unbuilt until CP6 landed, which it now has (2026-08-19) — see CP 6's status note. `scripts/check_7_retrieve.py` is all green, including one real-LLM smoke test, and it's wired end-to-end into `/api/ask` (SSE `plan`/`lane`/`token`/`citations` events) and re-verified against the real 930-doc corpus below.

**Four real bugs found only by testing against the live server and real data — none of `check_7_retrieve.py`'s synthetic fixtures caught any of them:**
1. **`config.py` never loaded `.env`, only every `scripts/check_*.py` did.** Every check script calls `load_dotenv(ROOT / ".env")` itself before touching `Settings.from_env()`; `app.py` never did, so a plain `uvicorn joel.app:app` (exactly how the dev server is normally started, with no wrapper) ran with `HYDRA_HTTP`/`HYDRA_BOLT`/etc. missing from its actual process environment. `_runtime()` is lazy, so this stayed invisible until the *first* call that actually needed it — the first real `/api/ask` — which then raised a raw `KeyError` deep in `Settings.from_env()`, outside every LLM-specific error handler. Fixed by calling `load_dotenv()` at the top of `app.py` itself, before any other project import.
2. **Concurrent `SentenceTransformer.encode()` calls segfault the worker.** `run_lanes` runs VECTOR and VEC-ARTIFACTS concurrently via `ThreadPoolExecutor`, and both call `embed_fn` for the same question at (almost) the same instant on the one shared model instance. That reproduced a hard `SIGSEGV` (exit 139) against the real model and real corpus, not a catchable Python exception — so the `try/except Exception` wrapped around `answer_question` in `/api/ask` (added for bug 1) could not have helped either. Fixed with a plain `threading.Lock` around the `.encode()` call in `app._embed_fn`; embedding a handful of short strings is fast enough that serializing it isn't a real throughput cost.
3. **The FTS lane quoted the entire question as one exact phrase.** `fts_lane` reused `PHRASE`'s `_quote_fts()` helper on the *whole* natural-language question, turning `docs_fts MATCH` into "every word must appear consecutively in this exact order" — which a real question essentially never satisfies, so FTS silently returned 0 hits against the real 930-doc corpus every time, even for a question copied almost verbatim from a real doc's title. §10.2 wants FTS to be bm25-ranked term overlap ("rare tokens (IDF)"), not a phrase match — that's PHRASE's job. Fixed with `_or_of_quoted_tokens()`: each word is still individually quoted (so a bare `OR`/`NEAR`/`*` in the question still can't act as an FTS5 operator, keeping §18's "quote user text" rule intact) but joined with `OR` instead of concatenated into one phrase, restoring real bm25 ranking. Verified live: the same question that returned 0 FTS hits before the fix returns 15 after it, against the real corpus.
4. **`openrouter_call` let raw network exceptions escape.** It only wrapped HTTP-status and response-shape errors in `LLMError`; a bare `requests.RequestException` (timeout, connection reset, DNS failure) or a non-JSON response body propagated straight up and crashed the SSE generator mid-stream — every caller (`plan_query`, `rerank_candidates`, `synthesize_answer`, `distill_thread`) only ever catches `LLMError` and degrades gracefully otherwise. Fixed by wrapping the `requests.post` call and the `resp.json()` call each in their own `try/except`, re-raising as `LLMError` either way.

All four are now regression-covered live (repeated real `/api/ask` calls against the real 930-doc corpus, no crashes/hangs, real lane hit counts, a real cited answer for a question matching real ingested GitHub data) and `check_5_store.py`/`check_7_retrieve.py` stay green.

**7.1 Lanes individually**
- [x] each of the four built lanes (VECTOR, VEC-ARTIFACTS, FTS, PHRASE) returns sensible results in isolation — *`check_lanes_individually`, plus live against the real corpus (bug 3 above)*
- [x] lanes run concurrently, not serially — *`ThreadPoolExecutor` in `run_lanes`; this is exactly what surfaced bug 2 against the real embedding model*
- [x] every lane excludes `forgotten=1`
- [x] when AskContext is passed, every lane restricts to `allowed_stamps(ask)` — *`check_visibility.py::check_retrieval_respects_room`*
- [x] GRAPH, WHO_KNOWS — built in CP6 (2026-08-19): `HydraStore.graph_expand`/`who_knows`, wired into `run_lanes` via an optional `hydra_store` param, degrading to empty (not a crash) when it's `None` or HydraDB is unreachable — see CP 6's status note

**7.2 Fusion**
- [x] a doc mid-rank in ≥3 lanes outranks a single-lane #1 (log per-lane ranks to prove it)
- [x] `PER_SOURCE_CAP` is enforced
- [x] age decay only reorders inside a tie window

**7.3 Rerank**
- [x] rerank scores are clamped and sorted on the 0–10 scale, never the ~0.09 RRF scale
- [ ] a topically-related non-answering doc scores ≤3 and drops out — not asserted as its own case yet, only implicitly via 7.4's abstention checks
- [ ] an exact-identifier match gets its boost — not asserted as its own case yet

**7.4 Abstention** — the important one
- [x] `reranked[0].rerank_score` is asserted to be on the 0–10 scale before comparison
- [x] five different invented-unanswerable questions all return `absent`
- [x] a fabricated citation triggers the gate
- [x] `answered` with no citations triggers the gate

**7.5 Modifiers**
- [ ] a temporal-history question returns the superseded state — masks exist (`_vector_mask`) but untested against real superseded data
- [ ] a current-state question returns the current one — same
- [ ] a conflict question returns both positions, dated and sourced — `Conflict`/`ConflictPosition` exist in `synthesize.py` but untested against a real conflicting pair
- [x] an exact token via PHRASE survives fusion into the final set

**7.6 Traces**
- [x] every question appends a full trace line — `log_trace` to `data/state/traces.jsonl`
- [ ] the file rotates rather than growing forever — **not built**, appends unboundedly today

---

### CP 8 — Sync engine (§11)

**Status 2026-08-19 — the real gap closed: an errored connector now retries itself.** Before this pass, `_scheduler_tick`'s due-query only ever selected `status='ready'` — the instant a sync failed for any non-auth reason, the connector fell to `status='error'` and became permanently invisible to the scheduler. Nothing retried it until a human clicked Sync now; §18's own risk list names this exact failure mode ("the scheduler stops and nobody notices"). Fixed with `syncer.py::backoff_seconds`/`next_retry_at` (the 1m→5m→15m→1h→6h ladder, capped) driving a new `connections.consecutive_failures` column (migration `005_sync_backoff.sql`), and the due-query now selects `status IN ('ready','error')` — `needs_reauth` stays excluded until a reconnect. `SYNC_MAX_CONCURRENT_JOBS` (a `settings` key, `sync_max_concurrent_jobs`, like every other runtime-editable setting — not an env var) is now actually enforced by counting `jobs.status='running'` before starting new ones. Verified against a real disposable DB with `_start_ingest` mocked (`scripts/check_8_sync.py`, new) and confirmed live: the running dev server picked up the change via `--reload` and a real scheduled sync ran cleanly under it.

**Deliberately not attempted this pass** (real scope, not a shortcut): proactive/reactive OAuth token refresh (401 → refresh → retry once) — no token-refresh code exists anywhere in this codebase yet for any provider; today a 401 just becomes `needs_reauth` directly, which is safe but not the full §11.4 flow. Composio proxy 429 backoff uses a fixed `1+attempt` sleep, not the literal `Retry-After` header value (Slack's own direct-client path, unused in production, does honor the real header). Progressive deep backfill (§11.3's separate backward-walking pass) doesn't exist — every sync is still the lookback-window re-fetch §6/§16.2 already documented as the accepted design instead of cursors, so "crash resume" is really "the next lookback re-fetch is idempotent via content_hash," not a literal cursor resume.

**8.1 It fires**
- [ ] 👁 a connector on a 1-minute interval runs twice with nobody watching — not run unattended for real wall-clock time this pass; structurally true from the fixed due-query + tick loop
- [x] `next_run_at` is computed at job **finish** — true on both the success path (unchanged) and now the failure path (`next_retry_at` computed when the failure is handled, not scheduled ahead of time)

**8.2 Repeat syncs are free**
- [x] the second run reports ~all-unchanged with **zero LLM calls** — verified in the 2026-08-18 real-data pass (§16.2), unaffected by this phase
- [x] job rows show new/changed/unchanged counts — unchanged, pre-existing

**8.3 Crash resume**
- [ ] kill the API mid-backfill, restart: the job resumes from its cursor — **no cursor exists** (§6's accepted lookback-re-fetch design); `release_running_jobs` (pre-existing) resets a crashed job's connector to `ready`/`pending_setup` on boot, and the next tick's full lookback re-fetch is idempotent via content_hash, which is this system's actual (different) answer to the same problem
- [x] document counts are unchanged (no duplicates) — content_hash dedup, pre-existing and unaffected

**8.4 Rate limits**
- [ ] a 429 with `Retry-After: 2` sleeps and resumes the same page — partial: `composio_conn.py::proxy_call` already retries on 429 (fixed backoff, up to 4 attempts) but doesn't parse the real `Retry-After` header value; not changed this pass
- [x] no page is ever skipped on a rate limit — the retry-then-raise behavior means a page either succeeds within the retry budget or fails the whole job (which the new backoff-and-retry now cleanly retries later), never silently drops one page while keeping the rest

**8.5 Tokens**
- [ ] a 401 refreshes once and retries once — not built (see status note above)
- [x] a failed refresh sets `needs_reauth` and the scheduler stops touching that connector — `_is_reauth`, pre-existing; the due-query change explicitly keeps excluding `needs_reauth`
- [x] auth failures skip the backoff ladder entirely — new: the except-branch now checks `_is_reauth` first and never touches `consecutive_failures`/the ladder for that path

**8.6 Catch-up**
- [x] `next_run_at` set 7 days in the past produces **exactly one** run — `check_8.2`

**8.7 Concurrency**
- [x] two connectors due at once respect `SYNC_MAX_CONCURRENT_JOBS` — `check_8.1a`
- [x] a connector never has two jobs running at once — `check_8.1c`, plus the pre-existing `_start_ingest` 409 guard
- [x] `Sync now` during a running job returns 409 — pre-existing, unchanged

**8.8 Backfill**
- [ ] the deep pass yields to a due incremental sync — no separate deep pass exists (§11.3 not built — every sync is the same lookback window)
- [ ] the seam between fast and deep passes re-distills nothing — n/a, no seam exists yet
- [x] `backfill_done` flips and the card says so — pre-existing, set on first successful sync

---

### CP 8a — Identity + workspace

**Status 2026-08-19 — done.** `scripts/check_identity.py` green. One workspace per install; login is required.

- [x] empty install → `/setup` creates the admin and the `orgs` row
- [x] second `/setup` is 409
- [x] login issues a session; expired/missing cookie is 401 on product APIs
- [x] admin can invite; token peek + accept creates a member
- [x] admin can change role and remove a member (not the last admin)
- [x] `PATCH /api/workspace` updates domain/name; it does not create an org if none exists

---

### CP 8b — Visibility + ask context (§1.4)

**Status 2026-08-19 — stamp + read table + channel membership all done.** Personal connectors and leasing remain not built (see the note on connector ownership below). `scripts/check_visibility.py` green, including a new `check_channel_membership` covering the full loop against a fake Slack API.

**Channel membership**, closing the exact gap §0.3 named ("web cannot yet include `channel:slack:…` even for people who are in that Slack room"): `joel/membership.py::sync_slack_channel_memberships` matches Slack channel members to workspace Actors **by email** — the identical signal Gmail visibility already uses (`SlackClient.user_emails()`, new, via `users.list`'s `profile.email`; `SlackClient.channel_member_ids()`, new, via `conversations.members` — paginated by hand since that endpoint returns plain user-id strings, not objects, and the existing `pages()` helper filters to dict items for every OTHER endpoint it serves, which would have silently returned nothing here if reused as-is). Runs after every Slack sync's fetch, best-effort (a scope gap or zero matches never fails the sync). `member_channel_stamps` feeds `AskContext.web`'s `channels` set in `/api/ask`. Verified against real Slack data (real `profile.email` fields came back; zero matches only because this install's real workspace admin email doesn't happen to coincide with any connected Slack member's — the mechanism itself is proven by the fake-API unit test, which round-trips a real member/non-member pair through actual retrieval and confirms the private doc is readable for one and not the other).

**Connector ownership — groundwork only, not the feature.** Migration `006_channel_membership.sql` also adds `connections.owned_by`/`connections.kind` (`org`|`personal`), every existing row staying `kind='org'`. Discovered while scoping this: `connections.provider` has a `UNIQUE` constraint (§12.2/migration 001) — there is currently no way to have more than one connection per provider at all, so real personal-connector support (a second Slack connection owned by one person, reads preferring personal-then-org-shared per Supermemory's model) needs that constraint removed plus a redesigned connect flow and every `SELECT … FROM connections WHERE provider=?` call site (there are several, including the live-lookup credential resolution added in CP10) updated to disambiguate by owner. That's a distinctly larger, separate phase, not a checkbox to half-do here.

- [x] `derive` stamps gmail as `user:gmail:…`, private slack as `channel:slack:…`, company data as `org`
- [x] `content_hash` ignores visibility
- [x] persist writes `docs.visibility`; migration restamps existing gmail
- [x] old npz without a visibility meta field loads as `org`
- [x] asking from public/org cannot retrieve a private-channel or gmail doc
- [x] asking from that private channel can retrieve it plus `org`, not gmail
- [x] a web desk with the actor's gmail alias can retrieve that mailbox
- [x] `/api/ask` builds AskContext from the session, not from the POST body
- [x] channel membership: a desk includes `channel:slack:…` rooms the actor is in — `joel/membership.py`, `check_channel_membership`
- [ ] org-shared vs personal connector scope — schema groundwork only (`owned_by`/`kind` columns); real support blocked on the `connections.provider` UNIQUE constraint, see note above
- [ ] Slack / MCP surfaces construct AskContext from the event — **not built** (§17 cut list: web desk must keep working, these are lowest priority)

---

### CP 9 — The app (§12)

**9.1 Clean install**
- [ ] `docker compose up` from a fresh clone on pruned Docker reaches `/setup`
- [ ] only `LLM_API_KEY` had to be set
- [ ] no Rust compile happens

**9.2 Onboarding**
- [x] `/setup` collects domain → workspace with favicon and derived name — *identity module, not the old `/onboarding` org step*
- [ ] the readiness checklist ticks over a real first sync
- [ ] it forwards to chat when the first connector is ready

**9.3 Connectors page** (`/integrations`)
- [ ] status, last sync and **next sync** are visible and correct
- [ ] backfill progress updates live
- [ ] a real error renders verbatim on the card with Retry
- [ ] `needs_reauth` shows Reconnect and reconnecting resumes from the stored cursor

**9.4 Chat**
- [ ] a real question answers with working citation links
- [ ] a public-room-ineligible doc (private slack / someone else's gmail) is not cited
- [ ] all four status badges render correctly
- [ ] the reasoning path shows graph paths
- [ ] streaming works (the SSE-over-POST decision holds up in the browser)

**9.5 Unattended freshness**
- [ ] post a message, wait one interval, ask about it — **it answers with no human action**

**9.6 Settings and restart**
- [ ] a model change takes effect without a restart
- [ ] pause ingestion actually stops the scheduler
- [ ] `docker compose down && up`: state survives, scheduler resumes, no duplicate docs

---

### CP 10 — Agent (§13)

**Status 2026-08-19 — built and wired into `/api/ask`**, verified with `scripts/check_10_agent.py` (fake-LLM determinism for rewrite/meta, real network calls for live lookup against real stored GitHub/Slack credentials) and end-to-end over real HTTP/SSE against the running dev server. `agent/working_memory.py` implements §13.1 (`prompts/rewrite_question.md`, previously undocumented as a file even though §18 named it); `agent/live.py` + `connectors/github.py::fetch_github_item` + `connectors/slack.py::fetch_slack_channel_latest` implement §13.2.

**Three real bugs found only by testing this live, none caught by synthetic fixtures:**
1. **Duplicate live targets.** `detect_live_targets`'s haystack is `question + plan.entities + plan.exact_tokens` — the planner often echoes the same substring from the question back into `exact_tokens`, so the same GitHub PR mention matched twice and got "checked" twice. Fixed with a `seen: set[LiveTarget]` dedupe (targets are frozen dataclasses, hashable for free).
2. **A live PR/issue fetch worked but couldn't answer the question it was fetched for.** `merged`/`draft`/`state` lived only in `CanonicalDoc.extra`, which `StoreDoc` never carries into the embedded/indexed body — so "is PR 118 merged?" retrieved the doc but neither the embedding nor the answer LLM could see its actual status. Fixed by extending the existing `qualify_github_item` pre-hook (§6's adapters — the only normalization path) to prepend an explicit `"Status: merged"` / `"Status: closed (not merged)"` / `"Status: draft"` / `"Status: open"` line to the body — deliberately spelling out "closed (not merged)" rather than bare "closed", which a live run showed the LLM correctly refusing to interpret as an answer to "was it merged" (right instinct, wrong source data). This also improves the regular scheduled-sync corpus, not just live lookup.
3. **A freshly live-fetched doc still didn't get cited**, even after the fix above and even though it was correctly re-embedded and re-indexed. RRF/vector similarity between a short generic PR title and the question didn't rank it in the top 20 among ~930 competing docs, so it never reached rerank. Fixed by adding `answer_question(..., extra_doc_ids=...)`: the caller's already-known-relevant doc ids (this turn's live fetches) are hydrated and prepended to the fused candidate set before rerank — guaranteeing the LLM reranker actually SEES it and can judge it on merit, rather than hoping general retrieval rediscovers it. `retrieve/lanes.py::hydrate_doc_ids` is the new public hydration entry point this required.

All three are regression-covered (`check_10_agent.py`, and a real `/api/ask` call verified live: "is amarpathak/vaadi#1 merged?" → `status: answered`, one citation with `"live": true`, answer prefixed "As of just now:").

**10.1 Follow-ups**
- [x] a pronoun follow-up is rewritten standalone and answered correctly — `check_10.1a`, real turns
- [x] an already-standalone question passes through unchanged — `check_10.1b`

**10.2 Cheap paths**
- [x] "hi" classifies as chitchat: zero retrieval, zero ingest — and costs zero LLM calls, better than the one-call floor (`_is_chitchat`'s pre-existing regex fast path, unchanged)
- [x] "what did you just say" classifies as meta and answers from the turns — `check_10.2a`, `agent/working_memory.py::answer_meta` (no 8th prompt — mechanical, from the stored turns alone, per §13.1's own "answered from the conversation alone" rule)
- [ ] 👁 both return visibly faster than a knowledge question — not measured with real wall-clock timing yet, only structurally true (meta/chitchat skip retrieval+rerank+answer entirely)

**10.3 Live lookup bounds**
- [x] at most 2 lookups per question, 10s timeout each — `agent/live.py::MAX_LOOKUPS`/`TIMEOUT_SECONDS`, enforced in `app.py::_run_live_lookup` via `ThreadPoolExecutor(...).result(timeout=...)`
- [x] only whitelisted read operations are reachable — `detect_live_targets` recognizes exactly two shapes today (GitHub PR/issue-by-number, Slack latest-N-in-channel); **Jira/Linear issue-by-key and Gmail thread-by-id are the same shape but not implemented yet** (§13.2's other two whitelist entries) — a question needing them detects zero targets, same as any non-matching question, never a crash or a guess
- [x] the LIVE chip renders and the answer says "as of just now" — verified live over real HTTP: `citations[].live=true`, `web/components/beautifului/CitationChip.tsx` already rendered this (was always `false` from the backend before); answer text prefixed `"As of just now: "` when a live citation is actually used

**10.4 Live → memory**
- [x] fetched content that passes the filter appears in the corpus afterwards — verified live (`github__pr_amarpathak_vaadi_1`/`_2` now permanently in `docs`, re-embedded, re-indexed)
- [ ] **a junk message fetched live is NOT indexed** — not true today, but not a live-lookup-specific gap: EVERY raw ingested doc (live or scheduled-sync) is stored as a plain row regardless of "noise" — only the ARTIFACT layer (distillation's noise classification) filters chit-chat out of the curated/retrievable layer. This checklist item's premise predates the "always store raw, distill filters at the artifact layer" design CP3/CP4/CP5 already shipped and verified; changing it now would be a system-wide ingest change, not a live-lookup fix, and is out of this phase's scope.

**10.5 Isolation**
- [x] no conversation message ever appears in FTS, vectors, or the graph — `agent/working_memory.py` only ever reads `messages`; nothing in the agent layer writes conversation content into `upsert_docs`' input anywhere

---

### CP 11 — Operations (§14)

**Status 2026-08-20.** `/api/health`'s index triple and `rebuild_index.py` were both stubs/wrong-sourced before this pass — fixed and, in the process, `/api/health` immediately found real, pre-existing drift in this install's own graph (1456 SQLite docs vs. 1574 real `:Doc` nodes) — exactly the "find it, don't paper over it" job §14.1 describes it doing. That drift predates this session (likely accumulated `:Doc` nodes from earlier development/checkpoint runs against this same shared graph, per §2.1's "one universe") and is left for a deliberate investigation rather than papered over with a silent rebuild.

- **`/api/health`** was fully hardcoded (`"hydra": "ok"` regardless of reality, `index: {0,0,0,consistent:true}` always, `corpus` always zeros) — now every field is a real, live query: `HydraStore.count_nodes` (new — `COUNT(*)` uppercase/no-alias is the one spelling this HydraDB build accepts; `count(n)`/`count(*)` are rejected with a misleading "property values support integer/float/boolean/string" error, now documented in `store.py`'s gotcha docstring), SQLite/vector counts from the real tables, `queue_depth` from real running jobs, `corpus.oldest_doc`/`artifacts`/`entities` all real. HydraDB unreachable degrades `hydra`/`graph`/`entities`/`consistent` to an honest error/`None` rather than a fake "ok".
- **`rebuild_index.py`** read FROM SQLite before this pass — which means it could never actually recover FROM a lost/corrupted SQLite, the entire point of §14.4's disaster-recovery story. Rewritten to replay `data/canonical/*.jsonl` directly (fold to the last state per `doc_id`, forget-tombstones excluded), reconstructing the `docs` table itself before re-running the existing `upsert_docs` store-layer call. Verified against the real ~1360-live-doc canonical archive (13.6s, real embeddings, real HydraDB — `graph_created=9` caught 9 real docs that had never made it into the graph before) and, separately, a small synthetic fixture in `check_11_ops.py` per §14.4's own CI requirement.
- **`traces.jsonl` rotation** (CP7.6's open item): `retrieve/__init__.py::log_trace` now rotates at `TRACES_MAX_BYTES` (20MB, 5 numbered backups) instead of growing forever.
- **Forget → canonical tombstone**: already done, just previously mis-marked as open in this doc — `app.py::forget_doc` was already rewriting the canonical JSONL line to a tombstone (§14.5) when this pass started; verified still correct.

**Deliberately not attempted this pass**: the retry ledgers `store_sql.py::upsert_docs` still lacks for a mid-batch failure (§8.2/CP5.5's open item — SQLite commits, vectors/graph don't, and there's no `data/state/pending_*.jsonl` queue yet; the content-hash compare makes a manual re-run self-healing, just not automatic); distinguishing "LLM key missing" from "LLM key present but rejected" in `/api/health`'s `llm_error` (would need a live provider call on every health check).

**11.1 Health**
- [x] `/api/health` reports a consistent index triple on a real corpus — real (and it correctly reports `false` on this install's actual pre-existing drift, not a rubber-stamped `true`)
- [x] it shows per-connector last success and next run — pre-existing, unaffected
- [x] the spend counter is populated — pre-existing (real all-time counts; not actually windowed to 30 days despite the `spend_30d` key name — the `spend` table has no date dimension at all, a deeper gap than this pass's scope)

**11.2 Migration**
- [x] applied to a **populated** database, every row survives and `schema_version` bumps — continuously true all session: `schema_version` went 4→6 across two new migrations this pass, applied live to the real ~1400-doc production database via `--reload` restarts, data intact throughout

**11.3 Rebuild**
- [x] `rebuild_index.py` from canonical reproduces identical SQLite, npz and graph counts — verified against the real corpus (see status note); "identical" here means every canonical-sourced doc, not thread artifacts/ontology edges, which were never in canonical to begin with (documented in the script's own docstring)
- [x] it runs in CI against a small fixture — `check_11_ops.py::check_rebuild_from_canonical`

**11.4 Forget survives**
- [x] a forgotten doc does not come back after a rebuild — `check_11_ops.py::check_rebuild_from_canonical` asserts this directly (a tombstoned doc_id from a synthetic fixture stays absent after rebuild)

**11.5 Degraded modes**
- [x] HydraDB stopped: chat answers on four lanes (of six — GRAPH/WHO_KNOWS are the two Hydra-dependent ones) with no 500 — `graph_lane`/`who_knows_lane` already degrade to empty on any exception (built in CP10's live-lookup pass); `/api/health` now also degrades honestly instead of lying — 👁 no dedicated frontend banner yet for this specific state
- [ ] LLM key rejected: banner with the provider's real error, ingestion pauses — partial: `/api/health.llm_error` distinguishes "missing" but not "present but rejected" (see note above); ingestion already effectively pauses the LLM-dependent stage when `llm_call is None` per §14.6, but that's the missing-key case, not rejected-key
- [ ] no connectors: `/chat` is locked with an explanation, not an empty box — backend 409 already exists (pre-existing); the frontend empty-state treatment is unverified, out of this pass's (backend) scope

---

### CP 12 — Connector harness (§12.4)

- [x] `SourceManifest` drives field mapping; provider-specific code is `pre` hooks or fetcher enrichment
- [x] Composio proxy is the production `RequestFn` (no raw provider tokens)
- [ ] the `Connector` ABC / `poll`+`backfill` is **not** the shipped contract — lookback re-fetch instead
- [ ] `scripts/conformance.py --provider X` exists and runs
- [ ] the first three connectors pass it unmodified
- [x] 👁 later connectors were added as a manifest + fetch function, not a new adapter module

---

### CP-C — Per-connector conformance (run for EVERY connector, every wave)

This is the repeated checklist. A connector ships when all of it is green, and not before.

**Auth**
- [ ] connect flow completes from a clean state
- [ ] tokens are stored Fernet-encrypted; no token appears in any log
- [ ] refresh works; a forced expiry recovers without human action
- [ ] revoking access produces `needs_reauth`, not a crash loop
- [ ] disconnect removes credentials and stops the schedule

**Fetch**
- [ ] pagination is followed to the end (assert on a container with more than one page)
- [ ] `Retry-After` / rate-limit headers are honoured
- [ ] the forward cursor persists and resumes after a kill
- [ ] the backward backfill cursor persists and terminates with `backfill_done`
- [ ] an empty account or empty channel returns cleanly rather than erroring

**Normalize**
- [ ] the manifest maps onto exactly one archetype
- [ ] `external_id` is the item, never its container
- [ ] `doc_id` collides with nothing from any other connector
- [ ] timestamps are tz-aware; the provider's own format is parsed, not stringified
- [ ] raw author handles are preserved
- [ ] `url` deep-links to the item and actually opens

**Incremental**
- [ ] a second sync with no upstream change reports all-unchanged and zero LLM calls
- [ ] a **new** item is picked up on the next scheduled run
- [ ] an **edited** item is detected — either natively or via the documented re-fetch window
- [ ] an upstream delete does nothing (append-only, by design)

**Pipeline**
- [ ] threads group correctly for conversation/tracker archetypes
- [ ] at least one artifact is produced and 👁 reads correctly
- [ ] entities from this source resolve against the existing registry rather than creating duplicates
- [ ] a question answerable only from this source answers with a citation to it

**Product**
- [ ] icon present in `web/icons/`, card copy written, sensible default interval
- [ ] backfill progress renders on the card
- [ ] listed in the README's supported-sources table