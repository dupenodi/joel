"""§10.5 — the answer prompt plus the deterministic abstention gate on top.
The gate is what makes "absent" trustworthy: reranking picks the best
candidates, but nothing stops an LLM from padding a weak context into a
confident-sounding answer anyway, so `should_abstain` overrides the model's
own `status` rather than trusting it.

RERANK_FLOOR runs on the reranker's 0-10 scale, never RRF's ~0.09 scale —
see rerank.py's module docstring for why that distinction matters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from joel.llm import LLMCallFn, LLMError, call_json
from joel.retrieve.rerank import RerankedDoc

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "answer.md"
_SYSTEM_PROMPT = (
    "Follow the user's instructions exactly. Return ONLY valid JSON — no prose, "
    "no markdown fences."
)
_STAGE = "answer"
CONTEXT_BODY_CHARS = 2000

RERANK_FLOOR = 5.0  # reranker scale is 0-10; tune on real traces.jsonl, never on RRF scores

_ABSENT_ANSWER = "Not in the company's memory."


class ConflictPosition(BaseModel):
    claim: str = ""
    doc_id: str = ""
    when: str = ""
    source_type: str = ""


class Conflict(BaseModel):
    positions: list[ConflictPosition] = Field(default_factory=list)
    assessment: str = "unresolved"


class AnswerResult(BaseModel):
    status: str = "absent"  # answered|partial|conflicted|absent
    answer: str = _ABSENT_ANSWER
    citations: list[str] = Field(default_factory=list)
    reasoning_path: list[str] = Field(default_factory=list)
    conflict: Conflict | None = None
    confidence: float = 0.0


def _absent_result(reason: str = _ABSENT_ANSWER) -> AnswerResult:
    return AnswerResult(status="absent", answer=reason, citations=[], reasoning_path=[], confidence=0.0)


def _pre_gate_abstain(reranked: list[RerankedDoc]) -> bool:
    """The two `should_abstain` rules that don't depend on the model's own
    answer — checked BEFORE spending an LLM call on a context that's
    already too weak to answer from."""
    if not reranked:
        return True
    if reranked[0].rerank_score < RERANK_FLOOR:
        return True
    return False


def should_abstain(reranked: list[RerankedDoc], ans: AnswerResult) -> bool:
    """Verbatim port of §10.5's deterministic gate. Runs AFTER synthesis
    too, since a fabricated citation or an unsupported "answered" can only
    be caught once the model has actually answered."""
    if _pre_gate_abstain(reranked):
        return True
    if ans.status == "answered" and not ans.citations:
        return True
    valid_ids = {r.id for r in reranked}
    if set(ans.citations) - valid_ids:
        return True
    return False


def _build_context(reranked: list[RerankedDoc]) -> str:
    blocks = []
    for r in reranked:
        d = r.doc
        body = (d.body or "")[:CONTEXT_BODY_CHARS]
        blocks.append(
            f"[{d.id}] {d.title}\n"
            f"source={d.source_type} granularity={d.granularity} ts={d.ts or 'unknown'} "
            f"validity={d.validity}\n{body}"
        )
    return "\n\n".join(blocks)


def _parse_answer(raw: Any) -> AnswerResult:
    if not isinstance(raw, dict):
        return _absent_result()
    status = str(raw.get("status") or "absent").strip().lower()
    if status not in {"answered", "partial", "conflicted", "absent"}:
        status = "absent"
    citations = [str(c) for c in (raw.get("citations") or []) if isinstance(c, (str, int, float))]
    reasoning_path = [str(p) for p in (raw.get("reasoning_path") or []) if isinstance(p, (str, int, float))]
    conflict = None
    conflict_raw = raw.get("conflict")
    if isinstance(conflict_raw, dict):
        positions = [
            ConflictPosition(
                claim=str(p.get("claim") or ""),
                doc_id=str(p.get("doc_id") or ""),
                when=str(p.get("when") or ""),
                source_type=str(p.get("source_type") or ""),
            )
            for p in (conflict_raw.get("positions") or [])
            if isinstance(p, dict)
        ]
        conflict = Conflict(positions=positions, assessment=str(conflict_raw.get("assessment") or "unresolved"))
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return AnswerResult(
        status=status,
        answer=str(raw.get("answer") or "").strip() or _ABSENT_ANSWER,
        citations=citations,
        reasoning_path=reasoning_path,
        conflict=conflict,
        confidence=max(0.0, min(1.0, confidence)),
    )


def synthesize_answer(
    llm_call: LLMCallFn | None,
    question: str,
    reranked: list[RerankedDoc],
    *,
    graph_paths: list[str] | None = None,
) -> AnswerResult:
    """The full §10.5 flow: pre-gate → LLM synthesis → post-gate. Returns
    "absent" (never raises) on a weak context, a missing LLM key, or an
    LLM/parse failure — an answering outage must degrade to honest silence,
    not a 500."""
    if _pre_gate_abstain(reranked):
        return _absent_result()
    if llm_call is None:
        return _absent_result("Not in the company's memory. (no LLM key configured)")

    template = _PROMPT_PATH.read_text()
    paths_block = "\n".join(graph_paths or []) or "(none — ontology not yet built)"
    user_prompt = (
        template.replace("{context}", _build_context(reranked))
        .replace("{paths}", paths_block)
        .replace("{question}", question)
    )
    try:
        raw = call_json(llm_call, _STAGE, _SYSTEM_PROMPT, user_prompt)
    except LLMError:
        return _absent_result()

    ans = _parse_answer(raw)
    if should_abstain(reranked, ans):
        return _absent_result()
    return ans


__all__ = [
    "AnswerResult",
    "Conflict",
    "ConflictPosition",
    "RERANK_FLOOR",
    "should_abstain",
    "synthesize_answer",
]
