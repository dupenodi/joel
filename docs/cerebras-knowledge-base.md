# Cerebras: How We Built Our Knowledge Base

**Source:** [How Cerebras Built Its Enterprise Knowledge Base](https://www.cerebras.ai/blog/how-we-built-our-knowledge-base)  
**Authors:** Isaac Tai, Daniel Kim, Mike Gao  
**Published:** 15 Jul 2026  
**Captured:** 16 Aug 2026 from the live page, including SVG figures, inline CSS, and the JS that powers the interactive widgets.

This note is a working extract of the article — prose, diagrams, interactive states, and the tricks they actually encode — then a gap check against `PLAN.md`.

---

## 1. What they shipped

Internal tool **Cerebras Knowledge**. In three months:

- >15,000 questions / day
- Used by humans, automations, and agents
- Teams spanning data-center ops, chip design, hardware, training, inference, cloud

The questions that filled Slack:

> “Where can I find X?” · “Who is the expert in Y?” · “What is Z?”

Design thesis: **meet data where it lives.** Do not force a single source of truth. Extract from Slack, GitHub, Jira, docs, netlists, custom DBs. Platforms stay; the knowledge base is the overlay.

The product is three things:

1. Collect and store internal data
2. Query that data
3. AuthN/Z, auditing, analytics

Core store: **one Postgres table** holding embeddings, raw summaries, and metadata. One connector per source. Anything in the table is immediately queryable through the same interface (MCP, web UI, agents).

---

## 2. Architecture (hero SVG — fig 001)

Exploded isometric stack, bottom → top. Scroll parallax on the layers (disabled under `prefers-reduced-motion` and below 900px).

| Layer | What it is |
|---|---|
| **SOURCES** | Slack · Wiki · Code · Incidents |
| **DISTILLATION** | LLM extractors |
| **EMBEDDINGS** | pgvector · 3072-dim · HNSW |
| **RETRIEVAL** | six lists in parallel |
| **FUSION + RERANK** | RRF (k=60) → LLM rerank |
| **SYNTHESIS** | answer + citations |

Visual language used on every figure: cream paper `#fbfbfb`, ink `#171717`, cobalt/terracotta `#cc461f` / `#a93613`, IBM Plex Mono labels, hairline graph-paper background (40px grid + center dots). Not marketing illustration — they are the spec.

```
SOURCES  →  DISTILL  →  EMBED (3072 HNSW)  →  6 lists  →  RRF k=60  →  LLM rerank  →  answer+citations
```

---

## 3. One table, many sources (fig 002)

SVG: six source cards fan into one **EMBEDDINGS** record, then out to **MCP / WEB UI / AGENTS**.

Sources shown: Slack · Wiki/Confluence · Code repos · Netlists · PRM docs · Custom databases.

Each embedding row:

| Field | Content |
|---|---|
| DOCUMENT | normalized text |
| EMBEDDING | vector |
| METADATA | source + timestamps |

Captions on the figure: **ONE EMBEDDINGS TABLE** · **ONE CONNECTOR PER SOURCE**.

A source definition is three things: what the data is, how to connect, how often to fetch. Custom teams PR a small Python module that emits the same row shape.

---

## 4. Slack — the load-bearing source

Slack is where the most up-to-date engineering discussion lives. Vector search over raw messages failed for three reasons:

1. Density varies: “hey yeah sure mike” and a kernel explanation are both messages.
2. Short messages beat long, detailed ones on cosine similarity.
3. Meaning depends on the surrounding thread.

So every thread is retrievable through **several techniques at once**, and no single scorer is trusted.

### 4.1 Four retrieval signals (interactive fig `hybrid`)

Query used in the widget: **“restore hangs after manifest load”**

Four candidates, four timestamps:

| Age | Kind | Text |
|---|---|---|
| 2w ago | THREAD | Checkpoint stalls on the NFS mount — set `CKPT_PREFETCH=4`. |
| 1d ago | MESSAGE | `ERR_MANIFEST_TIMEOUT`: restore hangs after manifest load. |
| 3h ago | MESSAGE | sounds good, thanks! will try that |
| 8mo ago | THREAD | restore hangs after manifest load → use `LEGACY_FETCHER=1`. |

Clicking a signal restyles each row as **boost / dim / cut / none**:

| Candidate | 01 Full-text | 02 Embedding | 03 IDF | 04 Age decay |
|---|---|---|---|---|
| NFS stall + `CKPT_PREFETCH=4` | dim (no shared tokens) | **boost** (paraphrase) | **boost** (rare flag) | **boost** (recent wins tie) |
| `ERR_MANIFEST_TIMEOUT` paste | **boost** (exact tokens) | dim | **boost** (rare error) | none |
| “sounds good, thanks!” | dim | **boost** (false neighbor) | **cut** (no rare tokens) | none |
| 8-month-old `LEGACY_FETCHER=1` | **boost** (also matches) | none | none | **cut** (decayed) |

The tricks, in their words:

- **Full-text** catches tokens embeddings blur: error strings, flag names, host names. A pasted error is almost always the best evidence; semantic similarity must not outrank it.
- **Embedding** catches paraphrase. “restore hangs after manifest load” and “checkpoint stalls on the NFS mount” share no vocabulary.
- **IDF** separates signal from filler. A short message around a rare config flag deserves to rank. “sounds good, thanks!” sits close to many queries in embedding space and scores near zero once term rarity is applied.
- **Age decay** encodes that Slack answers expire. When relevance is otherwise equal, the newer thread wins. The 8-month-old exact match is the stale-infra trap.

Legend in the widget: solid orange outline = boosted by this signal; struck/dotted = penalized.

Keyboard: arrow keys cycle modes. `data-stage` 0–3 drives CSS.

### 4.2 Socket Mode ingest (fig 003)

Not polling. A Slack bot in **Socket Mode** receives every message over a persistent WebSocket.

Event path on the SVG:

```
SOCKET EVENT → ROUTE
                 ├─ BOT REPLY
                 ├─ @MENTION / DM
                 └─ TRACKED CHANNEL
                        ↓
                 REINGEST_THREAD → UPSERT THREAD → SYNC_WORKER
                        ↓
                   DISTILL → THREAD VECTOR
                           → BURST VECTORS
                 RESET WATERMARKS
```

Tricks:

- ACK immediately, dedupe on the stable Slack event ID, then mark for the ingest consumer.
- **Never save a reply in isolation.** Resolve the thread, re-fetch parent + every reply from the Slack API, write the **whole thread back as one row**. Participant list and last-activity timestamp always reflect the complete conversation.
- **Every channel is its own data source** — busy incident channels can ingest more often.
- Raw text is keyword-searchable the moment it lands (Postgres **GIN** full-text over raw content). Distillation is extra work for vector search, not a gate on lexical search.

### 4.3 Distill, then embed (interactive fig 004)

The article’s central ingestion claim: **do not embed the raw transcript.** Normalize the thread into a consistent format first. They say accuracy increased significantly when they did this (refs: Anthropic XML tags, nested data format).

Interactive three-stage pipeline. Channel `#CKPT-SUPPORT`, thread `thread_8f42`.

**Stage 01 — RAW THREAD** (all four messages enter together):

| t | Role the distiller will assign | Who | Text |
|---|---|---|---|
| 09:14 | QUESTION | Maya | Restore stalls after manifest load on the larger cluster. Small runs are fine. |
| 09:17 | SUMMARY | Owen | I can reproduce with 128 shards. The logs stop before cache warmup. |
| 09:18 | CONTEXT | Sam | My laptop also stalls when it sees Monday. |
| 09:21 | RESOLUTION | Maya | Setting `CKPT_PREFETCH=4` makes it complete. The default is too high for the NFS mount. |

Sam’s laptop line is labeled **CONTEXT** — it is in the input, it does not become the artifact.

**Stage 02 — THREAD ARTIFACT** (one JSON object from the whole thread):

```json
{
  "question": "Why does restore stall after manifest load?",
  "summary": "Large restores stop before cache warmup.",
  "resolution": "Set CKPT_PREFETCH=4 for the NFS mount.",
  "systems": ["checkpoint restore", "NFS"],
  "code_refs": ["CKPT_PREFETCH"]
}
```

Question is **what a future engineer would search**, not Maya’s first message verbatim.

**Stage 03 — EMBEDDED ROW** (pgvector):

Normalized document = `question + summary + resolution + systems + code references`

| col | value |
|---|---|
| source | `slack_thread` |
| source_id | `thread_8f42` |
| embedding | 3,072 dims |
| metadata | channel + authors + time |

Caption: **ONE QUERYABLE DATABASE RECORD.**

### 4.4 Bursting (fig 005)

Thread-level summaries miss tangent answers. A **burst** = a run of consecutive messages from the **same author**.

They embed qualifying bursts **with the thread topic prepended as context** (Anthropic contextual retrieval). That is how a one-off message whose vocabulary never made the summary stays findable.

Filter — weighted combination, must clear a threshold before embed:

- Contains a relatively rare token, **IDF ≥ 4.0**
- Combined burst **≥ 200 characters**
- One or more messages have **reactions** (social boost)

SVG story:

```
AUTHOR A short     ─┐
AUTHOR A follow-up ─┴─ BURST 01 FILTERED   short, common tokens, no reactions
AUTHOR B technical ─┐
AUTHOR B resolution─┴─ BURST 02 EMBEDDED   long, rare terms, reacted to
AUTHOR C ack          (not a kept burst)
```

Qualifying bursts sit in the embeddings table **alongside** the thread-level record.

---

## 5. Code repositories (interactive fig 006)

They almost skipped code embeddings (“grep is all you need”). After talking to others and reading Cursor’s semantic-search writeup, they embedded anyway. Some internal repos **> 40 GB**. The hard problem is staying current.

**CocoIndex** (open-source) tracks sync metadata in the same Postgres as the vectors. On each commit, re-embed **only changed chunks**. Teams onboard repos via config files with **path allowlists / denylists**.

### Chunking widget

Demo file: `CHECKPOINT_LOADER.CC` (C++ `CheckpointLoader` with `LoadManifest`, `WarmShardCache`, `Restore`, private fields). Hover/click toggles mode.

**01 NAIVE WINDOWS — cut every N tokens**

Five fixed bands: lines `[0–5], [6–12], [13–19], [20–26], [27–31]`. Status text: **“5 CHUNKS — FUNCTION BODIES ARE SPLIT ACROSS WINDOWS.”**

**02 LANGUAGE-AWARE — high → low regex boundaries** (default)

Recursive overlay, coarse to fine:

| depth | label | lines |
|---|---|---|
| 0 | 1 TRY: CLASS | 0–31 |
| 1 | 2 METHOD: LOADMANIFEST() | 2–7 |
| 2 | 3 IF STILL LARGE: IF | 4 |
| 1 | 2 METHOD: WARMSHARDCACHE() | 9–15 |
| 2 | 3 IF STILL LARGE: FOR | 10–13 |
| 1 | 2 METHOD: RESTORE() | 17–24 |
| 2 | 3 IF STILL LARGE: IF | 19 |
| 2 | 3 IF STILL LARGE: FOR | 20–22 |
| 1 | 2 SECTION: PRIVATE FIELDS | 26–30 |

Legend: filled band = semantic node; struck band = fixed split.

A single file can produce **multiple embeddings at different specificity** (file-level and function-level). If a class chunk is still too large, fall back to methods, then smaller blocks (`if` / `for`).

---

## 6. Query path

### 6.1 Planner + parallel fan-out (fig 007)

Every query starts with a short LLM planning pass over a **compact description of what is indexed**: which projects exist, which sources each project has, what each source is good at.

Tools:

| Tool | Job |
|---|---|
| `subsystem_index` | per-file LLM summaries |
| `search` | unified vector pipeline across Slack, wiki, code, others — merged and reranked internally |
| `search_slack` | direct Slack retrieval |
| `search_code` | **ripgrep** over source repos |
| `recent_prs` | recent PRs relevant to the question |
| `who_knows` | people with demonstrated expertise |

Executor fans selected tools out **in parallel**, normalizes into a common evidence schema (scores, recency, source hints), then a synthesis LLM writes the answer with citations.

SVG: `QUESTION → PLANNER → [SEARCH, SEARCH_SLACK, SEARCH_CODE, RECENT_PRS, WHO_KNOWS] → EVIDENCE (normalized rows) → SYNTHESIS → ANSWER + CITATIONS`

### 6.2 RRF then rerank (interactive fig 008)

Problem they name: a doc can rank high because it **shares vocabulary while answering a different question.**

Before the LLM reranker they fuse incompatible lists with **reciprocal rank fusion**:

```
score(d) = Σ  1 / (60 + rank_L(d))     k = 60, default weight 1.0
```

Smoothing constant is the point: **consensus beats a single strong vote.** A doc near the top of several lists can beat a list-1 exclusive.

The widget is a live calculator. Six togglable lists (click a column header to drop it from the sum; `RESET_` restores all). Hover a merged row highlights that doc in every source list. Rank changes animate with a FLIP translate.

**The six lists and their top-5 (this is their “six lists in parallel”):**

| Rank | VECTOR | FTS | THREAD SUMMARIES | GRAPH | WIKI VECTOR | SLACK FTS |
|---|---|---|---|---|---|---|
| 1 | CKPT_LOADER.CC | WIKI: CHECKPOINT FORMAT | THREAD: NFS STALL | CLASS: CHECKPOINTLOADER | WIKI: CHECKPOINT FORMAT | THREAD: NFS STALL |
| 2 | CLASS: CHECKPOINTLOADER | CKPT_LOADER.CC | THREAD: CACHE WARMUP | MANIFEST_PARSER.H | WIKI: LOAD STALLS | THREAD: CACHE WARMUP |
| 3 | WIKI: CHECKPOINT FORMAT | RUNBOOK: NFS MOUNTS | CLASS: CHECKPOINTLOADER | RUNBOOK: NFS MOUNTS | RUNBOOK: NFS MOUNTS | BURST: TIMEOUT FLAGS |
| 4 | THREAD: NFS STALL | INC-82: SLOW RESTORE | WIKI: LOAD STALLS | THREAD: NFS STALL | INC-82: SLOW RESTORE | INC-82: SLOW RESTORE |
| 5 | INC-82: SLOW RESTORE | THREAD: CACHE WARMUP | INC-82: SLOW RESTORE | WIKI: CHECKPOINT FORMAT | CLASS: CHECKPOINTLOADER | CLASS: CHECKPOINTLOADER |

Default merged top-6 (all lists on), scores from `1/(60+rank)`:

| Merged | Doc | Score | Why it wins |
|---|---|---|---|
| 1 | CLASS: CHECKPOINTLOADER | 0.0792 | 1/(60+2)+1/(60+3)+1/(60+1)+1/(60+5)+1/(60+5) — in five lists |
| 2 | INC-82: SLOW RESTORE | 0.0776 | mid-rank in five lists |
| 3 | WIKI: CHECKPOINT FORMAT | 0.0640 | tied |
| 4 | THREAD: NFS STALL | 0.0640 | tied |
| 5 | THREAD: CACHE WARMUP | 0.0476 | tied |
| 6 | RUNBOOK: NFS MOUNTS | 0.0476 | tied |

Tied 3/4 and 5/6 are the exhibit: fusion does not break ties by recency here; the **age-decay rule is a Slack scorer**, applied when relevance is otherwise equal, not a blanket boost inside RRF.

After fusion they:

1. **Merge duplicate chunks back to one source**
2. **Cap how many results each file can contribute**
3. Keep a **diverse top 20**
4. Send query + those 20 to a **small reranker**, score 0–10, **keep top 10** (Lost-in-the-Middle: don’t stuff the synthesizer)
5. **Only then expand context**: if a wiki section hits, pull in the **two neighboring sections** so heading / preconditions / caveats that chunking split apart are not lost

Output of search is a packet: fused, source-deduped, reranked against the actual question, then expanded.

### 6.3 Two surfaces (fig 009)

Same tools, different orchestration.

| | MCP | Web UI |
|---|---|---|
| What is exposed | retrieval **primitives**, as LLM-free as possible | full pipeline |
| Who orchestrates | Claude Code / any MCP client | the UI agent |
| Path | direct tool calls → raw evidence rows | planner → executor → synthesis |
| Why | cheap, stable, no hidden LLM in the tool | “ask a question, get an answer” |

Tools named: `search_slack`, `search_code`, `search`, `who_knows`. Inputs/outputs narrow and stable.

---

## 7. Organization (fig 010)

“Search everything everywhere” died as the corpus grew. Compiler engineers did not want infra runbooks.

A **project** is a named bundle of data sources (Slack channels, repos, DBs, doc spaces). Lightweight: the same source can be referenced by many projects **without duplicating data**.

SVG:

```
COMPILER PROJECT ── default query scope ── Compiler Slack, Monolith repo, Shared incidents
PLATFORM PROJECT ── default query scope ── Shared incidents, Platform repo, Cloud runbooks
```

Onboarding: pick or create a default project (ML training infra, Compiler, Data Center Ops). Stored on the user profile. New engineers get high-signal answers without learning which channels matter.

---

## 8. Trick list (the actual playbook)

Numbered so the PLAN gap check can point at them.

1. **Do not centralize writing.** Extract in place.
2. **One row schema for every source.** Connectors are plugins; query is uniform.
3. **Index raw text immediately** (GIN / FTS). Distillation is for vectors, not a gate on exact match.
4. **Never embed raw Slack.** Distill the whole thread into `{question, summary, resolution, systems, code_refs}`, embed that.
5. **Question is retrieval fuel** — phrase it as a future search, not the first message.
6. **Keep chatter in the distiller’s input** so it can label CONTEXT/noise; do not let it become the record.
7. **Bursts** (same-author runs) catch answers the thread summary drops.
8. **Prepend thread topic to burst text** before embedding (contextual retrieval).
9. **Do not embed low-signal bursts.** IDF ≥ 4.0, length ≥ 200 chars, reactions. “thanks!” never becomes a neighbor.
10. **Four Slack signals, fused later:** full-text, embedding, IDF, age-decay-on-ties.
11. **Re-ingest the entire thread on any reply.** One row always is the conversation.
12. **Per-channel watermarks / freshness**, not one global crawl rate.
13. **Language-aware recursive code chunking**, coarse → fine. Naive windows split functions; that is the failure mode they animate.
14. **File-level and function-level vectors** from the same file.
15. **Incremental re-embed of changed code only** (CocoIndex + Postgres sync metadata).
16. **Path allow/deny lists** so teams can onboard their own repos.
17. **Planner over a catalog of sources**, then parallel tool fan-out, then normalize, then synthesize.
18. **Ripgrep is a first-class tool** next to vectors (`search_code`). Semantic search did not replace grep.
19. **`who_knows` is a tool**, not a hope that embeddings surface owners.
20. **RRF k=60** so consensus outranks a single list’s #1.
21. **Per-file cap + source dedup** after fusion, before rerank.
22. **Rerank 20 → 10** with a small model scoring “does this **answer** the question,” not “is it about the topic.”
23. **Expand neighbors after ranking**, never before (keeps retrieval cheap, snippets complete).
24. **MCP = dumb primitives; UI = the agent.** Don’t hide an LLM inside every tool.
25. **Scope search with projects** that reference shared sources, don’t copy them.
26. **Default project on the user profile** so onboarding is “pick your world,” not “learn the corpus.”

---

## 9. References they cite

1. Malkov & Yashunin — HNSW (arXiv:1603.09320)
2. Anthropic — Contextual Retrieval, 2024
3. Cormack, Clarke, Büttcher — Reciprocal Rank Fusion, SIGIR 2009
4. Li et al. — Search-o1, arXiv:2501.05366, 2025
5. Anthropic — Code Execution with MCP, 2025
6. Liu et al. — Lost in the Middle, arXiv:2307.03172, 2023
7. Anthropic — Use XML Tags
8. Slack Engineering — How Slack AI Processes Billions of Messages
9. Improving Agents — Best Nested Data Format
10. Cursor — Improving Agent with Semantic Search, 2025

---

## 10. Visual / interactive inventory

All article figures are inline HTML/CSS/SVG plus small IIFEs. No raster images in the article body (only CookieYes chrome). Shared figure class: `.cb-fig`, cobalt CSS variables, graph-paper data-URI background.

| Figure | Type | Interaction |
|---|---|---|
| 001 hero stack | SVG, 6 `.hero-layer`s | scroll parallax `translateY` |
| 002 one table | static SVG | — |
| 003 Slack Socket flow | static SVG | — |
| hybrid | HTML list + 4 mode buttons | click/arrows restyle boost/cut |
| 004 distill | 3-stage HTML pipeline | click/arrows set `data-stage` |
| 005 bursts | static SVG | — |
| 006 chunking | JS-rendered code + overlay | hover/click naive vs language-aware |
| 007 planner fan-out | static SVG | — |
| 008 RRF | JS live scorer | toggle lists, hover highlight, FLIP reorder, RESET_ |
| 009 MCP vs UI | static SVG | — |
| 010 projects | static SVG | — |

---

## 11. Gap check against `PLAN.md`

`PLAN.md` §1.3 already names this article as the ingestion/retrieval philosophy. Most of the load-bearing tricks are in the spec. The misses are listed last.

### Already in the plan (mapped)

| Cerebras # | In PLAN |
|---|---|
| 1 meet data where it lives | Connectors extract; no “put it all in Confluence” |
| 2 one schema | `CanonicalDoc` + `store.upsert_docs` to SQLite / npz / Hydra |
| 4 distill then embed | §7 — “chatter informs the artifact, then vanishes” |
| 5 question-shaped artifact | `distill_thread.md` rule 1; `title=question[:300]`; `normalized_body` puts Q first |
| 6 keep noise in distiller input | §7.4 “Feed the distiller the WHOLE thread” |
| 7 bursts | `group_bursts`, 7-minute gap added |
| 9 don’t index thanks | `keep_burst` + `artifact_class=noise` |
| 10 four signals | §1.3 names them; FTS + PHRASE + VECTOR + age-on-ties in fusion |
| 13 language-aware code chunking | `BOUNDARIES` class → function; “never split a function body” |
| 17 planner then parallel lanes | `plan_query.md` + thread-pool lanes |
| 19 who_knows | `WHO_KNOWS` lane + Cypher |
| 20 RRF k=60 | `retrieve/fuse.py` copied, including the 0.0164 vs 0.0469 consensus example |
| 21 per-source cap | `PER_SOURCE_CAP = 3` |
| 22 rerank 20 → 8–10, “answering ≠ about the topic” | `rerank.md` rules 1 and 4 |
| 10 age decay on ties only | fusion `EPS = 0.005` window, “never as a blanket boost” |

PLAN goes **further** than the article on: ontology / reversal ledger in HydraDB, entity resolution, abstention statuses, conflict surfaces, live Composio lookups, three-store split (graph must not hold bodies). Those are joel-specific, not gaps.

### Partial — same idea, different mechanism

| Cerebras | PLAN | Difference that can bite |
|---|---|---|
| One Postgres table (embed + summary + meta) | Three stores, `doc_id` join | Intentional (Hydra track). Fine if upsert is the only writer. |
| 3072-dim HNSW pgvector | 384-dim bge-small, brute-force npz | Intentional (local, no limits). |
| IDF as its own ranked view, fused at query time | IDF at **ingest** (`df.frequency < 0.02`) + BM25 inside FTS | §1.3 *says* four query-time signals; §10.2 has no IDF lane. BM25 is the stand-in. |
| Burst filter: IDF≥4.0, ≥200 chars, reactions (weighted) | Keep if role∈{q,a,resolution} OR reactions OR (≥30 words AND rare tokens) | PLAN is role-first (better, because distillation already labeled). Thresholds are not the same; don’t “fix” them toward 200 chars without the distiller roles. |
| Re-fetch whole thread, upsert **one row** | Re-distill affected thread; artifact + **kept bursts** as separate rows | PLAN is closer to their burst diagram than their “one row” sentence. Need `kept.json` deletes. |
| Sync: Socket Mode, per-channel watermarks | Connect + Sync now, 90 days / 2k docs | Real-time is out of v1. Incremental poll is the substitute. |
| Code: if still large, split `if`/`for` | Never bisect a function; oversized function stays one chunk | PLAN is stricter. Matches their “don’t split functions” animation; skips their tertiary fallback. |
| Six RRF lists including WIKI VECTOR and SLACK FTS | VECTOR, VEC-ARTIFACTS, FTS, PHRASE, GRAPH, WHO_KNOWS | Same count, different split. No per-source vector/FTS lanes; PHRASE covers pasted errors; VEC-ARTIFACTS covers thread summaries. |
| `search_code` = ripgrep as a planner tool | PHRASE/FTS over code chunks | No dedicated ripgrep lane. Exact identifiers rely on `code_refs` + FTS. |
| File-level **and** function-level vectors | Function/class chunks only | May miss “which file is this in” queries that want the whole file as a hit. |

### Missing from the plan (real gaps)

These are in the article and **not** specified in `PLAN.md`. Ranked by whether they would change retrieval quality on the demo.

**Would change answers — consider adding if time:**

1. **Contextual retrieval on bursts (trick 8).** PLAN embeds burst text as-is. Cerebras prepends the thread topic/question. Cheap, cited (Anthropic 2024), and it is exactly how a tangent resolution stays findable. One-line change in burst body: `f"Thread: {artifact.question}\n{burst.text}"`.

2. **Neighbor expansion after rerank (trick 23).** PLAN sends a 300-char snippet into the reranker and the synthesizer. Cerebras ranks first, then pulls ±2 wiki/doc sections. Without this, Confluence H2 splits in §6 lose preconditions/caveats. After keeping 8–10, stitch `LINKED_TO` siblings (the split parts) into the answer context.

3. **Raw FTS before distillation finishes (trick 3).** Cerebras GIN-indexes raw Slack the moment it lands. PLAN’s chat is gated until the first connector is `ready`, which includes distilling. Fine for the demo; means a just-synced channel is dark until the LLM distiller catches up. If Sync-now must feel instant, upsert raw bursts/docs to FTS first, replace with artifacts when distill returns.

4. **Merge duplicate chunks back to one source (trick 21, second half).** `PER_SOURCE_CAP` limits how often a *connector* votes, not how many near-duplicate chunks of the same wiki page / same file survive into the top 20. After RRF, collapse `doc_id`s that share `container+url` or a code path so the reranker doesn’t see five windows of one file.

**Deliberately out of v1 — do not sneak in:**

5. Socket Mode / persistent Slack bot (no schedules in v1).
6. Per-channel freshness watermarks.
7. MCP primitive surface (joel is a web app; Claude Code as orchestrator is a different product).
8. AuthN/Z, audit, analytics (single-tenant, no login).
9. Projects as query scopes (one org; `JOEL_DATASET=main|bench` is the only split).
10. CocoIndex + path allowlists (GitHub adapter + bounded backfill instead).
11. Custom sources as “PR a Python module” (adapter interface is the analogue).
12. `subsystem_index` (per-file LLM summaries) and `recent_prs` as planner tools.
13. Default-project onboarding (joel onboarding is domain → connectors / benchmark).

### Verdict

The plan already copied the article’s two ideas that matter most: **distill-then-embed** and **RRF k=60 over complementary lists, then LLM rerank**. Bursting, language-aware code chunking, `who_knows`, question-shaped artifacts, and age-decay-on-ties are in there too.

The three article tricks that are **not** in the spec and **would** show up as worse retrieval: **prepend thread context on burst embeddings**, **expand neighboring sections after rerank**, and **collapse same-source duplicate chunks before the reranker**. IDF-as-its-own-lane is claimed in §1.3 and implemented only as BM25 + ingest filtering — worth a one-line honesty fix in §10.2, not a new lane.

Everything else missing is a product-scope cut (MCP, projects, Socket Mode, auth), not a missed ranking trick.
