Score how well each candidate helps ANSWER the question. Answering ≠ being about the topic.

Return ONLY JSON: [{"id":"...","score":0-10,"reason":"<=80 chars"}]

## Rules
1. States the fact/fix/decision the question asks for → 8-10.
2. Exact identifier overlap with question tokens → +2.
3. `granularity=artifact` with an on-point resolution outranks raw chatter
   covering the same topic.
4. Topically related but non-answering → <=3. Be harsh — this is THE failure
   mode; a system that ranks "about the topic" as "answers the question" is
   useless.
5. Question asks for CURRENT state and the candidate is old/likely superseded
   → cap at 4, reason "stale".
6. Score only what the snippet shows. Never invent facts not present in it.
7. Score EVERY candidate given, in the same order they were given, one entry
   each. Never skip one.

## Question
{question}

## Candidates
Each row: id · title · container (channel/repo/etc.) · granularity · ts · snippet (<=300 chars)
---
{candidates}
