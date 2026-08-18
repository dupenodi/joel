"""Provider fetch + Composio auth.

  gate.py              allowlist (id, toolkit, ingest, lookback)
  composio_conn.py     hosted OAuth, proxy, and tool execution
  oauth.py             Fernet for stored account ids
  http.py              RequestFn, ProviderAPIError, tool_request
  slack/github/gmail   first-wave fetchers
  catalog.py           Linear, Notion, Drive, HubSpot (proxy)
  jira/confluence/fireflies  tool-execute fetchers (proxy routing fails)

Adapters live in `joel.adapters.manifests`.
"""
