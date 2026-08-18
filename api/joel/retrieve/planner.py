"""§10.1 — one LLM call that turns a question into a retrieval plan. Never
answers; only decides which lanes to run and how to mask/rewrite for them.

Model alias: §18's prompt index maps `plan_query` to RESOLVE, not a new
alias — CP0.4 only ever verifies 5 aliases (distill/extract/answer/resolve/
rerank) and this reuses one of them rather than adding a 6th. The `llm_call`
stage tag passed through is therefore `"resolve"`, matching what
`make_openrouter_caller` resolves against `llm_model_resolve`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from joel.llm import LLMCallFn, LLMError, call_json

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "plan_query.md"
_SYSTEM_PROMPT = (
    "Follow the user's instructions exactly. Return ONLY valid JSON — no prose, "
    "no markdown fences."
)
_STAGE = "resolve"  # see module docstring — plan_query reuses the RESOLVE alias

_VALID_INTENTS = {
    "lookup",
    "multihop",
    "conflict",
    "temporal",
    "aggregate",
    "absent_check",
    "who",
    "live",
}


class Temporal(BaseModel):
    period: str | None = None
    wants_history: bool = False


class QueryPlan(BaseModel):
    intent: str = "lookup"
    entities: list[str] = Field(default_factory=list)
    exact_tokens: list[str] = Field(default_factory=list)
    temporal: Temporal = Field(default_factory=Temporal)
    needs_current_only: bool = False
    rewrites: list[str] = Field(default_factory=list)


def _fallback_plan(question: str) -> QueryPlan:
    """A planner failure must degrade to "search everything literally", not
    crash the whole question — the vector/FTS lanes still work fine off the
    raw question text alone."""
    return QueryPlan(intent="lookup", rewrites=[])


def plan_query(llm_call: LLMCallFn, question: str) -> QueryPlan:
    template = _PROMPT_PATH.read_text()
    user_prompt = template.replace("{question}", question)
    try:
        raw = call_json(llm_call, _STAGE, _SYSTEM_PROMPT, user_prompt)
    except LLMError:
        return _fallback_plan(question)
    if not isinstance(raw, dict):
        return _fallback_plan(question)

    intent = str(raw.get("intent") or "lookup").strip().lower()
    if intent not in _VALID_INTENTS:
        intent = "lookup"

    temporal_raw = raw.get("temporal") if isinstance(raw.get("temporal"), dict) else {}
    temporal = Temporal(
        period=(str(temporal_raw.get("period")) if temporal_raw.get("period") else None),
        wants_history=bool(temporal_raw.get("wants_history", False)),
    )

    def _str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(v) for v in value if isinstance(v, (str, int, float))]

    return QueryPlan(
        intent=intent,
        entities=_str_list(raw.get("entities")),
        exact_tokens=_str_list(raw.get("exact_tokens")),
        temporal=temporal,
        needs_current_only=bool(raw.get("needs_current_only", False)),
        rewrites=_str_list(raw.get("rewrites"))[:2],
    )


__all__ = ["QueryPlan", "Temporal", "plan_query"]
