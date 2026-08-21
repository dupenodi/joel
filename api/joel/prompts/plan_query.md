Classify a question against a company knowledge system and emit a retrieval plan.

Return ONLY JSON:
{
  "intent": "lookup|multihop|conflict|temporal|aggregate|absent_check|who|live",
  "entities": ["<names exactly as the question writes them>"],
  "exact_tokens": ["<identifiers/error strings/quoted phrases worth exact search, else []>"],
  "temporal": {"period": "<2026Q2|null>", "wants_history": true|false},
  "needs_current_only": true|false,
  "rewrites": ["<2 alternates varying VOCABULARY, not word order>"]
}

## Rules
1. exact_tokens = CAPS_SNAKE identifiers, error codes, quoted strings, ticket keys
   (e.g. `ERR_MANIFEST_TIMEOUT`, `AUTH-123`). Never invent one that isn't in the text.
2. intent "live" + needs_current_only true = the question wants RIGHT-NOW state from
   a connected tool. Memory is stale for these. Includes:
   - a named object ("is PR 118 merged", "latest in #eng")
   - the current set ("open GitHub PRs", "open issues", "anything new today")
   If it could change since the last sync, it is live — not lookup.
3. intent "who" = asks who did/knows/owns something.
4. intent "conflict" = asks to reconcile or notices two different claims.
5. intent "temporal" = explicitly a past state ("what did we decide in Q1").
6. intent "lookup" = a fact that already lives in memory (decisions, owners,
   how something works). Code or docs *about* a tool are lookup; the tool's
   current tickets/messages are live.
7. rewrites vary VOCABULARY only — never reorder the same words.
8. Never answer the question. Only plan how to retrieve for it.

## Question
{question}
