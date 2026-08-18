"""Phase 7 (§10) — retrieval and answering. `answer_question` is the single
entry point: plan → lanes → fuse → rerank → abstention gate → synthesize.

Reduced-lane build: GRAPH and WHO_KNOWS aren't implemented (they need CP6's
ontology, which doesn't exist yet — see `lanes.py`'s module docstring).
VECTOR, VEC-ARTIFACTS, FTS and PHRASE already have real ingested/distilled
data to search, so a question can get a real, cited answer today without
waiting on ontology.
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
from joel.retrieve.lanes import RetrievedDoc, run_lanes
from joel.retrieve.planner import QueryPlan, plan_query
from joel.retrieve.rerank import RerankedDoc, rerank_candidates
from joel.retrieve.synthesize import AnswerResult, synthesize_answer

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
) -> RetrievalTrace:
    question = question.strip()
    plan = plan_query(llm_call, question) if llm_call is not None else QueryPlan(intent="lookup")
    lane_results = run_lanes(conn, index, embed_fn, plan, question)
    fused = rrf_fuse(lane_results, top_n=FUSE_TOP_N)
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


def log_trace(traces_path: Path, trace: RetrievalTrace, *, extra: dict | None = None) -> None:
    """§10.6: one line per question, file rotated by the caller rather than
    growing forever. These traces are how RERANK_FLOOR gets tuned later and,
    per §16.3, the free evaluation set once there's enough of them."""
    traces_path.parent.mkdir(parents=True, exist_ok=True)
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


__all__ = ["RetrievalTrace", "answer_question", "log_trace", "FUSE_TOP_N"]
