Decide whether two name mentions refer to the SAME real person/entity.
Return ONLY JSON: {"same": true|false, "confidence": 0.0-1.0, "reason": "<=120 chars"}

Evidence:
A: "{a_name}"  contexts: {a_ctx}  identifiers: {a_ids}
B: "{b_name}"  contexts: {b_ctx}  identifiers: {b_ids}

Rules:
1. Matching identifiers (same email/user id) → same, confidence 0.95+.
2. CONFLICTING identifiers (two different emails, both present) → NOT same, even with
   identical names. Different people share names.
3. Nickname/initial form + overlapping containers + no conflicting identifier → likely same.
4. Same name, disjoint containers, no shared project, no identifier → insufficient
   evidence: false, LOW confidence. Do not guess.
5. Never merge a PERSON with a TEAM, SERVICE, or PROJECT.
6. Bias toward NOT merging: a false merge corrupts every downstream answer; a missed
   merge loses recall on one entity.
