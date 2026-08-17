"""Canonical data models shared by every adapter, the distiller, and the
store (§5). Everything downstream keys off `doc_id` -- adapters build it with
`build_doc_id`/`build_artifact_id`/`build_code_doc_id` below rather than
constructing the string inline, so the one rule that matters project-wide
(never content-hash it; content changes on supersession/re-distill and a
content hash would orphan every edge pointing at the old id) has exactly one
place to get wrong.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

_SLUG_DISALLOWED = re.compile(r"[^a-z0-9_.-]+")


def slug(value: str) -> str:
    """Lowercase, keep `[a-z0-9_.-]`, collapse everything else to `_`."""
    return _SLUG_DISALLOWED.sub("_", value.lower()).strip("_") or "_"


def build_doc_id(source_type: str, external_id: str) -> str:
    return f"{source_type}__{slug(external_id)}"


def build_artifact_id(source_type: str, thread_id: str) -> str:
    return f"art__{source_type}__{slug(thread_id)}"


def build_code_doc_id(source_type: str, path: str, index: int) -> str:
    return f"{source_type}__code_{slug(path)}_c{index}"


def compute_content_hash(title: str, body: str) -> str:
    """sha256(title + "\\n" + body). Change detection only — never an identity."""
    return hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()


def period_of(ts: datetime | None) -> str:
    if ts is None:
        return "unknown"
    return f"{ts.year}Q{(ts.month - 1) // 3 + 1}"


def _require_tz_aware(value: datetime | None) -> datetime | None:
    """§6's guardrail: pass tz-aware datetimes or None, never a raw string --
    burst gaps and `period_of` break quietly on naive datetimes rather than
    raising, so this is enforced here instead of trusted to every caller."""
    if value is not None and value.tzinfo is None:
        raise ValueError(
            f"datetime {value!r} is naive; use fromtimestamp(x, timezone.utc) "
            "or fromisoformat with an offset"
        )
    return value


class CanonicalDoc(BaseModel):
    doc_id: str  # stable id, the cross-store join key -- see build_doc_id
    source_type: str  # slack|gmail|linear|jira|confluence|gdrive|github|hubspot|fireflies
    external_id: str  # provider-native id of THIS item
    title: str
    body: str
    extra: dict[str, Any] = Field(default_factory=dict)
    author_raw: str | None = None  # RAW handle -- resolution happens in §9
    participants_raw: list[str] = Field(default_factory=list)
    container: str | None = None  # channel/project/space/repo/mailbox/pipeline
    url: str | None = None
    timestamp: datetime | None = None  # tz-aware or None, never a raw string
    thread_id: str | None = None
    parent_id: str | None = None
    linked_ids: list[str] = Field(default_factory=list)
    # lifecycle — how joel knows what changed without re-reading everything
    content_hash: str = ""  # sha256(title+"\n"+body); CHANGE DETECTION ONLY
    ingested_via: str = "sync"  # sync | backfill | live
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    # filled by later phases
    actor_id: str | None = None
    artifact_class: str = "document"
    validity: str = "current"
    granularity: str = "document"  # artifact|burst|document|record|code
    resolved: str = "na"

    _check_timestamp = field_validator("timestamp")(_require_tz_aware)
    _check_first_seen = field_validator("first_seen")(_require_tz_aware)
    _check_last_seen = field_validator("last_seen")(_require_tz_aware)


class Burst(BaseModel):
    burst_id: str  # f"{thread_id}_b{n}"
    thread_id: str
    author_raw: str
    text: str
    message_external_ids: list[str]
    start_ts: datetime
    end_ts: datetime
    has_reactions: bool = False
    role: str | None = None  # question|answer|context|resolution|noise (from distiller)
    kept: bool = False

    _check_start_ts = field_validator("start_ts")(_require_tz_aware)
    _check_end_ts = field_validator("end_ts")(_require_tz_aware)


class ThreadArtifact(BaseModel):
    artifact_id: str  # f"art__{source_type}__{slug(thread_id)}"
    thread_id: str
    source_type: str
    container: str | None
    question: str
    summary: str
    resolution: str | None
    resolved: bool
    systems: list[str]
    code_refs: list[str]  # VERBATIM identifiers -- exact-match fuel
    actors: list[dict]  # [{"name": raw, "role": "asker|resolver|participant"}]
    artifact_class: str
    supersedes: str | None
    confidence: float
    timestamp: datetime | None
    source_message_ids: list[str]

    _check_timestamp = field_validator("timestamp")(_require_tz_aware)

    def normalized_body(self) -> str:
        # question first (queries are question-shaped), verbatim refs last (BM25 fuel)
        parts = [f"Q: {self.question}", f"Summary: {self.summary}"]
        if self.resolution:
            parts.append(f"Resolution: {self.resolution}")
        if self.systems:
            parts.append("Systems: " + ", ".join(self.systems))
        if self.code_refs:
            parts.append("Refs: " + ", ".join(self.code_refs))
        return "\n".join(parts)


__all__ = [
    "CanonicalDoc",
    "Burst",
    "ThreadArtifact",
    "slug",
    "build_doc_id",
    "build_artifact_id",
    "build_code_doc_id",
    "compute_content_hash",
    "period_of",
]
