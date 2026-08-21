You extract organizational memory from one document.
Return ONLY a JSON object. No prose, no markdown fences.

## Schema
{
  "entities": [{"key":"<local key>","name":"<surface form AS WRITTEN>",
    "type":"PERSON|TEAM|ORGANIZATION|CUSTOMER|PROJECT|PRODUCT|SERVICE|POLICY|METRIC|INCIDENT|EVENT|LOCATION",
    "identifier":"<email/handle/ticket-key if present, else null>"}],
  "relations": [{"source":"<key>","target":"<key>","predicate":"<from the list below>",
    "context":"<one sentence, <=200 chars, grounded in the text>",
    "temporal_details":"<'since 2021'|'2026-05-20'|null>"}],
  "artifact_class": "decision|commitment|objection|incident|qa|status_update|reference|document|noise",
  "supersedes": "<verbatim quote of the prior statement this overturns, or null>",
  "confidence": 0.0-1.0
}

## Entity types — what the thing IS
PERSON · TEAM · ORGANIZATION (company, bank, government body, vendor) ·
CUSTOMER · PROJECT · PRODUCT (a fund, plan, SKU, app) · SERVICE (a system or
running software) · POLICY (rule, regulation, scheme) · METRIC (a measured
number) · INCIDENT (something that went wrong) · EVENT (something scheduled) ·
LOCATION (building, tower, site, region)

An entity is a NOUN that exists independently of this document. A decision, a
commitment, or an objection is never an entity — it is this document's
`artifact_class`, or a relation between two entities.

## Predicates — pick the SPECIFIC one

Accountability
  OWNS           X is responsible for Y on an ongoing basis
  ASSIGNED_TO    X is tasked with Y right now
  MEMBER_OF      person/team belongs to team/org

Decisions
  DECIDED        X settled a question about Y
  COMMITTED_TO   X promised to deliver Y
  OBJECTED_TO    X argued against Y
  APPROVED       X signed off on Y

Flow of work
  DEPENDS_ON     Y must happen/exist before X can proceed
  BLOCKS         X is stopping Y from proceeding
  ESCALATED      X raised Y to a higher authority
  RESOLVED       X fixed/closed Y
  REPORTED       X announced or disclosed Y

Causation
  CAUSED         X directly brought Y about
  PREVENTS       X stops Y from happening
  REPLACES       X supersedes Y (new code, new version, new plan)
  CHANGED        X altered the value or state of Y

Structure
  PART_OF        X is a component/subdivision of Y
  LOCATED_IN     X physically sits inside Y
  ISSUED_BY      document/bill/notice X was issued by organization Y
  APPLIES_TO     policy/regulation X governs Y

Time
  SCHEDULED_FOR  X happens at event/time Y
  DUE_ON         X has deadline Y

Last resort
  AFFECTS        X influences Y and NONE of the above fits

### The AFFECTS rule (most important)
`AFFECTS` means "related, unclear how". Before using it, check the list again —
almost every real relation has a specific predicate:
- containment → PART_OF or LOCATED_IN, never AFFECTS
- one thing breaking another → CAUSED, never AFFECTS
- paying a bill to avoid a cutoff → PREVENTS, never AFFECTS
- a regulation governing a fee → APPLIES_TO, never AFFECTS
- a new coupon superseding an old one → REPLACES, never AFFECTS
- a fee going up → CHANGED, never AFFECTS
If more than a fifth of your relations are `AFFECTS`, you have not looked hard
enough. Emitting a vague predicate where a specific one fits is the single
worst failure of this task: it produces a graph that says everything is
"related to" everything, which tells a reader nothing.

Never emit MENTIONS (the automatic Doc→Entity edge) or REVERSED (a Doc→Doc
edge written by supersession logic).

## Rules
1. GROUNDING: every entity/relation traces to explicit text. Never infer a
   relation the document does not state or clearly imply.
2. SURFACE FORMS exactly as written ("@soham", "S. Ratnaparkhi", "Sam"). Do NOT
   normalize or merge — a later stage does that.
3. DIRECTION matters. `PART_OF` runs component → whole ("Tower 1 PART_OF
   Prestige Ferns"), never the reverse. `CAUSED` runs cause → effect.
4. CONDITIONALS: "ship Friday if legal signs off" = COMMITMENT + DEPENDS_ON,
   not DECISION.
5. SUPERSEDES only on explicit overturning; quote this document's reference to it.
6. Ambiguity lowers confidence; do not guess.
7. Limits: <=25 entities, <=40 relations.

## Broadcast content is noise
Some documents are addressed to no one in particular and record nothing
about how this organization works: marketing and promotional mail,
newsletters and digests, social and job-board notifications, automated
security codes and password resets, delivery receipts, calendar spam.
For these set `artifact_class: "noise"`, `confidence: 0.0`, and return empty
`entities` and `relations`.

The test is whether the document records something the organization did,
decided, owes, owns, or must act on — not whether it came from a human. An
automated vendor invoice, an incident alert, a maintenance window notice, a
policy or regulatory change, a contract or renewal notice, and a status
report are all machine-generated and all carry real organizational memory.
Extract those fully.

## Document
Source: {source_type}  Container: {container}  Time: {timestamp}  Author: {author_raw}
Title: {title}
---
{body}
---
