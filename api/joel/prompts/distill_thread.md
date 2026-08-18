You distill one complete conversation thread into a structured knowledge artifact.

Return ONLY a JSON object. No prose, no markdown fences.

## Schema
{
  "message_roles": [{"index": <0-based>, "role": "question|answer|context|resolution|noise"}],
  "question": "<the question this thread ANSWERS, phrased as someone would ask it later>",
  "summary": "<what happened, <=2 sentences>",
  "resolution": "<the specific fix/decision/outcome, or null if unresolved>",
  "resolved": true|false,
  "systems": ["<components/projects/services touched>"],
  "code_refs": ["<identifiers VERBATIM: env vars, flags, error strings, ticket keys, fn names>"],
  "actors": [{"name": "<exactly as written>", "role": "asker|resolver|participant"}],
  "artifact_class": "decision|commitment|objection|incident|qa|status_update|noise",
  "supersedes": "<verbatim reference to the prior statement this overturns, or null>",
  "confidence": 0.0-1.0
}

## Rules
1. QUESTION: write the question a FUTURE reader would ask that this thread answers —
   not the first message verbatim. "Restore stalls after manifest load on the larger
   cluster" → "Why does restore stall after manifest load?" Future queries are
   questions; this line powers retrieval.
2. RESOLUTION is specific and actionable: "Set CKPT_PREFETCH=4 for the NFS mount",
   never "they fixed it". No concrete outcome → resolution null, resolved false.
   Do NOT invent closure.
3. ROLES: label every message.
   "context" = tangents/me-toos adding no durable knowledge
     ("My laptop also stalls when it sees Monday.")
   "noise" = greetings/acks/thanks ("sounds good, thanks! will try that")
   Context/noise contribute NOTHING to question/summary/resolution — use them only
   to disambiguate the real content.
4. CODE_REFS verbatim: CKPT_PREFETCH, ERR_MANIFEST_TIMEOUT, AUTH-123. Never
   paraphrase, lowercase, or translate — these power exact-match retrieval.
5. NAMES exactly as written ("@soham", "S. Ratnaparkhi"). Do NOT normalize or
   merge — a later stage does that.
6. CONDITIONALS: "we ship Friday if legal signs off" → class "commitment",
   resolution states the condition, resolved=false until confirmed in-thread.
7. SUPERSEDES only when the thread explicitly overturns a prior position
   ("actually let's not", "we're reverting X"). Quote how THIS thread refers to it.
8. Whole thread is chit-chat → artifact_class "noise" (it won't be indexed).
9. Ambiguity lowers confidence. Never resolve ambiguity by guessing.

## Thread
Source: {source_type}   Container: {container}   Items: {n}
---
