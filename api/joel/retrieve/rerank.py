"""§10.4 — LLM rerank pass: fused RRF candidates (numeric consensus) in,
"does this actually answer the question" judgments (0-10 scale) out. The
scale difference matters downstream: `should_abstain` in `synthesize.py`
gates on THIS 0-10 scale, never on raw RRF scores (§18's own gotcha list
calls this out by name — RRF tops out near 0.09, so a naive 0.3 threshold
against it would silently abstain on every question)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from joel.llm import LLMCallFn, LLMError, call_json
from joel.retrieve.lanes import RetrievedDoc

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "rerank.md"
_SYSTEM_PROMPT = (
    "Follow the user's instructions exactly. Return ONLY valid JSON — no prose, "
    "no markdown fences."
)
_STAGE = "rerank"
KEEP_TOP_N = 10
SNIPPET_CHARS = 300


@dataclass(frozen=True)
class RerankedDoc:
    doc: RetrievedDoc
    score: float
    reason: str

    @property
    def id(self) -> str:
        return self.doc.id

    @property
    def rerank_score(self) -> float:
        return self.score


def _build_candidates_block(candidates: list[RetrievedDoc]) -> str:
    lines = []
    for c in candidates:
        snippet = (c.body or "")[:SNIPPET_CHARS].replace("\n", " ")
        # `container` (Slack channel, GitHub repo, ...) is what a question
        # like "latest message in #general" actually names -- without it,
        # rerank can't tell two candidates from different channels apart.
        lines.append(
            f"{c.id} · {c.title} · {c.container or 'unknown'} · {c.granularity} · "
            f"{c.ts or 'unknown'} · {snippet}"
        )
    return "\n".join(lines)


def rerank_candidates(
    llm_call: LLMCallFn, question: str, candidates: list[RetrievedDoc], *, keep: int = KEEP_TOP_N
) -> list[RerankedDoc]:
    """Score every fused candidate against the question; return the top
    `keep` by score, descending. An LLM failure degrades to an empty
    result — not a raised exception — so a rerank outage makes the system
    abstain (safe) rather than crash the question."""
    if not candidates:
        return []

    template = _PROMPT_PATH.read_text()
    user_prompt = template.replace("{question}", question).replace(
        "{candidates}", _build_candidates_block(candidates)
    )
    try:
        raw = call_json(llm_call, _STAGE, _SYSTEM_PROMPT, user_prompt)
    except LLMError:
        return []
    if not isinstance(raw, list):
        return []

    by_id = {c.id: c for c in candidates}
    scored: list[RerankedDoc] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        doc_id = str(entry.get("id") or "")
        if doc_id not in by_id or doc_id in seen:
            continue
        try:
            score = float(entry.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(10.0, score))
        reason = str(entry.get("reason") or "")[:80]
        scored.append(RerankedDoc(doc=by_id[doc_id], score=score, reason=reason))
        seen.add(doc_id)

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:keep]


__all__ = ["RerankedDoc", "rerank_candidates", "KEEP_TOP_N"]
