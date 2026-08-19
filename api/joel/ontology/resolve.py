"""§9.2 — the 3-stage resolution funnel (cheap → expensive) that turns raw
extracted surface forms into a stable `:Entity` registry: blocking, then
fuzzy scoring, then an LLM tie-break for the ambiguous middle band, cached
forever by sorted pair so the same two names are never judged twice.

Registry persists to `data/entities/registry.json`
(`{entity_id: {canonical_name, type, identifier, aliases[], evidence{}}}`,
exactly §9.2's shape) and the LLM verdict cache to
`data/entities/resolve_cache.json`. Both are plain JSON, not SQLite —
entity identity is corpus-wide state the graph and the registry agree on
together, not a per-row index column.

Blocking here approximates §9.2's four keys (email local-part, metaphone of
last token, first-initial+last-name, container co-occurrence) with three of
them plus a fuzzy top-K prefilter standing in for metaphone, rather than
adding a phonetic-matching dependency for one blocking key — a mention that
metaphone blocking would have caught (a misspelled surname with no shared
container or identifier) still gets a shot via the fuzzy prefilter, just
scored instead of key-matched.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from joel.llm import LLMCallFn, LLMError, call_json

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "resolve_entity.md"
_SYSTEM_PROMPT = (
    "Follow the user's instructions exactly. Return ONLY valid JSON — no prose, "
    "no markdown fences."
)
_STAGE = "resolve"  # reuses the RESOLVE model alias, same as plan_query (§18)

AUTO_MERGE = 0.92
AUTO_REJECT = 0.55
_FUZZY_PREFILTER_LIMIT = 5
_FUZZY_PREFILTER_FLOOR = 55  # 0-100 rapidfuzz scale
_MAX_CONTEXTS = 10
_MAX_ALIASES_SCANNED_PER_TYPE = 2000  # guardrail, not expected to matter at this project's scale

_NON_WORD = re.compile(r"[^a-z0-9\s]+")
_WS = re.compile(r"\s+")


def norm(name: str) -> str:
    """Lowercase, strip a leading '@', collapse punctuation to spaces,
    collapse whitespace. `same as written` mentions differ only cosmetically
    ("@soham" vs "soham", "S.  Ratnaparkhi" vs "s ratnaparkhi") and this is
    the one place that normalization is allowed to happen (§9.1/§9.2 both
    insist surface forms stay verbatim everywhere upstream of here)."""
    text = name.strip().lstrip("@").lower()
    text = _NON_WORD.sub(" ", text)
    return _WS.sub(" ", text).strip()


def initials(name: str) -> str:
    return "".join(w[0] for w in norm(name).split() if w)


def email_localpart(identifier: str | None) -> str | None:
    if not identifier or "@" not in identifier:
        return None
    return identifier.split("@", 1)[0].strip().lower()


@dataclass(frozen=True)
class Mention:
    """One raw extracted surface form, ready to resolve against the
    registry. `container` is the doc's container (channel/project/...) —
    the resolution funnel's co-occurrence signal, not the entity's."""

    name: str
    etype: str
    identifier: str | None
    context: str
    container: str | None


@dataclass
class EntityRecord:
    entity_id: str
    canonical_name: str
    etype: str
    identifier: str | None
    aliases: list[str] = field(default_factory=list)  # lowercased surface forms
    evidence: dict[str, Any] = field(
        default_factory=lambda: {"contexts": [], "containers": []}
    )

    def to_json(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "type": self.etype,
            "identifier": self.identifier,
            "aliases": self.aliases,
            "evidence": self.evidence,
        }

    @staticmethod
    def from_json(entity_id: str, data: dict[str, Any]) -> "EntityRecord":
        return EntityRecord(
            entity_id=entity_id,
            canonical_name=data.get("canonical_name") or entity_id,
            etype=data.get("type") or "PERSON",
            identifier=data.get("identifier"),
            aliases=list(data.get("aliases") or []),
            evidence=dict(data.get("evidence") or {"contexts": [], "containers": []}),
        )


class EntityRegistry:
    """In-memory registry, explicitly loaded/saved — callers own the I/O
    boundary (same pattern as `distill/state.py`'s thread_state) so this
    class has zero SQLite/filesystem-locking concerns of its own."""

    def __init__(self) -> None:
        self.entities: dict[str, EntityRecord] = {}
        self._counters: dict[str, int] = {}

    @staticmethod
    def load(path: Path) -> "EntityRegistry":
        registry = EntityRegistry()
        if not path.exists():
            return registry
        data = json.loads(path.read_text() or "{}")
        for entity_id, payload in data.items():
            registry.entities[entity_id] = EntityRecord.from_json(entity_id, payload)
            etype = registry.entities[entity_id].etype
            prefix = f"{etype.lower()}_"
            if entity_id.startswith(prefix):
                try:
                    n = int(entity_id[len(prefix) :])
                    registry._counters[etype] = max(registry._counters.get(etype, 0), n)
                except ValueError:
                    pass
        return registry

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {eid: rec.to_json() for eid, rec in self.entities.items()}
        path.write_text(json.dumps(data, indent=2, sort_keys=True))

    def _next_id(self, etype: str) -> str:
        n = self._counters.get(etype, 0) + 1
        self._counters[etype] = n
        return f"{etype.lower()}_{n:04d}"

    def create(self, mention: Mention) -> str:
        entity_id = self._next_id(mention.etype)
        self.entities[entity_id] = EntityRecord(
            entity_id=entity_id,
            canonical_name=mention.name,
            etype=mention.etype,
            identifier=mention.identifier,
            aliases=[norm(mention.name)],
            evidence={
                "contexts": [mention.context] if mention.context else [],
                "containers": [mention.container] if mention.container else [],
            },
        )
        return entity_id

    def add_evidence(self, entity_id: str, mention: Mention) -> None:
        rec = self.entities[entity_id]
        alias = norm(mention.name)
        if alias and alias not in rec.aliases:
            rec.aliases.append(alias)
        if mention.identifier and not rec.identifier:
            rec.identifier = mention.identifier
        containers = rec.evidence.setdefault("containers", [])
        if mention.container and mention.container not in containers:
            containers.append(mention.container)
        contexts = rec.evidence.setdefault("contexts", [])
        if mention.context and len(contexts) < _MAX_CONTEXTS:
            contexts.append(mention.context)

    def blocking_candidates(self, mention: Mention) -> list[EntityRecord]:
        """§9.2.A: normalized-email local part, first-initial+last-name,
        container co-occurrence, plus a fuzzy top-K prefilter standing in
        for metaphone blocking (see module docstring)."""
        same_type = [
            r for r in self.entities.values() if r.etype == mention.etype
        ][:_MAX_ALIASES_SCANNED_PER_TYPE]
        if not same_type:
            return []
        matched: dict[str, EntityRecord] = {}

        mention_lp = email_localpart(mention.identifier)
        if mention_lp:
            for r in same_type:
                if email_localpart(r.identifier) == mention_lp:
                    matched[r.entity_id] = r

        mention_initials = initials(mention.name)
        if mention_initials:
            for r in same_type:
                if initials(r.canonical_name) == mention_initials:
                    matched[r.entity_id] = r

        if mention.container:
            for r in same_type:
                if mention.container in r.evidence.get("containers", []):
                    matched[r.entity_id] = r

        pool = {r.entity_id: r.canonical_name for r in same_type}
        for name, score, entity_id in process.extract(
            mention.name, pool, scorer=fuzz.token_set_ratio, limit=_FUZZY_PREFILTER_LIMIT
        ):
            if score >= _FUZZY_PREFILTER_FLOOR:
                matched[entity_id] = self.entities[entity_id]

        return list(matched.values())


def pair_score(
    a_name: str,
    a_identifier: str | None,
    a_containers: list[str],
    b_name: str,
    b_identifier: str | None,
    b_containers: list[str],
) -> float:
    """§9.2.B's formula, plus one guard the plan's pseudocode leaves
    implicit but `resolve_entity.md` rule 2 states outright: conflicting
    identifiers mean NOT the same entity even with an identical name. That
    has to be enforced here, before the auto-merge threshold, not only in
    the LLM prompt — two different people who happen to share a local part
    (sam@acme.com vs sam@other.com) would otherwise score high enough on
    name-similarity plus the local-part bonus alone to clear AUTO_MERGE and
    never reach the LLM tie-break at all."""
    if (
        a_identifier
        and b_identifier
        and a_identifier.strip().lower() != b_identifier.strip().lower()
    ):
        return 0.0
    na, nb = norm(a_name), norm(b_name)
    score = max(fuzz.token_set_ratio(na, nb), fuzz.partial_ratio(na, nb)) / 100
    if initials(na) == initials(nb) and initials(na):
        score += 0.10
    a_lp, b_lp = email_localpart(a_identifier), email_localpart(b_identifier)
    if a_lp and a_lp == b_lp:
        score += 0.35
    if len(set(a_containers) & set(b_containers)) >= 2:
        score += 0.08
    return min(score, 1.0)


def _llm_verdict(llm_call: LLMCallFn, mention: Mention, candidate: EntityRecord) -> dict[str, Any]:
    template = _PROMPT_PATH.read_text()
    user_prompt = (
        template.replace("{a_name}", mention.name)
        .replace("{a_ctx}", mention.context or "")
        .replace("{a_ids}", mention.identifier or "none")
        .replace("{b_name}", candidate.canonical_name)
        .replace("{b_ctx}", "; ".join(candidate.evidence.get("contexts", [])[:3]))
        .replace("{b_ids}", candidate.identifier or "none")
    )
    try:
        raw = call_json(llm_call, _STAGE, _SYSTEM_PROMPT, user_prompt)
    except LLMError:
        # §9.2.C rule 6: bias toward NOT merging — a failed judgment call
        # degrades to "insufficient evidence", never to a guessed merge.
        return {"same": False, "confidence": 0.0, "reason": "resolver LLM call failed"}
    if not isinstance(raw, dict):
        return {"same": False, "confidence": 0.0, "reason": "resolver returned non-object JSON"}
    return raw


def resolve_mention(
    registry: EntityRegistry,
    mention: Mention,
    *,
    llm_call: LLMCallFn | None,
    cache: dict[str, dict[str, Any]],
) -> str:
    """Return the entity_id `mention` resolves to, creating a new entity if
    nothing matches closely enough. Mutates `registry` in place; persistence
    is the caller's job (mirrors `distill/state.py`'s save-after-call shape).
    `cache` is keyed by `"sorted_norm_a||sorted_norm_b"` so the same pair of
    names is never sent to the LLM twice (§9.4's incremental-resolution
    rule) — callers load/save it alongside the registry.
    """
    candidates = registry.blocking_candidates(mention)
    best: EntityRecord | None = None
    best_score = 0.0
    for candidate in candidates:
        score = pair_score(
            mention.name,
            mention.identifier,
            [mention.container] if mention.container else [],
            candidate.canonical_name,
            candidate.identifier,
            candidate.evidence.get("containers", []),
        )
        if score > best_score:
            best, best_score = candidate, score

    entity_id: str | None = None
    if best is not None and best_score >= AUTO_MERGE:
        entity_id = best.entity_id
    elif best is not None and best_score >= AUTO_REJECT and llm_call is not None:
        key = "||".join(sorted([norm(mention.name), norm(best.canonical_name)]))
        verdict = cache.get(key)
        if verdict is None:
            verdict = _llm_verdict(llm_call, mention, best)
            cache[key] = verdict
        if verdict.get("same") and mention.etype == best.etype:
            entity_id = best.entity_id

    if entity_id is None:
        entity_id = registry.create(mention)
    else:
        registry.add_evidence(entity_id, mention)
    return entity_id


def load_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text() or "{}")


def save_cache(path: Path, cache: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True))


__all__ = [
    "AUTO_MERGE",
    "AUTO_REJECT",
    "Mention",
    "EntityRecord",
    "EntityRegistry",
    "norm",
    "initials",
    "email_localpart",
    "pair_score",
    "resolve_mention",
    "load_cache",
    "save_cache",
]
