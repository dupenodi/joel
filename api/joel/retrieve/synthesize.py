"""§10.5 — the answer prompt plus the deterministic abstention gate on top.
The gate is what makes "absent" trustworthy: reranking picks the best
candidates, but nothing stops an LLM from padding a weak context into a
confident-sounding answer anyway, so `should_abstain` overrides the model's
own `status` rather than trusting it.

RERANK_FLOOR runs on the reranker's 0-10 scale, never RRF's ~0.09 scale —
see rerank.py's module docstring for why that distinction matters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, Field

from joel.llm import (
    JSONFieldStreamer,
    LLMCallFn,
    LLMError,
    LLMStreamFn,
    call_json,
    parse_json_response,
)
from joel.retrieve.rerank import RerankedDoc

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "answer.md"
_SYSTEM_PROMPT = (
    "Follow the user's instructions exactly. Return ONLY valid JSON — no prose, "
    "no markdown fences."
)
_STAGE = "answer"
CONTEXT_BODY_CHARS = 2000

RERANK_FLOOR = 5.0  # reranker scale is 0-10; tune on real traces.jsonl, never on RRF scores

# Below this, the best candidate is genuinely unrelated and calling the model
# would only invite invention. Between this and RERANK_FLOOR the context is
# real but does not fully answer — the case a single floor handled worst.
#
# The reranker is deliberately harsh (see prompts/rerank.md: "topically
# related but non-answering → <=3"), so a document that holds most of what
# someone asked for routinely scores 2-4. With one floor at 5 that document
# was retrieved, correctly scored, and then discarded, and the user was told
# "Not in the company's memory" about a notice the system was holding. The
# honest answer there is not silence, it is "here is what the notice says,
# and here is the part it does not say" — which is exactly the `partial`
# status the answer prompt already defines.
SYNTHESIS_FLOOR = 2.0

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
    """The `should_abstain` rules that don't depend on the model's own
    answer — checked BEFORE spending an LLM call on a context that's
    already too weak to answer from."""
    if not reranked:
        return True
    if reranked[0].rerank_score < SYNTHESIS_FLOOR:
        return True
    return False


def _is_weak_context(reranked: list[RerankedDoc]) -> bool:
    """Context good enough to reason over, not good enough to be confident:
    the model may answer `partial`, never `answered`."""
    return bool(reranked) and reranked[0].rerank_score < RERANK_FLOOR


def _downgrade_if_weak(ans: AnswerResult, reranked: list[RerankedDoc]) -> AnswerResult:
    """A confident `answered` off a below-floor context is the exact failure
    the floor exists to prevent, but throwing the whole answer away costs
    the user the part that was genuinely supported. Downgrade the claim
    instead of deleting it — the prose and citations survive, the confidence
    does not."""
    if ans.status == "answered" and _is_weak_context(reranked):
        return ans.model_copy(update={"status": "partial"})
    return ans


def should_abstain(
    reranked: list[RerankedDoc],
    ans: AnswerResult,
    *,
    profile_only: bool = False,
) -> bool:
    """Verbatim port of §10.5's deterministic gate. Runs AFTER synthesis
    too, since a fabricated citation or an unsupported "answered" can only
    be caught once the model has actually answered.

    `profile_only`: answering from workspace_about with no corpus hits —
    citations are optional (there is no doc_id to cite).
    """
    if profile_only:
        if ans.status == "absent":
            return True
        if not (ans.answer or "").strip() or ans.answer.strip() == _ABSENT_ANSWER:
            return True
        return False
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
        # `container` (Slack channel name, GitHub repo, etc.) is the human
        # identifier a question actually names ("#all-acme-inc") -- without
        # it here, only the opaque `[doc_id]` (often a raw provider ID like
        # a Slack channel_id) is visible, and the model has no way to
        # confirm a doc belongs to the channel/repo the question asked
        # about. Found live: a real "latest message in #channel" question
        # abstained because the doc's own text never states its channel.
        blocks.append(
            f"[{d.id}] {d.title}\n"
            f"source={d.source_type} container={d.container or 'unknown'} "
            f"granularity={d.granularity} ts={d.ts or 'unknown'} "
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


def _voice_block(*, voice: str = "", workspace_about: str = "") -> str:
    parts: list[str] = []
    about = workspace_about.strip()
    how = voice.strip()
    if about:
        parts.append(f"## About this company\n{about}")
    if how:
        parts.append(f"## How you talk\n{how}")
    if not parts:
        return ""
    return "\n\n" + "\n\n".join(parts) + "\n"


def synthesize_answer(
    llm_call: LLMCallFn | None,
    question: str,
    reranked: list[RerankedDoc],
    *,
    graph_paths: list[str] | None = None,
    voice: str = "",
    workspace_about: str = "",
) -> AnswerResult:
    """The full §10.5 flow: pre-gate → LLM synthesis → post-gate. Returns
    "absent" (never raises) on a weak context, a missing LLM key, or an
    LLM/parse failure — an answering outage must degrade to honest silence,
    not a 500.

    When the corpus is empty/weak but `workspace_about` is set (onboarding
    Research seed), still answer from that profile — otherwise Chat looks
    broken right after setup before connectors finish.
    """
    profile = workspace_about.strip()
    weak = _pre_gate_abstain(reranked)
    if weak and not profile:
        return _absent_result()
    if llm_call is None:
        return _absent_result("Not in the company's memory. (no LLM key configured)")

    profile_only = weak and bool(profile)
    template = _PROMPT_PATH.read_text()
    paths_block = "\n".join(graph_paths or []) or "(none — ontology not yet built)"
    if profile_only:
        context = (
            "(No indexed documents ranked high enough for this question. "
            "Answer ONLY from ## About this company in the voice block if it "
            "contains the answer; otherwise status=absent. Citations may be [].)"
        )
    else:
        context = _build_context(reranked)
        if _is_weak_context(reranked):
            context += (
                "\n\n(None of these scored as a direct answer. Say what they DO "
                "establish and name precisely what is still missing; status must "
                "be `partial` or `absent`, never `answered`.)"
            )
    user_prompt = (
        template.replace("{context}", context)
        .replace("{paths}", paths_block)
        .replace("{question}", question)
        .replace("{voice_block}", _voice_block(voice=voice, workspace_about=workspace_about))
    )
    try:
        raw = call_json(llm_call, _STAGE, _SYSTEM_PROMPT, user_prompt)
    except LLMError:
        return _absent_result()

    ans = _downgrade_if_weak(_parse_answer(raw), reranked)
    if should_abstain(reranked, ans, profile_only=profile_only):
        return _absent_result()
    return ans


def synthesize_answer_streaming(
    llm_stream: LLMStreamFn | None,
    question: str,
    reranked: list[RerankedDoc],
    *,
    graph_paths: list[str] | None = None,
    voice: str = "",
    workspace_about: str = "",
) -> Iterator[tuple[str, str | AnswerResult]]:
    """`synthesize_answer`, delivered as it is written.

    Yields `("delta", text)` for each piece of the answer prose as the model
    produces it, then exactly one `("result", AnswerResult)` at the end.

    The deltas are display, not truth. `should_abstain` can only run once the
    citations exist, so a model that fabricates one is caught after some of
    its prose has already been shown -- the final `AnswerResult` is
    authoritative and the caller is expected to replace what it streamed if
    the two disagree. Streaming an answer that is later withdrawn is the
    honest trade for not making every question feel like a five-second
    hang; silently keeping a retracted answer on screen would not be.
    """
    profile = workspace_about.strip()
    weak = _pre_gate_abstain(reranked)
    if weak and not profile:
        yield ("result", _absent_result())
        return
    if llm_stream is None:
        yield ("result", _absent_result("Not in the company's memory. (no LLM key configured)"))
        return

    profile_only = weak and bool(profile)
    template = _PROMPT_PATH.read_text()
    paths_block = "\n".join(graph_paths or []) or "(none — ontology not yet built)"
    if profile_only:
        context = (
            "(No indexed documents ranked high enough for this question. "
            "Answer ONLY from ## About this company in the voice block if it "
            "contains the answer; otherwise status=absent. Citations may be [].)"
        )
    else:
        context = _build_context(reranked)
        if _is_weak_context(reranked):
            context += (
                "\n\n(None of these scored as a direct answer. Say what they DO "
                "establish and name precisely what is still missing; status must "
                "be `partial` or `absent`, never `answered`.)"
            )
    user_prompt = (
        template.replace("{context}", context)
        .replace("{paths}", paths_block)
        .replace("{question}", question)
        .replace("{voice_block}", _voice_block(voice=voice, workspace_about=workspace_about))
    )

    extractor = JSONFieldStreamer("answer")
    try:
        for chunk in llm_stream(_STAGE, _SYSTEM_PROMPT, user_prompt):
            text = extractor.feed(chunk)
            if text:
                yield ("delta", text)
    except LLMError:
        yield ("result", _absent_result())
        return

    try:
        parsed = parse_json_response(extractor.raw)
    except ValueError:
        # The stream completed but the document is not parseable JSON. The
        # non-streaming path gets a repair retry here; retrying would mean
        # re-streaming prose the user has already read, so accept the loss
        # and abstain rather than double-answering.
        yield ("result", _absent_result())
        return

    ans = _downgrade_if_weak(_parse_answer(parsed), reranked)
    if should_abstain(reranked, ans, profile_only=profile_only):
        yield ("result", _absent_result())
        return
    yield ("result", ans)


def context_is_weak(reranked: list[RerankedDoc]) -> bool:
    """Public name for the pre-synthesis gate: is this context too thin to
    answer from at all? Callers outside synthesis use it to decide whether
    a live lookup is worth attempting, before spending an answer call."""
    return _pre_gate_abstain(reranked)


__all__ = [
    "AnswerResult",
    "Conflict",
    "ConflictPosition",
    "RERANK_FLOOR",
    "context_is_weak",
    "should_abstain",
    "synthesize_answer",
    "synthesize_answer_streaming",
]
