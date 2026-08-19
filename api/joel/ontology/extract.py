"""§9.1 — extract organizational memory (entities + relations) from one
document. Runs once per `ThreadArtifact` for threads (shorter, noise-free —
the raw chatter never gets its own extraction pass) and once per singleton
document for everything that isn't threaded (Confluence pages, Drive files,
HubSpot records, GitHub code chunks, ...).

For thread-sourced docs, distillation's own `artifact_class`/`supersedes`
already won (§7.2's note) — callers pass those through unchanged and only
use this module's `entities`/`relations`. `EXTRACT_VALID_ETYPES` intentionally
excludes DECISION/COMMITMENT/OBJECTION/DOCUMENT — §9.1 rule 3 is explicit
that those are never entities, only a document's artifact_class or a
relation between two real entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from joel.llm import LLMCallFn, LLMError, call_json

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "extract_ontology.md"
_SYSTEM_PROMPT = (
    "Follow the user's instructions exactly. Return ONLY valid JSON — no prose, "
    "no markdown fences."
)
_STAGE = "extract"
_MAX_BODY_CHARS = 6000  # documents can run long; the prompt only needs enough to ground extraction
_MIN_CONFIDENCE = 0.3  # same floor distill_thread.py uses — ambiguity lowers confidence, don't guess

EXTRACT_VALID_ETYPES = frozenset(
    {"PERSON", "TEAM", "PROJECT", "CUSTOMER", "SERVICE", "POLICY", "METRIC", "INCIDENT"}
)
# §4.2's Entity→Entity edge set, plus AFFECTS/RESOLVED which §9.1 rule 4 also allows.
EXTRACT_VALID_PREDICATES = frozenset(
    {
        "OWNS",
        "DECIDED",
        "COMMITTED_TO",
        "OBJECTED_TO",
        "DEPENDS_ON",
        "BLOCKS",
        "ASSIGNED_TO",
        "REPORTED",
        "ESCALATED",
        "APPROVED",
        "RESOLVED",
        "AFFECTS",
    }
)


class ExtractFailure(RuntimeError):
    def __init__(self, doc_id: str, reason: str):
        super().__init__(f"extraction failed for doc {doc_id!r}: {reason}")
        self.doc_id = doc_id
        self.reason = reason


@dataclass(frozen=True)
class ExtractInput:
    """What extraction needs from either a `ThreadArtifact` or a singleton
    `CanonicalDoc` — the two callers build this, this module doesn't know
    their field names (same seam shape as `store_sql.py`'s `StoreDoc`)."""

    doc_id: str
    source_type: str
    container: str | None
    timestamp: str | None  # ISO or None
    author_raw: str | None
    title: str
    body: str


@dataclass(frozen=True)
class ExtractedEntity:
    key: str  # local key, scoped to this one extraction call
    name: str
    etype: str
    identifier: str | None


@dataclass(frozen=True)
class ExtractedRelation:
    source: str  # local key
    target: str  # local key
    predicate: str
    context: str
    temporal_details: str | None


@dataclass(frozen=True)
class ExtractionResult:
    doc_id: str
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    artifact_class: str = "noise"
    supersedes: str | None = None
    confidence: float = 0.0


def _build_user_prompt(doc: ExtractInput) -> str:
    template = _PROMPT_PATH.read_text()
    body = doc.body[:_MAX_BODY_CHARS]
    return (
        template.replace("{source_type}", doc.source_type)
        .replace("{container}", doc.container or "unknown")
        .replace("{timestamp}", doc.timestamp or "unknown")
        .replace("{author_raw}", doc.author_raw or "unknown")
        .replace("{title}", doc.title)
        .replace("{body}", body)
    )


def extract_ontology(llm_call: LLMCallFn, doc: ExtractInput) -> ExtractionResult:
    """One extraction call. Returns an `ExtractionResult` with `confidence`
    below `_MIN_CONFIDENCE` or `artifact_class == "noise"` still populated —
    callers (the ontology pipeline) decide whether that's enough to skip
    writing edges, mirroring `distill_thread`'s own noise/confidence gate
    rather than silently dropping the doc here where a caller can't tell
    "nothing extracted" from "extraction never ran"."""
    try:
        raw = call_json(llm_call, _STAGE, _SYSTEM_PROMPT, _build_user_prompt(doc))
    except LLMError as exc:
        raise ExtractFailure(doc.doc_id, str(exc)) from exc
    if not isinstance(raw, dict):
        raise ExtractFailure(doc.doc_id, f"expected a JSON object, got {type(raw).__name__}")

    local_keys: set[str] = set()
    entities: list[ExtractedEntity] = []
    for item in (raw.get("entities") or [])[:25]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        name = str(item.get("name") or "").strip()
        etype = str(item.get("type") or "").strip().upper()
        if not key or not name or etype not in EXTRACT_VALID_ETYPES:
            continue
        identifier = item.get("identifier")
        entities.append(
            ExtractedEntity(
                key=key,
                name=name,
                etype=etype,
                identifier=str(identifier).strip() if identifier else None,
            )
        )
        local_keys.add(key)

    relations: list[ExtractedRelation] = []
    for item in (raw.get("relations") or [])[:40]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        predicate = str(item.get("predicate") or "").strip().upper()
        # Grounding: a relation whose endpoints weren't declared as entities,
        # or whose predicate isn't one §9.1 rule 4 allows (MENTIONS/REVERSED
        # are written elsewhere, never asserted directly), doesn't get
        # silently coerced — it's dropped, same spirit as distill's roles.
        if source not in local_keys or target not in local_keys:
            continue
        if predicate not in EXTRACT_VALID_PREDICATES:
            continue
        context = str(item.get("context") or "").strip()[:200]
        temporal = item.get("temporal_details")
        relations.append(
            ExtractedRelation(
                source=source,
                target=target,
                predicate=predicate,
                context=context,
                temporal_details=str(temporal).strip() if temporal else None,
            )
        )

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return ExtractionResult(
        doc_id=doc.doc_id,
        entities=entities,
        relations=relations,
        artifact_class=str(raw.get("artifact_class") or "noise").strip().lower(),
        supersedes=(str(raw["supersedes"]).strip() if raw.get("supersedes") else None),
        confidence=confidence,
    )


__all__ = [
    "ExtractFailure",
    "ExtractInput",
    "ExtractedEntity",
    "ExtractedRelation",
    "ExtractionResult",
    "EXTRACT_VALID_ETYPES",
    "EXTRACT_VALID_PREDICATES",
    "extract_ontology",
    "_MIN_CONFIDENCE",
]
