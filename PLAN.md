# joel — Build Spec

**What:** a self-hostable company brain. Connect your tools, joel distills them into a knowledge graph on HydraDB, and you chat with your org's memory — with citations, a decision-reversal ledger, and honest "not in the data" answers.
**Hackathon:** Hack Hydra, Track 01 (Enterprise Context + Ontology). Deadline 11:59 PM PT Aug 20 = **12:29 PM IST Aug 21**.
**Today:** Aug 16. Solo build.

---

## 0. How to use this document

Execute top-to-bottom. Every phase ends in a **Checkpoint** (`scripts/check_N_*.py`); non-zero exit = stop and fix. Commit per checkpoint. `[CUT]` = droppable, order in §17.

Each risky step carries a guardrail table — **the ❌ column is a mistake an implementing agent will plausibly make, and it usually fails silently** (wrong-case property values match nothing without erroring, a listening port isn't a working node, a fabricated citation looks like a real one). Treat ❌ rows as assertions to encode in checkpoints.

Hard constraints: no commits before Aug 12 · public repo, MIT `LICENSE` · README explains HydraDB usage · demo video ≤ 3:00 · Google Form before the deadline.

---

## 1. Product definition

### 1.1 What joel is (and deliberately isn't)

joel is a **simple web app**, single-tenant, self-hosted, no login:

| Page | Purpose |
|---|---|
| `/onboarding` | enter your **company domain URL** → org created → pick a data path (connect your tools / benchmark corpus) → watch ingestion → ready |
| `/connectors` | connect/disconnect tools, per-connector ingestion status, **Sync now** |
| `/chat` | the chatbot: conversations sidebar, status-badged answers (✅🟡⚠️🚫), citations, reasoning path |
| `/settings` | LLM keys + models, Composio key, custom OAuth creds, embedding model |
| `/profile` | display name, org (domain, logo, name), danger zone (wipe org) |

**Deliberately NOT in v1:** Slack/bot surfaces · schedules, routines, digests, proactive triggers · multi-tenant/auth/billing · graph-explorer page (the reasoning path in chat is the graph exhibit). Anything not in the table above does not get built.

### 1.2 "Ready to use" — defined precisely

Per-connector state machine: `pending_auth → backfilling (n/m docs) → distilling (k threads) → linking (entity resolution + ontology) → ready | error(msg)`. Each state renders on the connector card with counts.

Org readiness: **READY ⇔ every active connector is `ready` AND index counts are consistent (SQLite rows == vector rows == graph `:Doc` count) AND the ontology pass has run since the last ingested doc.** The onboarding screen shows this as a live checklist (`fetched ✓ · distilled ✓ · people resolved ✓ · graph linked ✓ · indexes consistent ✓`).

Chat gating: hard-gated until the **first** connector reaches `ready`; after that, chat is open with a banner ("still ingesting — answers may be incomplete") whenever any connector is mid-sync.

### 1.3 Design lineage (context for the agent, one paragraph each)

**Sentra's three layers** — factual memory (what/where/who) = doc rows + graph doc-nodes; interaction memory (why: decisions, commitments, objections) = the ontology edges in HydraDB; action memory is out of v1 scope.

**Cerebras' knowledge-base pipeline** — the ingestion/retrieval philosophy this build copies: *distill threads into one structured artifact before embedding* (chatter informs the artifact, then vanishes); retrieval = parallel lists (vector, full-text, artifacts, graph) fused with **RRF k=60** then LLM-reranked; four signals each catch what the others miss (full-text = exact tokens, embedding = paraphrase, IDF = rare beats filler, age decay = newer wins ties).

**Build vs. free:** local HydraDB (the hackathon's open-source repo) is an OpenCypher graph database — Bolt + HTTP, snapshot-consistent, `algo.MSpaths` path procedures. It does NOT ship embeddings, BM25, or ingestion. So: **HydraDB owns the graph** (ontology, reversal ledger, WHO_KNOWS, multi-hop — the load-bearing "Best Use of HydraDB"), SQLite FTS5 owns exact/BM25, a local sentence-transformers model owns vectors. Everything is local; there are no usage limits anywhere.

---

## 2. Architecture

```
        Connectors (demo | benchmark | composio | custom-oauth)
                              │  raw docs
                              ▼
        ┌──────────────────────────────────────────┐
        │ Adapters: raw → CanonicalDoc (+threads)  │  §6
        └──────────────────┬───────────────────────┘
                           ▼
        ┌──────────────────────────────────────────┐
        │ Distillation: bursts → filter → LLM →    │  §7
        │ ThreadArtifact (1/thread)                │
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
        │ reconcile conflicts → Cypher edges       │
        └──────────────────┬───────────────────────┘
                           ▼
  QUESTION → planner → [VECTOR|VEC-ART|FTS|PHRASE|GRAPH|WHO_KNOWS]   §10
             → RRF(k=60) → rerank → answer|partial|conflicted|absent
                           ▼
        joel-api (FastAPI: orgs, connectors, sync, conversations,
                  /ask SSE, settings)  →  joel-web (Next.js, 5 pages)   §12
```

### 2.1 Data placement — decide once

| Store | Owns | Never holds |
|---|---|---|
| **HydraDB** (`/store` volume) | `:Doc` nodes (metadata only), `:Entity`/`:Alias`, every ontology + structural edge | document bodies (graph stays traversal-fast) |
| **SQLite** (`data/index/{dataset}.db`) | bodies, metadata columns, FTS5, `orgs/connections/conversations/messages/settings` tables | graph structure |
| **vectors** (`data/index/{dataset}.npz`) | doc_id → normalized embedding | anything else |

Two universes, switched by `JOEL_DATASET=main|bench`: separate HydraDB store dirs, separate db/npz files. Never mix — real-org data would silently change benchmark numbers.

| ✅ DO | ❌ DON'T |
|---|---|
| One `store.upsert_docs(rows)` fanning out to all three (SQLite → vectors → graph), per-destination retry ledgers | Let phases write to stores directly — three-way drift is unfindable |
| doc_id is the join key, identical across all three | Let SQLite rowids or graph-internal ids leak into app code |

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
│       ├── config.py hydra.py store.py models.py
│       ├── adapters/   base slack gmail linear jira confluence gdrive
│       │               github code_chunk hubspot fireflies
│       ├── distill/    bursts.py artifact.py df_index.py
│       ├── ontology/   extract.py resolve.py reconcile.py
│       ├── retrieve/   planner.py lanes.py fuse.py rerank.py synthesize.py
│       ├── connectors/ base.py benchmark.py composio_conn.py oauth.py
│       ├── syncer.py routes.py
│       └── prompts/    *.md (6 — §18)
├── web/                      # Next.js app (Dockerfile)
├── scripts/ check_{0..10}_*.py rebuild_index.py
└── eval/ run_eval.py score.py ablate.py results/
```

```bash
# .env.example
JOEL_DATASET=main                        # main | bench
HYDRA_HTTP=http://hydradb:8443           # 127.0.0.1 outside compose
HYDRA_BOLT=neo4j://hydradb:7687
HYDRA_TOKEN=local-development-token-32-bytes
HYDRA_NAMESPACE=default
HYDRA_CELL=cell-0
EMBED_MODEL=BAAI/bge-small-en-v1.5       # local CPU, 384-dim, zero cost/limits
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=                             # the ONLY key a judge must supply
LLM_MODEL_DISTILL=anthropic/claude-sonnet-4.5
LLM_MODEL_EXTRACT=anthropic/claude-sonnet-4.5
LLM_MODEL_ANSWER=anthropic/claude-sonnet-4.5
LLM_MODEL_RESOLVE=anthropic/claude-haiku-4.5
LLM_MODEL_RERANK=anthropic/claude-haiku-4.5
COMPOSIO_API_KEY=                        # optional: real-tool connectors
JOEL_SECRET=                             # generated on first boot; encrypts oauth tokens
```

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

### ✅ Checkpoint 0 — `check_0_env.py`
`just smoke` passed · curl round-trip of the FOLLOWS edge · Bolt `RETURN 1` · one LLM call per model alias (5) · embedding model loads and encodes locally.

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
| `:DECIDED :OWNS :COMMITTED_TO :OBJECTED_TO :RESOLVED :ASSIGNED_TO :DEPENDS_ON :BLOCKS :APPROVED :ESCALATED :AFFECTS` | Entity → Entity | `doc_id, ctx (≤200), ts` | the ontology — **the Best-Use-of-HydraDB exhibit** |

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
| `MERGE` | ids are deterministic → client-side create-if-absent: `data/state/written.json` ledger, `CREATE` only new; "upsert" = `MATCH … SET` |
| `SET` | delete-and-recreate helper (re-create edges too) |
| relationship properties | reify: `(:Claim {predicate, doc_id, ctx, ts})` with `:FROM`/`:TO` |
| `IN` lists / `UNWIND` params | chunk client-side into OR-chains |

| ✅ DO | ❌ DON'T |
|---|---|
| Enforce id uniqueness in `store.py` | Assume the DB dedupes — double-ingest = duplicate nodes = double-counted retrieval votes |
| Lowercase/slug every filterable property at write; matching is exact | Write `Engineering`, match `engineering`, get zero rows and no error |
| Bound traversals (`[*..3]`, `resultLimit`) | Unbounded expansion on a broad entity mid-demo |

### ✅ Checkpoint 1 — `check_1_graph_model.py`
Probe Doc + 2 Entities + Alias + `DECIDED` edge written, **strong-read** back · property-filtered MATCH hits on right values and misses on wrong ones for every property · `SET validity` round-trips · Doc→Entity→Doc traversal works · `algo.MSpaths` returns a path · every §4.4 assumption verified, fallbacks noted in `store.py` comments.

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

**doc_id rules:** `{source_type}__{slug(external_id)}`, slug `[a-z0-9_.-]` · artifacts `art__{source_type}__{slug(thread_id)}` · GitHub prefixes by item type (`github__issue_123` vs `github__pr_123` — numbers collide) · code `github__code_{slug(path)}_c{i}` · **never content-hashed** (content changes on supersession/re-distill; a content hash orphans everything).

### ✅ Checkpoint 2 — `check_2_normalize.py`
Parse `questions.jsonl` (count + category distribution) · every gold `document_id` exists in the downloaded slices · build `dev_manifest.json` = gold docs + ~150 distractors (**backwards from the questions**, never random) · thread-grouping table per source — Slack showing ~0 threads means your `thread_id` mapping is broken; fix before §7.

---

## 6. Phase 3 — Source adapters

One adapter = `raw dict → CanonicalDoc | list[CanonicalDoc]`; thread-emitting adapters also return `dict[thread_id, list[CanonicalDoc]]` for distillation. A thread-like container = anything with `thread_id` and ≥3 items: Slack thread, email thread, ticket+comments, PR+reviews, meeting.

**Universal rules:**

| ✅ DO | ❌ DON'T |
|---|---|
| Inspect one real corpus doc per source **before coding** (10 min each) — mappings below are target shapes, field names drift | Code all nine blind, debug during ingest |
| `external_id` = the individual item's id | Use the container (channel/project/space) id — relations then point at the container |
| Skip bodies < 20 chars | Index stubs — ranking noise, real cost |
| Preserve raw handles exactly (`@soham`, `S. Ratnaparkhi`) | Normalize names in adapters — destroys the entity-resolution signal |
| tz-aware datetimes (`fromtimestamp(x, timezone.utc)`, `fromisoformat`) | Pass raw strings/floats — burst gaps + `period_of` break quietly |
| Keep genuine near-duplicates (the benchmark plants them; resolving them is the task) | "Helpfully" dedupe near-matches — only byte-identical dupes drop |

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
- **Linear / Jira:** ticket + each comment as separate docs; comments carry `parent_id = ticket key`, `thread_id = ticket key`. Jira `external_id` = the **issue key** (`AUTH-123`) — questions cite keys, never the numeric internal id. `status/priority/assignee` live in `extra` (they churn); only distiller-set `resolved` is a hot property. Container = project/team.
- **Confluence:** HTML → markdown with a real parser (`markdownify`/bs4), preserve headings + code blocks. Keep page hierarchy via `parent_id`. Infer `doc_type` (runbook|spec|policy|notes) into `extra` — feeds conflict precedence (§9.4). Split >3K-token pages on H2 boundaries into `_s{i}` parts with `LINKED_TO` between.
- **Google Drive:** corpus ships extracted text (expected) → normal doc. If binary, extract locally (pypdf/mammoth) — nothing manages parsing for you.
- **GitHub:** issues/PRs as docs (`github__issue_N` / `github__pr_N`), review comments as comment docs (`parent_id` = PR), PR+reviews = a thread grouping. **Code files: language-aware chunks, never split a function body** — an oversized function becomes one oversized chunk, never a bisected one:
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

### ✅ Checkpoint 3 — `check_3_adapters.py`
20 real docs per adapter parse clean · **zero doc_id collisions corpus-wide** (catches the GitHub prefix rule) · every doc: body, valid granularity, tz-aware-or-None timestamp · stats table per source · thread groupings for ≥4 sources · one real code file chunked, no split functions (eyeball) · Gmail probe: quotes stripped, signature kept.

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

Artifact (skip if class=`noise` or confidence < 0.3): `doc_id=artifact_id` · `title=question[:300]` · `body=normalized_body()` · `granularity="artifact"` · `resolved` · edges `DISTILLED_FROM` → each kept burst, `LINKED_TO` → thread root. Kept bursts: `granularity="burst"`, `REPLY_TO` → root. Dropped bursts: **never stored** — persist per-thread kept-sets to `data/state/kept.json` (re-syncs must delete bursts that stop being kept, in all three stores).

| ✅ DO | ❌ DON'T |
|---|---|
| Iterate the prompt on 15 real dev threads before scaling | Scale to thousands on the first draft |
| One JSON-repair retry, then `failed_distill.jsonl` | Retry-loop malformed outputs |
| Feed the distiller the WHOLE thread including noise (rule 3 needs to see it) | Pre-filter messages before distillation |
| Spot-check every `resolved:true` in dev | Trust `resolved` — invented closure is the signature hallucination |

### ✅ Checkpoint 4 — `check_4_distill.py`
15 real threads, <5% JSON failure after one repair · eyeball all 15 (specific resolutions, question-shaped questions) · noise assertion: a thanks-burst dropped AND a pasted-error burst kept · `code_refs` verbatim round-trip against thread text · class distribution sane (>60% `qa` = loose definitions; confident `noise` = rule 8 broken).

---

## 8. Phase 5 — Store layer

```python
class Store:
    def __init__(self, dataset):
        self.db = sqlite3.connect(f"data/index/{dataset}.db")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY, title TEXT, body TEXT,
          source_type TEXT, container TEXT, granularity TEXT, artifact_class TEXT,
          validity TEXT, resolved TEXT, ts TEXT, period TEXT, url TEXT,
          author_raw TEXT, thread_id TEXT, extra JSON);
        CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(id UNINDEXED, title, body, content='');
        """)
        self.vec_path = f"data/index/{dataset}.npz"
        self.model = SentenceTransformer(os.environ["EMBED_MODEL"])
        self.hydra = Hydra()
    def upsert_docs(self, docs):
        # 1) SQLite INSERT OR REPLACE + FTS rows
        # 2) embed title+"\n"+body[:2000] (artifacts: normalized_body), batches of 256,
        #    NORMALIZE at write; id->row map persisted to .npz
        # 3) HydraDB: UNWIND-batched :Doc CREATEs (skip ids in data/state/written.json —
        #    the client-side MERGE), then structural edges
        # per-destination retry ledgers: data/state/pending_{sqlite|vec|graph}.jsonl
```

Vector search = brute-force dot product over the npz matrix (normalized at write) — ≤50K×384 is milliseconds; no FAISS until >200K rows. bge-small on CPU ≈ 1–2K docs/min.

| ✅ DO | ❌ DON'T |
|---|---|
| FTS5 contentless (`content=''`) + explicit rowid↔id map | Duplicate bodies into the FTS shadow table |
| Quote user text in FTS queries (`"…"`) | Raw questions into `MATCH` — FTS5 operators (`OR NEAR *`) in a question crash it |
| `scripts/rebuild_index.py` regenerates SQLite+npz from `canonical/*.jsonl` | Treat indexes as the source of truth — canonical JSONL is |
| Per-destination retries | All-or-nothing batches stranding good rows |

### ✅ Checkpoint 5 — `check_5_store.py`
Dev set through `upsert_docs`, zero stranded rows in any ledger · SQLite count == npz rows == `:Doc` count (strong read) · FTS phrase-query of a pasted error returns its kept burst · vector query "why does restore stall" ranks the artifact top-3 · `DISTILLED_FROM` count matches kept bursts · re-run changes no counts (idempotence).

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
    "type":"PERSON|TEAM|PROJECT|CUSTOMER|SERVICE|POLICY|METRIC|DECISION|COMMITMENT|OBJECTION|INCIDENT|DOCUMENT",
    "identifier":"<email/handle/ticket-key if present, else null>"}],
  "relations": [{"source":"<key>","target":"<key>","predicate":"<UPPER_SNAKE>",
    "context":"<one sentence, <=200 chars, grounded in the text>",
    "temporal_details":"<'since 2021'|'2026-05-20'|null>"}],
  "artifact_class": "decision|commitment|objection|status_update|incident|question|reference|noise",
  "supersedes": "<verbatim quote of the prior statement this overturns, or null>",
  "confidence": 0.0-1.0
}

## Rules
1. GROUNDING: every entity/relation traces to explicit text. Never infer a relation
   the document does not state or clearly imply.
2. SURFACE FORMS exactly as written ("@soham", "S. Ratnaparkhi", "Sam"). Do NOT
   normalize or merge — a later stage does that.
3. PREDICATES — prefer: OWNS, DECIDED, COMMITTED_TO, OBJECTED_TO, DEPENDS_ON, BLOCKS,
   ASSIGNED_TO, REPORTED, ESCALATED, APPROVED, REVERSED, RESOLVED, MENTIONS, AFFECTS.
4. CONDITIONALS: "ship Friday if legal signs off" = COMMITMENT + DEPENDS_ON, not DECISION.
5. SUPERSEDES only on explicit overturning; quote this document's reference to it.
6. Ambiguity lowers confidence; do not guess.
7. Limits: <=25 entities, <=40 relations.

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

Loser: `SET validity='superseded'` in the graph **and** SQLite (both lanes filter on it) + `(:Doc)-[:REVERSED {ts}]->(:Doc)`. Keep superseded rows — "what was the plan before it changed" is a benchmark category. Log every reconciliation decision.

Canonicalize entity names through the registry **before** writing ontology edges — raw surface forms as nodes = two Sams = dead multi-hop.

### ✅ Checkpoint 6 — `check_6_ontology.py`
Extraction parse-fail <5% · eyeball top-10 alias clusters (one bad mega-merge poisons everything) · the corpus's Sam/@soham analogue resolves to one `:Entity` with ≥3 aliases · WHO_KNOWS for a known incident returns its resolver · supersession flip round-trips in both stores + `REVERSED` edge exists · ≥1 conflict logged (zero = broken detector; the corpus plants contradictions).

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

Modifiers: `temporal` → mask `period`, **no recency preference** (you want the old state) · `conflict` → don't mask `validity` (need both sides) · `needs_current_only` → mask `validity='current'` on vector lanes. Masks = numpy boolean filters over metadata loaded once at startup.

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

Deterministic gate on top:

```python
def should_abstain(docs, ans):
    if not docs: return True
    if docs[0].score < 0.30: return True                    # calibrate on dev traces
    if ans["status"] == "answered" and not ans["citations"]: return True
    if set(ans["citations"]) - {d.id for d in docs}: return True   # fabricated citation
    return False
```

Log `(question, gold, predicted, lanes, ranks)` → `eval/results/traces.jsonl`. When the gate fires (or intent is `live`) and Composio connections exist, the live-lookup step (§12.5) runs before returning `absent`.

### ✅ Checkpoint 7 — `check_7_answer.py` (nine probes)
1 lookup w/ citation · 2 multihop w/ non-empty path, ≥2 sources · 3 known conflict → both positions · **4 invented-unanswerable → absent — THE gate; pass ~5 different ones before proceeding** · 5 temporal-history returns the superseded state · 6 current-only returns the current one · 7 exact-token via PHRASE survives fusion · 8 consensus: a doc mid-rank in ≥3 lanes outranks a single-lane #1 (log per-lane ranks) · 9 planted related-but-non-answering doc reranks ≤3 and drops out.

---

## 11. Phase 8 — Eval + ablations

Output JSONL `{question_id, answer, document_ids}` — **verify the internal↔corpus id mapping on 5 gold rows before running anything** (perfect system + wrong id format = zero). Concurrency 8–12 + resume file. `score.py`: retrieval recall@k · answer accuracy (LLM judge) · **abstention precision AND recall reported separately** · conflict accuracy · path validity.

Ablation ladder (`eval/ablate.py`, the README centerpiece): **A** vector-only → **B** +distillation (artifacts in the index) → **C** +RRF lanes → **D** +rerank+gate+graph. Report stages that didn't move accuracy honestly — negative results read as rigor.

### ✅ Checkpoint 8 — end-to-end on dev without crashing · output validates · ablation table in `eval/results/` · scale to eval slices only if time allows (a complete small system beats a half-ingested big one).

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

**The prebuilt-image unlock (Aug 16, ~30 min):** build the HydraDB repo's own `Dockerfile` once, push `ghcr.io/dupenodi/hydradb-node:hackhydra`. Without it every judge pays a 20-minute Rust compile before seeing anything. Bake the embedding model into the joel-api image (`RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"`) so first boot doesn't hang on a 130MB download.

Judge path: `git clone … && cp .env.example .env` (one LLM key) `&& docker compose up` → localhost:3000.

| ✅ DO | ❌ DON'T |
|---|---|
| Test compose from a clean clone on a pruned Docker (`docker system prune`) | Ship a compose that works only because your host has state |
| Pin image tags; document every env var in `.env.example` | `latest` + undocumented env |
| Persist everything under named volumes; kill-and-up must survive | Store state in container FS |

### 12.2 API — `joel/routes.py` (FastAPI)

| Endpoint | Does |
|---|---|
| `POST /api/org {domain}` | create org: name derived from domain, logo via `https://www.google.com/s2/favicons?domain={d}&sz=128` |
| `GET /api/org` | org + readiness (the §1.2 checklist, live) |
| `GET/POST /api/connectors` · `POST /api/connectors/{id}/sync` · `DELETE /api/connectors/{id}` | connector CRUD + **Sync now** |
| `GET /oauth/{provider}/start` · `GET /oauth/{provider}/callback` | custom-OAuth flow |
| `GET/POST /api/conversations` · `GET /api/conversations/{id}` | conversation list / messages |
| `POST /api/ask {conversation_id, question}` | **SSE stream**: `status → lanes → tokens → citations → reasoning_path` |
| `GET/PUT /api/settings` · `GET/PUT /api/profile` | settings kv, profile |
| `POST /api/org/wipe` | danger zone: truncate all three stores for the dataset |

SQLite tables added: `orgs` (single row: domain, name, logo_url, state), `connections` (`id, provider, mode, status, account_ref, cursor, last_sync, doc_count, error_msg, config_json`), `conversations` (`id, title, created_at`), `messages` (`id, conversation_id, role, content_json, created_at`), `settings` (kv).

### 12.3 Web — the five pages (Next.js + Tailwind + shadcn)

**`/onboarding`** — 3 steps: ① domain input (`yourco.dev`) → org card appears with fetched favicon + derived name → ② choose data: **Connect your tools** (jumps to connectors) · **Load benchmark corpus** (no tool credentials needed) → ③ the live readiness checklist (`fetched ✓ · distilled ✓ · people resolved ✓ · graph linked ✓ · indexes consistent ✓`) → auto-forward to `/chat` at READY.

**`/connectors`** — one card per tool: logo, status pill (per-connector state machine §1.2), mode badge (`demo/benchmark/composio/oauth`), last sync, doc count, buttons [Connect] [Sync now] [Disconnect], inline error with retry. Empty state links back to onboarding.

**`/chat`** — conversations sidebar (auto-titled from first question) · message stream with the status badge per answer: ✅ answered / 🟡 partial ("**Not found:** …") / ⚠️ conflicted (two positions side by side, dated + sourced, assessment line) / 🚫 **"Not in the company's memory."** · citations as chips deep-linking `url` · collapsible "reasoning path" rendering the graph paths · footer chips naming the lanes that contributed (`artifacts·phrase·graph`) · ingestion banner while any connector is syncing · a distinct **LIVE chip** on citations that came from a real-time tool call (§12.5).

**`/settings`** — LLM base/key/model pickers · Composio key · custom OAuth creds per provider · embed model (read-only display) · all persisted to the `settings` table, overriding `.env`.

**`/profile`** — display name + auto avatar (initial) · org block (logo, name, domain, created, doc/entity counts) · danger zone: wipe org (typed confirmation).

Every page is a thin view over queries this spec already builds — the product layer is presentation + connectors, not new intelligence.

### 12.4 Connectors — four modes, one interface

```python
class Connector(ABC):
    provider: str      # slack | gmail | jira | ...
    mode: str          # benchmark | composio | oauth
    def auth_status(self) -> str: ...
    def backfill(self, cursor) -> Iterator[list[dict]]: ...   # raw docs, batched
    def poll(self, cursor) -> tuple[list[dict], str]: ...     # Sync-now / incremental
    # raw → CanonicalDoc uses the SAME §6 adapters. Connectors fetch; adapters normalize.
```

| Mode | Who | Setup |
|---|---|---|
| **benchmark** | evaluators reproducing numbers | point at downloaded slices |
| **composio** | anyone connecting real tools fast | paste a free Composio API key → hosted OAuth per tool |
| **oauth** | teams who won't route through Composio | own OAuth app: paste client id + secret |

**Composio path — important distinction:** Composio is agent-tooling-first, but its actions are **directly executable via SDK without any agent** — they're wrapped API calls you can loop. Still, for bulk backfill the cleaner pattern is **Composio as auth broker only**: user completes hosted OAuth → joel **retrieves the connected account's access token** from Composio → ingestion hits the **provider APIs directly** with that token (Slack `conversations.list`/`conversations.history` with real cursors, Gmail `messages.list`, GitHub REST) — full pagination + rate-limit control, no action-wrapper constraints. Fetch strategy, in order: ① direct provider APIs with Composio-brokered tokens · ② fallback: loop Composio actions (fine for a bounded 2K-doc backfill; handle pagination params yourself). **Verify token-retrieval availability in Composio docs at build time — it decides which branch you're on; if unavailable, branch ② is the plan.** Ship **Slack + GitHub** first; the other seven render as "coming soon" cards behind the same interface. Chat is memory-first but ALSO uses Composio — live lookups, §12.5.

**Custom OAuth path:** generic authorization-code flow — per-provider `{auth_url, token_url, scopes}` config → `GET /oauth/{provider}/start` with `redirect_uri=http://localhost:8000/oauth/{provider}/callback` → token exchange → stored in SQLite **Fernet-encrypted with `JOEL_SECRET`** (generated on first boot) → direct API fetchers with refresh-on-401. Implement fully for **one** provider (GitHub is the least-friction OAuth app to create) and document the pattern. README states it plainly: self-hosted, single-tenant, tokens at rest on your disk, encrypted with a key on the same disk — honest local-first security.

**Sync model (deliberately simple, no schedulers):** backfill on connect (bounded: last 90 days OR 2,000 docs per connector, user-adjustable) → after that, the **Sync now** button runs `poll()`. That's it. Incremental docs run the pipeline incrementally: only affected threads re-distill; bursts that stop being kept get deleted from all three stores (the `kept.json` diff).

| ✅ DO | ❌ DON'T |
|---|---|
| Progress on the connector card during backfill (`backfilling 340/2000 → distilling 12 threads → linking → ready`) | A silent 15-minute first sync — users assume it's broken |
| Serialize LLM-heavy stages behind one queue with a concurrency cap | Let two connectors' backfills fan 200 parallel distill calls into your key |
| Surface last error on the card + retry | Bury sync failures in logs |

### 12.5 Live lookups — chat uses Composio tools too

Memory-first, always: the full retrieval pipeline (§10) runs first. Then, live tools kick in on exactly two conditions: **(a)** planner intent is `live`, or **(b)** the abstention gate fired AND ≥1 Composio connection is active. In either case the answer step may execute Composio actions directly (same SDK, no agent framework) against connected tools — e.g. fetch the latest N messages of a channel, get a PR's current state — and synthesize from `memory context + live results`.

Guardrails (encode all of them):

| ✅ DO | ❌ DON'T |
|---|---|
| Hard cap: **2 tool calls per question, 10s timeout each, read-only action whitelist** | Open-ended tool loops — this is a lookup, not an agent |
| Label live-sourced citations with the LIVE chip; answer text says "as of just now" | Blend live facts into memory citations indistinguishably |
| Stream a "checking live…" SSE event so the UI shows what's happening | Silent 8-second stalls |
| **Feed live results through the normal ingest pipeline after answering** — a live lookup becomes memory (the loop closes) | Re-fetch the same fact live forever |
| Abstention wording when tools ran: "Not in the company's memory — a live check of Slack found nothing either" | Plain 🚫 that hides the live attempt |
| Skip live entirely on `JOEL_DATASET=bench` | Let live calls contaminate benchmark runs |

### ✅ Checkpoint 9 — `check_9_app.py` + manual
`docker compose up` from a clean clone reaches onboarding · benchmark path loads the dev manifest and `/chat` answers a gold question with citations (**no tool credentials**) · Composio path: connect a real Slack, backfill progress visible, ask about a real message, **Sync now** picks up a message posted after backfill · live-lookup: a `live`-intent question triggers ≤2 tool calls and renders the LIVE chip · conversations persist across reload · settings round-trip · wipe org works · `docker compose down && up` — state survives.

---

## 13. Phase 10 — Demo plan (real connections)

The video demos joel on **your own real workspace** — no seeded fictional company. What real data must contain for the beats to land (if your history lacks one, create it naturally during the build days — posting in your own workspace IS real usage):

| Needed in the workspace | Powers |
|---|---|
| a resolved troubleshooting thread containing an exact identifier (env var / error string) | Q1 cited answer + the exact-match lane |
| a decision message and a later explicit reversal ("reverting X — going with Y") | the reversal ledger beat |
| a commitment nobody was assigned ("we told them we'd ship Z") | conflict/commitment material |
| two channels saying contradictory things about the same topic | ⚠️ both-sides beat |
| one person referenced two ways (display name vs @handle) | entity-resolution beat |
| a topic **never** discussed anywhere | 🚫 abstention beat |

**Run-of-show (record twice, blur anything sensitive, capture the OAuth consent once in advance):**
1. Onboarding on camera: your domain → org card with favicon → Connect your tools → Composio OAuth for Slack (+GitHub) → readiness checklist ticks over the real backfill (cut the wait).
2. **Q1** the troubleshooting question → ✅ cited answer quoting the exact identifier.
3. **Q2** "who fixed / who owns X?" → the person, with both name forms visible in the reasoning path.
4. **Q3** the contradictory topic → ⚠️ both positions, dated, sourced.
5. **Q4** "what did we decide on X — did that change?" → current state + superseded decision.
6. **Q5** the never-discussed topic → 🚫 "Not in the company's memory."
7. Post a correction in Slack → **Sync now** on the connector card → re-ask Q1 → updated answer cites the new message.
8. `[if wired]` a `live` question ("anything new in #eng today?") → the LIVE chip renders.

Real-data risk log: OAuth can hiccup on camera (pre-record consent) · private info on screen (blur pass before publishing) · backfill duration (start it before recording).

## 14. X posts — build-in-public (genuine voice, not promo)

Voice rules: share what you're learning, not a campaign. Tag @hydradb only where natural. **Credit the Cerebras article openly** — citing influences reads as real. Concrete beats clever. Post when the checkpoint actually passes. Real screenshots/clips only. Numbers from `eval/results/`, never invented. Drop each post in the hackathon Discord after posting (organizers asked for exactly this).

**Post 1 — today:**
> every team i've worked with loses the same knowledge over and over. someone asks "why did we pick X?" and the person who knew left six months ago. the doc says what was decided — never why.
>
> so this week i'm building **joel** for hack hydra: a company brain over 9 tools (slack, jira, confluence, gmail, meetings…) on @hydradb's open-source graph db, running fully local.
>
> not chat-over-docs. the goal is a system that remembers decisions, who made them, what overturned them, and says "not in the data" instead of guessing.
>
> day 0. will post what breaks.

**Post 2 — after CP4:**
> read the cerebras post on how they built their internal knowledge base and one idea rewired my whole build:
>
> don't embed messages. **distill the thread first.**
>
> a 4-message thread whose answer is "set CKPT_PREFETCH=4" should become ONE record that says exactly that. "sounds good, thanks!" should never be a search result.
>
> joel now turns every thread into {question, resolution, exact refs} before anything touches the index. the chatter still informs the artifact — then gets dropped.
>
> retrieval quality is mostly an ingestion problem.

**Post 3 — after CP7:**
> tested every retrieval signal on real messy company data. each one fails alone:
>
> - embeddings: "sounds good, thanks!" is a false neighbor of everything
> - full-text: misses every paraphrase
> - both: happily return the 8-month-old fix that no longer works
>
> so joel runs the lanes in parallel — vector, full-text, distilled artifacts, graph — and fuses with reciprocal rank fusion. a doc ranked 4th in three lists beats one ranked 1st in a single list. consensus over confidence.
>
> (also from the cerebras kb article. it's that good.)

**Post 4 — after CP6 (attach a WHO_KNOWS screenshot):**
> "who actually knows about the billing migration?"
>
> grep can't answer that. embeddings can't either. joel answers it with one hop in @hydradb:
>
> (person)-[:RESOLVED|OWNS|DECIDED]->(thing)
>
> the query was the easy part. the hard part was deciding that "Sam", "@soham" and "S. Ratnaparkhi" across 9 tools are one person. entity resolution is 80% of a company brain, and nobody talks about it.

**Post 5 — after CP9 (attach the clip):**
> ok this one felt like magic.
>
> asked joel how we fix restore stalls → answered, with citations.
> someone posted a correction in slack. hit "sync now" on the connector.
> asked again → new answer, cites the new message, old fix marked superseded.
>
> memory that updates when the team talks.

**Post 6 — ship day:**
> shipped **joel** for @hydradb's hack hydra.
>
> a self-hosted company brain: `docker compose up`, connect your tools, and chat with your org's memory. distills threads before embedding, resolves people across sources, keeps a decision-reversal ledger in the graph, and abstains instead of hallucinating.
>
> vector-only baseline: [A]% → full pipeline: [B]%. the gap is the graph.
>
> repo: [link] · demo: [link]
>
> favorite part: watching it say "not in the data." most systems can't.

---

## 15. Submission

**README:** problem → 30s GIF (onboarding→chat) → **How it uses HydraDB** (the ontology + reversal ledger live *in* the graph · WHO_KNOWS + multi-hop are Cypher/`algo.MSpaths` · thread/provenance structure as edges · "the ontology isn't an index over the database — it IS the database") → ablation ladder → architecture → **judge quickstart:** clone → `.env` with one LLM key → `docker compose up` → localhost:3000 → two cards: **connect your own Slack/GitHub via Composio** (the real experience, ~10 min if they have a workspace) or **load the benchmark corpus** (no tool credentials; needs the dataset download — link it + state sizes). Prebuilt GHCR image means no Rust compile either way; eval results checked in as CSV so numbers are inspectable without running anything → attribution (EnterpriseRAG-Bench MIT · HydraDB AGPL-3.0 · Cerebras article as design reference).

**Video (3:00, scripted):** 0:00 problem + a naive-RAG stale answer · 0:25 the pipeline diagram · 0:45 onboarding (domain → Composio OAuth → readiness ticks over a real backfill) · 1:05 the §13 questions Q1→Q5, landing hard on 🚫 · 2:15 sync-now beat if wired, else the reversal ledger + WHO_KNOWS query on screen · 2:40 ablation table: "this is a graph problem; here's what a vector index alone scores."

**Checklist:** MIT `LICENSE` · no pre-Aug-12 commits · `.env` untracked, `.env.example` complete · video ≤3:00, opens logged-out · compose tested from clean clone · form submitted with tested links · **deadline 12:29 PM IST Aug 21 — never the last 30 minutes.**

## 16. Schedule (today = Aug 16) — product-first

| Day | Target | CP |
|---|---|---|
| Aug 16 | HydraDB build + `just smoke` **+ push the GHCR image** · graph model + `cypher-compat.md` verify · adapters · DF index · compose skeleton | 0-3 |
| Aug 17 | distillation on dev · store layer · FastAPI `/api/ask` end-to-end (CLI-grade) | 4-5 |
| Aug 18 | ontology + resolution · lanes + RRF + rerank + abstention · dev eval + ablations | 6-8 |
| Aug 19 | **PRODUCT DAY:** the five pages · benchmark connector · Composio Slack (+GitHub if smooth) · live lookups · conversations + SSE | 9 |
| Aug 20 | prep real-workspace beats (§13 table) · record video · README · posts 5-6 · compose test from clean clone | — |
| Aug 21 AM | buffer: uploads + form (12:29 PM IST) | — |

Decided now: **product completeness beats benchmark scale.** Dev-set numbers with an installable product outrank a 45K ingest with a CLI. The rubric agrees.

## 17. Cut list (bottom-up)
1 eval-set scale-up (report dev numbers honestly) · 2 live lookups in chat (memory-first chat survives) · 3 custom-OAuth provider (Composio covers judges; keep the documented pattern) · 4 Composio beyond Slack+GitHub · 5 Sync-now beat in the video (Q1-Q5 survive) · 6 conversations sidebar → single conversation · **NEVER CUT: `docker compose up` from clean clone, the benchmark zero-credential path, chat with abstention + citations, distillation, entity resolution, the ontology-in-HydraDB, RRF fusion.**

## 18. Risks + prompt index
HydraDB build fails locally → day-1 task so Discord support has runway; Ubuntu/WSL best-documented · Cypher subset missing MERGE/SET/rel-props → §4.4 fallbacks, verified day 1 · Bolt auth differs → HTTP is the verified path · distill cost → estimate on 20 threads first; artifacts shrink extraction inputs · Composio action names drift → verify-at-build rule · over-merge → bias rule + CP6 eyeball · lanes rank poorly → tune top-k + gate threshold on `traces.jsonl`, not in prod · demo flake → record twice.
**Prompts (6):** `distill_thread` (DISTILL, 1/thread, most-tuned) · `extract_ontology` (EXTRACT) · `resolve_entity` (RESOLVE, ambiguous pairs, cached) · `plan_query` (RESOLVE, 1/q) · `rerank` (RERANK, 1/q) · `answer` (ANSWER, 1/q). All: JSON-only + one repair retry · rules after schema · negatives carry their reason · long input last.

## 19. Master gotcha checklist (pin it)
`RUST_MIN_STACK=33554432` or the node aborts on first query · unset `CLOUD_PROVIDER` reads as literal `null` · `LOCAL_PATH` must pre-exist · `GRAPH_ALLOW_PLAINTEXT=true` for dev · node holds the foreground = working · **a listening port proves nothing; a round-tripped write does** · macOS direct-cargo needs `BINDGEN_EXTRA_CLANG_ARGS` · venv for Python deps (PEP 668) · `strong` reads in checkpoints · verify MERGE/SET/rel-props before coding store.py · bound all traversals · never interpolate raw text into Cypher (Bolt params or careful escaping) · ids identical across SQLite/npz/graph · bodies in SQLite, never graph props · quote user text in FTS5 · normalize embeddings at write · `written.json` ledger = your MERGE · burst deletion is explicit in all three stores · demo/bench = separate store dirs + index files (`JOEL_DATASET`) · lowercase/slug every filterable value · AGPL attribution, joel stays MIT.

---

## 20. Landing page — copy, animations, and the Claude Design brief

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
Hack Hydra guide · hydra-db/hydradb repo (README, AGENTS.md, architecture.md, cypher-compat.md) · EnterpriseRAG-Bench (MIT) · Sentra Company Brain essays · Supermemory Company Brain · Cerebras "How we built our knowledge base" · Composio docs (verify action names at build time).