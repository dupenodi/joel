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
2. intent "live" = asks about RIGHT-NOW state of a connected tool ("latest message
   in #eng", "is PR 118 merged", "anything new today") — memory alone cannot
   answer these.
3. intent "who" = asks who did/knows/owns something.
4. intent "conflict" = asks to reconcile or notices two different claims.
5. intent "temporal" = explicitly asks about a past state ("what did we decide
   in Q1", "what was the plan before").
6. rewrites vary VOCABULARY only (synonyms, different phrasing of the same
   question) — never reorder the same words and call it a rewrite.
7. Never answer the question. Only plan how to retrieve for it.

## Question
{question}
