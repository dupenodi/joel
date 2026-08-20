"""Phase 7 (§10) — retrieval and answering. `answer_question` is the single
entry point: plan → lanes → fuse → rerank → abstention gate → synthesize.

Six lanes now run when `hydra_store` is passed: VECTOR, VEC-ARTIFACTS, FTS,
PHRASE, GRAPH and WHO_KNOWS (§9's ontology backs the last two). Passing
`hydra_store=None` degrades to the original four-lane build — e.g. §14's
"HydraDB unreachable" mode, or a caller that hasn't wired ontology up yet.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from joel.live_index import LiveIndex
from joel.llm import LLMCallFn
from joel.retrieve.fuse import rrf_fuse
from joel.retrieve.lanes import RetrievedDoc, hydrate_doc_ids, run_lanes
from joel.retrieve.planner import QueryPlan, plan_query
from joel.retrieve.rerank import RerankedDoc, rerank_candidates
from joel.retrieve.synthesize import AnswerResult, synthesize_answer
from joel.store import HydraStore
from joel.visibility import AskContext, allowed_stamps

EmbedFn = Callable[[list[str]], np.ndarray]

FUSE_TOP_N = 20


@dataclass
class RetrievalTrace:
    """Everything §10.6 wants logged, plus enough for `/api/ask` to render
    real lane/status SSE events instead of the old hardcoded ones."""

    question: str
    plan: QueryPlan
    lane_results: dict[str, list[RetrievedDoc]] = field(default_factory=dict)
    fused: list[RetrievedDoc] = field(default_factory=list)
    reranked: list[RerankedDoc] = field(default_factory=list)
    answer: AnswerResult = field(default_factory=AnswerResult)


def answer_question(
    conn: sqlite3.Connection,
    index: LiveIndex,
    embed_fn: EmbedFn,
    llm_call: LLMCallFn | None,
    question: str,
    *,
    ask: AskContext | None = None,
    hydra_store: HydraStore | None = None,
    extra_doc_ids: tuple[str, ...] = (),
) -> RetrievalTrace:
    question = question.strip()
    plan = plan_query(llm_call, question) if llm_call is not None else QueryPlan(intent="lookup")
    lane_results = run_lanes(conn, index, embed_fn, plan, question, ask=ask, hydra_store=hydra_store)
    fused = rrf_fuse(lane_results, top_n=FUSE_TOP_N)
    if extra_doc_ids:
        # §13.2: a doc the caller already knows is relevant this turn (a
        # freshly live-fetched one) gets a guaranteed shot at rerank rather
        # than hoping RRF rediscovers it among everything else in the
        # corpus — rerank's own LLM judgment still decides whether it
        # actually answers the question, this only guarantees it's SEEN.
        allowed = None if ask is None else allowed_stamps(ask)
        org_id = None if ask is None else ask.org_id
        already = {d.id for d in fused}
        extra = [
            d
            for d in hydrate_doc_ids(conn, list(extra_doc_ids), allowed=allowed, org_id=org_id)
            if d.id not in already
        ]
        fused = extra + fused
    reranked = rerank_candidates(llm_call, question, fused) if llm_call is not None else []
    answer = synthesize_answer(llm_call, question, reranked)
    return RetrievalTrace(
        question=question,
        plan=plan,
        lane_results=lane_results,
        fused=fused,
        reranked=reranked,
        answer=answer,
    )


TRACES_MAX_BYTES = 20 * 1024 * 1024  # 20MB per file
TRACES_MAX_BACKUPS = 5


def _rotate_if_needed(traces_path: Path) -> None:
    """§7.6/CP11: `traces.jsonl` appends unboundedly forever otherwise —
    the file this session has been writing to for real already knows how
    that goes. Simple numbered rotation (`.1` newest backup .. `.N`
    oldest, dropped past `TRACES_MAX_BACKUPS`), checked once per write
    rather than on a timer, so it needs no background task of its own."""
    try:
        if not traces_path.exists() or traces_path.stat().st_size < TRACES_MAX_BYTES:
            return
    except OSError:
        return
    oldest = traces_path.with_suffix(f"{traces_path.suffix}.{TRACES_MAX_BACKUPS}")
    if oldest.exists():
        oldest.unlink()
    for n in range(TRACES_MAX_BACKUPS - 1, 0, -1):
        src = traces_path.with_suffix(f"{traces_path.suffix}.{n}")
        if src.exists():
            src.rename(traces_path.with_suffix(f"{traces_path.suffix}.{n + 1}"))
    traces_path.rename(traces_path.with_suffix(f"{traces_path.suffix}.1"))


def log_trace(traces_path: Path, trace: RetrievalTrace, *, extra: dict | None = None) -> None:
    """§10.6: one line per question, rotated at `TRACES_MAX_BYTES` rather
    than growing forever. These traces are how RERANK_FLOOR gets tuned
    later and, per §16.3, the free evaluation set once there's enough of
    them."""
    traces_path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_needed(traces_path)
    line = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "question": trace.question,
        "plan": trace.plan.model_dump(),
        "lane_ranks": {name: [d.id for d in docs] for name, docs in trace.lane_results.items()},
        "rerank_scores": [{"id": r.id, "score": r.score} for r in trace.reranked],
        "status": trace.answer.status,
        "citations": trace.answer.citations,
        **(extra or {}),
    }
    with traces_path.open("a") as handle:
        handle.write(json.dumps(line) + "\n")


__all__ = [
    "RetrievalTrace",
    "answer_question",
    "log_trace",
    "FUSE_TOP_N",
    "TRACES_MAX_BYTES",
    "TRACES_MAX_BACKUPS",
]
