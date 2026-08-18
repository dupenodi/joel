"""Thread → `ThreadArtifact` distillation (§7.2–§7.5) — the heart of the build.

Pipeline per thread: `group_bursts()` groups the RAW messages independently
of the LLM (bursts.py); this module sends those same raw messages (not the
bursts) to the distill prompt so it can assign a role to every individual
message, then folds those per-message roles back onto the pre-grouped
bursts to decide what survives `keep_burst()` (§7.3).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from joel.distill.df_index import DocFrequencyIndex, keep_burst
from joel.llm import LLMCallFn, LLMError, call_json
from joel.models import Burst, CanonicalDoc, ThreadArtifact, build_artifact_id

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "distill_thread.md"
_SYSTEM_PROMPT = (
    "Follow the user's instructions exactly. Return ONLY valid JSON — no prose, "
    "no markdown fences."
)
_MIN_CONFIDENCE = 0.3

_MEMBER_ROLE_PRIORITY = ("resolution", "answer", "question", "context", "noise")


class DistillFailure(RuntimeError):
    def __init__(self, thread_id: str, reason: str):
        super().__init__(f"distill failed for thread {thread_id!r}: {reason}")
        self.thread_id = thread_id
        self.reason = reason


def _load_template() -> str:
    text = _PROMPT_PATH.read_text()
    if "## Thread" not in text:
        raise RuntimeError("prompts/distill_thread.md is missing its '## Thread' section")
    return text


def _build_user_prompt(msgs: list[CanonicalDoc]) -> str:
    template = _load_template()
    header = (
        template.replace("{source_type}", msgs[0].source_type)
        .replace("{container}", msgs[0].container or "unknown")
        .replace("{n}", str(len(msgs)))
    )
    lines = [
        f"[{i}] {m.author_raw or 'unknown'} "
        f"({m.timestamp.isoformat() if m.timestamp else 'unknown'}): {m.body}"
        for i, m in enumerate(msgs)
    ]
    return header + "\n".join(lines) + "\n---"


def _majority_role(roles: list[str]) -> str | None:
    """§7.3: burst role = majority of member messages; any `resolution`
    message forces the burst role to `resolution` regardless of count."""
    if not roles:
        return None
    if "resolution" in roles:
        return "resolution"
    counts = Counter(roles)
    top = counts.most_common()
    best_count = top[0][1]
    tied = [role for role, count in top if count == best_count]
    if len(tied) == 1:
        return tied[0]
    # stable tie-break: prefer the more "useful" role over context/noise
    for role in _MEMBER_ROLE_PRIORITY:
        if role in tied:
            return role
    return tied[0]


def distill_thread(
    msgs: list[CanonicalDoc],
    bursts: list[Burst],
    *,
    llm_call: LLMCallFn,
    df: DocFrequencyIndex,
) -> tuple[ThreadArtifact | None, list[Burst]]:
    """Run one distill call over `msgs` and fold the result onto `bursts`.

    Returns `(artifact_or_None, resolved_bursts)`. `resolved_bursts` is
    `bursts` with `.role` and `.kept` filled in for every burst — callers
    persist only the ones with `.kept == True` (§7.4); the artifact is
    `None` when the thread classifies as `noise` or confidence < 0.3, and
    callers must not index it, but the bursts are still returned so the
    dirty-thread accounting in §7.5 has something to diff against.
    """
    if not msgs:
        raise DistillFailure("", "empty thread")

    thread_id = msgs[0].thread_id or msgs[0].doc_id
    try:
        raw = call_json(llm_call, "distill", _SYSTEM_PROMPT, _build_user_prompt(msgs))
    except LLMError as exc:
        raise DistillFailure(thread_id, str(exc)) from exc
    if not isinstance(raw, dict):
        raise DistillFailure(thread_id, f"expected a JSON object, got {type(raw).__name__}")

    role_by_ext_id: dict[str, str] = {}
    for entry in raw.get("message_roles") or []:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry["index"])
        except (KeyError, TypeError, ValueError):
            continue
        role = str(entry.get("role") or "").strip()
        if role and 0 <= idx < len(msgs):
            role_by_ext_id[msgs[idx].external_id] = role

    resolved_bursts: list[Burst] = []
    for b in bursts:
        member_roles = [role_by_ext_id[eid] for eid in b.message_external_ids if eid in role_by_ext_id]
        updated = b.model_copy(update={"role": _majority_role(member_roles)})
        updated.kept = keep_burst(updated, df)
        resolved_bursts.append(updated)

    artifact_class = str(raw.get("artifact_class") or "noise").strip().lower()
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    if artifact_class == "noise" or confidence < _MIN_CONFIDENCE:
        return None, resolved_bursts

    actors_raw = raw.get("actors")
    actors = [a for a in actors_raw if isinstance(a, dict)] if isinstance(actors_raw, list) else []
    systems = [str(s) for s in (raw.get("systems") or []) if isinstance(s, (str, int, float))]
    code_refs = [str(c) for c in (raw.get("code_refs") or []) if isinstance(c, (str, int, float))]

    timestamps = [m.timestamp for m in msgs if m.timestamp is not None]
    artifact_ts = max(timestamps) if timestamps else None

    question = str(raw.get("question") or "").strip()
    if not question:
        raise DistillFailure(thread_id, "LLM returned an empty question")

    artifact = ThreadArtifact(
        artifact_id=build_artifact_id(msgs[0].source_type, thread_id),
        thread_id=thread_id,
        source_type=msgs[0].source_type,
        container=msgs[0].container,
        question=question,
        summary=str(raw.get("summary") or "").strip(),
        resolution=(str(raw["resolution"]).strip() if raw.get("resolution") else None),
        resolved=bool(raw.get("resolved", False)),
        systems=systems,
        code_refs=code_refs,
        actors=actors,
        artifact_class=artifact_class,
        supersedes=(str(raw["supersedes"]).strip() if raw.get("supersedes") else None),
        confidence=confidence,
        timestamp=artifact_ts,
        source_message_ids=[m.external_id for m in msgs],
    )
    return artifact, resolved_bursts


@dataclass(frozen=True)
class RedistillDiff:
    """§7.5's three buckets for a dirty thread's new kept-set vs its prior
    one. `to_upsert` covers both brand-new bursts and previously-kept bursts
    whose text changed; `unchanged` bursts are left alone entirely."""

    to_upsert: list[str] = field(default_factory=list)
    to_delete: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


def diff_kept_set(
    new_bursts: list[Burst],
    prior_kept_ids: set[str],
    prior_text_by_id: dict[str, str],
) -> RedistillDiff:
    """Compare a re-distilled thread's newly-kept bursts against the
    previously-kept set (from `thread_state`, §7.5) and say exactly what
    changed, so a re-distill touches only what moved rather than rewriting
    the whole thread every time one message changes.
    """
    kept_now = {b.burst_id: b for b in new_bursts if b.kept}
    to_upsert: list[str] = []
    unchanged: list[str] = []
    for burst_id, b in kept_now.items():
        if burst_id not in prior_kept_ids or prior_text_by_id.get(burst_id) != b.text:
            to_upsert.append(burst_id)
        else:
            unchanged.append(burst_id)
    to_delete = [burst_id for burst_id in prior_kept_ids if burst_id not in kept_now]
    return RedistillDiff(to_upsert=to_upsert, to_delete=to_delete, unchanged=unchanged)


__all__ = [
    "DistillFailure",
    "distill_thread",
    "RedistillDiff",
    "diff_kept_set",
]
