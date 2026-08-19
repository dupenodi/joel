# Visibility is one room stamp, not an ACL list

A document is written to the narrowest room it occurred in (`org`, `channel:slack:C…`, or `user:gmail:…`). Retrieval filters that one column. An ACL-of-principals table would let a doc belong to many rooms at once, which breaks the product rule that memory is written to exactly one place and that asking in public cannot see private-channel memory even indirectly.

Ask context is built by the server for the surface that received the question. A client-supplied room on `POST /api/ask` would let anyone claim a private Slack channel and read it.
