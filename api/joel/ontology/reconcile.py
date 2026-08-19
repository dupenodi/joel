"""§9.3 conflict/supersession + §9.4 incremental reconciliation.

A "claim" is one document asserting one (entity, predicate) fact. Validity
lives on the `:Doc`/`docs` row — the same `validity` flag §10.2's
`needs_current_only` mask and every other lane already filter on — so
reconciliation never touches the ontology edge itself; it flips the LOSING
claim's document to `validity='superseded'` in both SQLite and the graph
and records `(:Doc)-[:REVERSED {ts}]->(:Doc)` from winner to loser. Nothing
downstream of this module needs to change to respect a flip — the masks
already honor it.

§9.4 bounds this to the touched `(entity_id, predicate)` pairs from this
sync's extractions, each reconciled against EVERY current claim on that
pair (not just this sync's), which is why `reconcile_touched_pairs` in
`ontology/pipeline.py` re-reads the graph rather than diffing in memory.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from joel.store import HydraStore

FORMAL_SOURCE_TYPES = frozenset({"confluence", "gdrive"})
FORMAL_DOC_TYPES = frozenset({"runbook", "spec", "policy"})
_AUTHORITY_LADDER = (
    "confluence",
    "gdrive",
    "jira",
    "linear",
    "fireflies",
    "gmail",
    "slack",
    "hubspot",
)
REVERSED = "REVERSED"


@dataclass(frozen=True)
class Claim:
    doc_id: str
    source_type: str
    doc_type: str | None
    ts: str | None  # ISO — None sorts as "no evidence either way" for the timestamp rule
    confidence: float


@dataclass(frozen=True)
class ReconciliationDecision:
    winner_doc_id: str
    loser_doc_ids: tuple[str, ...]
    unresolved_doc_ids: tuple[str, ...]
    rule: str
    entity_key: str = ""
    predicate: str = ""


def authority_rank(source_type: str) -> int:
    """Lower is more authoritative. Unknown sources sort last, never first —
    an unrecognized source_type should never outrank a documented one."""
    try:
        return _AUTHORITY_LADDER.index(source_type)
    except ValueError:
        return len(_AUTHORITY_LADDER)


def _is_formal(claim: Claim) -> bool:
    return claim.source_type in FORMAL_SOURCE_TYPES and (claim.doc_type or "") in FORMAL_DOC_TYPES


def _beats(challenger: Claim, incumbent: Claim, *, explicit_supersedes: bool) -> tuple[str, str]:
    """§9.3's precedence ladder, applied to one (challenger, incumbent)
    pair. Returns ('challenger'|'incumbent'|'tie', rule_name)."""
    if explicit_supersedes:
        return "challenger", "explicit_supersedes"

    if challenger.ts and incumbent.ts and challenger.ts != incumbent.ts:
        later, earlier = (
            (challenger, incumbent) if challenger.ts > incumbent.ts else (incumbent, challenger)
        )
        if _is_formal(earlier) and not _is_formal(later) and later.confidence < 0.7:
            winner = "incumbent" if earlier is incumbent else "challenger"
            return winner, "formal_doc_outranks_low_confidence_chat"
        winner = "challenger" if later is challenger else "incumbent"
        return winner, "later_timestamp"

    ra, rb = authority_rank(challenger.source_type), authority_rank(incumbent.source_type)
    if ra < rb:
        return "challenger", "source_authority"
    if rb < ra:
        return "incumbent", "source_authority"
    return "tie", "unresolvable"


def reconcile_claim(
    candidate: Claim,
    existing: list[Claim],
    *,
    explicit_supersedes: bool,
    entity_key: str = "",
    predicate: str = "",
) -> list[ReconciliationDecision]:
    """One decision per existing claim on this (entity, predicate) pair —
    a candidate can beat one prior claim and tie another in the same pass,
    per §9.4's "reconcile across the whole set" instruction."""
    decisions: list[ReconciliationDecision] = []
    for other in existing:
        if other.doc_id == candidate.doc_id:
            continue
        winner, rule = _beats(candidate, other, explicit_supersedes=explicit_supersedes)
        if winner == "challenger":
            decisions.append(
                ReconciliationDecision(candidate.doc_id, (other.doc_id,), (), rule, entity_key, predicate)
            )
        elif winner == "incumbent":
            decisions.append(
                ReconciliationDecision(other.doc_id, (candidate.doc_id,), (), rule, entity_key, predicate)
            )
        else:
            decisions.append(
                ReconciliationDecision(candidate.doc_id, (), (other.doc_id,), rule, entity_key, predicate)
            )
    return decisions


def apply_decisions(
    conn: sqlite3.Connection,
    hydra_store: HydraStore,
    decisions: list[ReconciliationDecision],
    *,
    now: str,
    conflicts_path: Path,
) -> list[str]:
    """Flip every loser to superseded (SQLite + graph), write the
    `:REVERSED` edge, and log unresolved ties. Returns the doc_ids actually
    flipped this call, so callers can also refresh `LiveIndex`/the vector
    metadata mask for them (validity is one of `_vector_mask`'s filters)."""
    flipped: list[str] = []
    for decision in decisions:
        for loser_id in decision.loser_doc_ids:
            conn.execute("UPDATE docs SET validity='superseded' WHERE id=?", (loser_id,))
            hydra_store.set_property("Doc", loser_id, "validity", "superseded")
            hydra_store.create_edge("Doc", decision.winner_doc_id, REVERSED, "Doc", loser_id, ts=now)
            flipped.append(loser_id)
        if decision.unresolved_doc_ids:
            _log_conflict(conflicts_path, decision, now)
    return flipped


def _log_conflict(path: Path, decision: ReconciliationDecision, now: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text() or "[]")
        except json.JSONDecodeError:
            existing = []
    existing.append(
        {
            "entity_key": decision.entity_key,
            "predicate": decision.predicate,
            "doc_ids": [decision.winner_doc_id, *decision.unresolved_doc_ids],
            "rule": decision.rule,
            "logged_at": now,
        }
    )
    path.write_text(json.dumps(existing, indent=2))


__all__ = [
    "Claim",
    "ReconciliationDecision",
    "authority_rank",
    "reconcile_claim",
    "apply_decisions",
    "FORMAL_SOURCE_TYPES",
    "FORMAL_DOC_TYPES",
    "REVERSED",
]
