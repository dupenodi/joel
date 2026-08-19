You extract organizational memory from one business document.
Return ONLY a JSON object. No prose, no markdown fences.

## Schema
{
  "entities": [{"key":"<local key>","name":"<surface form AS WRITTEN>",
    "type":"PERSON|TEAM|PROJECT|CUSTOMER|SERVICE|POLICY|METRIC|INCIDENT",
    "identifier":"<email/handle/ticket-key if present, else null>"}],
  "relations": [{"source":"<key>","target":"<key>","predicate":"<UPPER_SNAKE>",
    "context":"<one sentence, <=200 chars, grounded in the text>",
    "temporal_details":"<'since 2021'|'2026-05-20'|null>"}],
  "artifact_class": "decision|commitment|objection|incident|qa|status_update|reference|document|noise",
  "supersedes": "<verbatim quote of the prior statement this overturns, or null>",
  "confidence": 0.0-1.0
}

## Rules
1. GROUNDING: every entity/relation traces to explicit text. Never infer a relation
   the document does not state or clearly imply.
2. SURFACE FORMS exactly as written ("@soham", "S. Ratnaparkhi", "Sam"). Do NOT
   normalize or merge — a later stage does that.
3. ENTITY TYPE is what the thing IS (a person, team, project…), never what
   happened to it. A decision, commitment, or objection is never an entity —
   it's this document's artifact_class, or a relation between two entities below.
4. PREDICATES — prefer: OWNS, DECIDED, COMMITTED_TO, OBJECTED_TO, DEPENDS_ON, BLOCKS,
   ASSIGNED_TO, REPORTED, ESCALATED, APPROVED, RESOLVED, AFFECTS (§4.2's Entity→Entity
   edge set). Never emit MENTIONS (that's the automatic Doc→Entity edge, not something
   to extract) or REVERSED (that's a Doc→Doc edge written by supersession logic,
   never asserted directly by extraction).
5. CONDITIONALS: "ship Friday if legal signs off" = COMMITMENT + DEPENDS_ON, not DECISION.
6. SUPERSEDES only on explicit overturning; quote this document's reference to it.
7. Ambiguity lowers confidence; do not guess.
8. Limits: <=25 entities, <=40 relations.

## Document
Source: {source_type}  Container: {container}  Time: {timestamp}  Author: {author_raw}
Title: {title}
---
{body}
---
