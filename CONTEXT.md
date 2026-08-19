# Joel

A self-hostable company brain: connected tools become shared memory, and answers are always scoped to who is asking and from where.

## Language

**Workspace**:
The one organization this install serves. Still the `orgs` row.
_Avoid_: tenant, org (as a product noun), company account

**Actor**:
A signed-in member of the workspace, with a role of admin or member.
_Avoid_: user (except as the table/id), account, owner

**Room**:
The place a document was written, or the place a question is being asked. Exactly one of: workspace-public, a private channel, or one person's desk.
_Avoid_: container, ACL, permission set, knowledge base

**Visibility**:
The room stamp stored on a document at ingest. Retrieval filters it; it is never inferred at query time.
_Avoid_: ACL, permission, access tag, containerTag

**Ask context**:
Who is asking and which room they are asking from. Built by the server for that surface (web, Slack, MCP). The client does not choose the readable set.
_Avoid_: session, query scope, authz context
