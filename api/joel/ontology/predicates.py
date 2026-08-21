"""The Entity→Entity edge vocabulary, in one place.

This used to live twice: `EXTRACT_VALID_PREDICATES` in `extract.py` (what the
model is allowed to emit) and `ONTOLOGY_PREDICATES` in `retrieve/lanes.py`
(what traversal walks). Two lists that must agree and had no mechanical
reason to are a standing invitation to drift — a predicate added to the
extractor but not the traversal set produces edges nothing can ever read.

## Why the set grew

The original twelve were all workplace-process verbs (OWNS, DECIDED,
ASSIGNED_TO…) with `AFFECTS` as the catch-all. On a real corpus that
catch-all swallowed everything: 15 of 34 extracted claims came back
`AFFECTS`, including ones with obvious specific meanings — "Tower 1 AFFECTS
Prestige Ferns Residency" is containment, "monkeys AFFECTS pipeline" is
causation, "payment AFFECTS interruption" is prevention. A predicate that
means "related somehow" carries almost no information, and a graph where
44% of edges are that predicate cannot be read.

The additions below are the specific relations that traffic was collapsing
into. `AFFECTS` survives as an explicit last resort so the model has
somewhere to put a genuine "influences, unclear how" — but the prompt now
makes it the option of last choice rather than the path of least
resistance.
"""

from __future__ import annotations

# Ordered roughly by how much a reader cares, since some UIs surface the
# first few; membership is what matters everywhere else.
ONTOLOGY_PREDICATES: tuple[str, ...] = (
    # -- accountability -------------------------------------------------
    "OWNS",
    "ASSIGNED_TO",
    "MEMBER_OF",
    # -- decisions and positions ---------------------------------------
    "DECIDED",
    "COMMITTED_TO",
    "OBJECTED_TO",
    "APPROVED",
    # -- flow of work ---------------------------------------------------
    "DEPENDS_ON",
    "BLOCKS",
    "ESCALATED",
    "RESOLVED",
    "REPORTED",
    # -- causation (was: AFFECTS) ---------------------------------------
    "CAUSED",
    "PREVENTS",
    "REPLACES",
    "CHANGED",
    # -- structure (was: AFFECTS/DEPENDS_ON) ----------------------------
    "PART_OF",
    "LOCATED_IN",
    "ISSUED_BY",
    "APPLIES_TO",
    # -- time -----------------------------------------------------------
    "SCHEDULED_FOR",
    "DUE_ON",
    # -- last resort ----------------------------------------------------
    "AFFECTS",
)

VALID_PREDICATES = frozenset(ONTOLOGY_PREDICATES)

# Entity types. ORGANIZATION/LOCATION/EVENT/PRODUCT were added alongside the
# predicates above for the same reason: without them a bank became a
# SERVICE, an apartment complex became a SERVICE, and a mutual fund became a
# METRIC, which made the type colouring on the graph meaningless.
ENTITY_TYPES: tuple[str, ...] = (
    "PERSON",
    "TEAM",
    "ORGANIZATION",
    "CUSTOMER",
    "PROJECT",
    "PRODUCT",
    "SERVICE",
    "POLICY",
    "METRIC",
    "INCIDENT",
    "EVENT",
    "LOCATION",
)

VALID_ETYPES = frozenset(ENTITY_TYPES)

__all__ = [
    "ONTOLOGY_PREDICATES",
    "VALID_PREDICATES",
    "ENTITY_TYPES",
    "VALID_ETYPES",
]
