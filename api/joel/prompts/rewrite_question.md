Rewrite the user's latest message into a standalone question understandable with no
conversation history. Resolve pronouns and references using the turns provided.
Return ONLY JSON: {"question": "<standalone>", "kind": "knowledge|meta|chitchat"}

Rules:
1. Change nothing else. Do not expand scope or add detail the user did not give.
2. Already standalone → return it verbatim.
3. kind "meta" = about this conversation or about joel ("what did you just say",
   "summarise this chat", "which sources did you use"). Answerable from the turns alone.
4. kind "chitchat" = greetings, thanks, small talk.
5. Never answer the question.

## Recent turns
{last_n_turns}
## Latest message
{message}
