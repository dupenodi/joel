"""§13.1 — working memory: follow-up rewriting and the meta/chitchat cheap
paths. Conversations are never indexed (not FTS, not vectors, not the
graph) — this module only ever reads `messages`, never writes anything
back into the corpus.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from joel.llm import LLMCallFn, LLMError, call_json

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "rewrite_question.md"
_SYSTEM_PROMPT = (
    "Follow the user's instructions exactly. Return ONLY valid JSON — no prose, "
    "no markdown fences."
)
# rewrite_question has no dedicated model alias (§18's prompt index lists it
# without one, unlike distill/extract/answer/resolve/rerank) — it reuses
# RESOLVE, the same reasoning plan_query already uses: a cheap,
# classification-shaped call that doesn't warrant a 6th alias.
_STAGE = "resolve"
RECENT_TURNS_LIMIT = 6
_VALID_KINDS = {"knowledge", "meta", "chitchat"}


@dataclass(frozen=True)
class Turn:
    role: str  # user | assistant
    content: str
    citations: tuple[str, ...] = ()


@dataclass(frozen=True)
class RewriteResult:
    question: str
    kind: str  # knowledge | meta | chitchat


def load_recent_turns(
    conn: sqlite3.Connection, conversation_id: str, *, limit: int = RECENT_TURNS_LIMIT
) -> list[Turn]:
    """The last `limit` turns, oldest first — trimmed by count rather than a
    token budget for now (conversations are short; revisit if that stops
    being true)."""
    import json

    rows = conn.execute(
        """SELECT role, content_json FROM messages WHERE conversation_id=?
           ORDER BY created_at DESC LIMIT ?""",
        (conversation_id, limit),
    ).fetchall()
    turns: list[Turn] = []
    for row in reversed(rows):
        payload = json.loads(row["content_json"] or "{}")
        content = str(payload.get("content") or "")
        citations = tuple(
            c.get("doc_id", "") for c in (payload.get("citations") or []) if isinstance(c, dict)
        )
        turns.append(Turn(role=row["role"], content=content, citations=citations))
    return turns


def _format_turns(turns: list[Turn]) -> str:
    if not turns:
        return "(no prior turns)"
    return "\n".join(f"{t.role}: {t.content}" for t in turns)


def rewrite_question(llm_call: LLMCallFn, turns: list[Turn], message: str) -> RewriteResult:
    """One cheap call per turn (§13.1). Degrades to "treat it as a
    standalone knowledge question" on any LLM failure — the full §10
    pipeline still works fine off the raw message text alone, same
    fallback shape `plan_query` already uses for its own failures."""
    message = message.strip()
    template = _PROMPT_PATH.read_text()
    user_prompt = template.replace("{last_n_turns}", _format_turns(turns)).replace(
        "{message}", message
    )
    try:
        raw = call_json(llm_call, _STAGE, _SYSTEM_PROMPT, user_prompt)
    except LLMError:
        return RewriteResult(question=message, kind="knowledge")
    if not isinstance(raw, dict):
        return RewriteResult(question=message, kind="knowledge")

    question = str(raw.get("question") or "").strip() or message
    kind = str(raw.get("kind") or "knowledge").strip().lower()
    if kind not in _VALID_KINDS:
        kind = "knowledge"
    return RewriteResult(question=question, kind=kind)


def answer_meta(turns: list[Turn], question: str) -> str:
    """§13.1's meta path: answered from the conversation alone, no lanes,
    no rerank, no extra LLM call — every example §13.1 gives ("what did
    you just say", "summarise this chat", "which sources did you use") is
    mechanically answerable straight from the stored turns, so this stays
    at zero additional cost rather than inventing an 8th prompt for a
    handful of deterministic cases."""
    assistant_turns = [t for t in turns if t.role == "assistant"]
    if not assistant_turns:
        return "We haven't covered anything yet in this conversation."

    last = assistant_turns[-1]
    lowered = question.lower()
    if "source" in lowered or "citation" in lowered:
        if not last.citations:
            return "My last answer didn't cite any sources."
        return "The sources for my last answer: " + ", ".join(last.citations)
    if "summar" in lowered:
        lines = [f"- {t.role}: {t.content}" for t in turns if t.content]
        return "Here's this conversation so far:\n" + "\n".join(lines) if lines else (
            "There's nothing to summarize yet."
        )
    # Default: "what did you just say" and anything else meta-shaped.
    return last.content


__all__ = [
    "Turn",
    "RewriteResult",
    "RECENT_TURNS_LIMIT",
    "load_recent_turns",
    "rewrite_question",
    "answer_meta",
]
