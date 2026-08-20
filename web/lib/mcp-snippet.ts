export function mcpOrigin(windowOrigin: string, apiBase = ""): string {
  const origin = (apiBase || windowOrigin).replace(/\/$/, "");
  return origin;
}

export function mcpUrl(windowOrigin: string, apiBase = ""): string {
  return `${mcpOrigin(windowOrigin, apiBase)}/mcp/`;
}

export function mcpSnippet(url: string, key = "joel_sk_…"): string {
  return `{
  "mcpServers": {
    "joel": {
      "url": ${JSON.stringify(url)},
      "headers": {
        "Authorization": ${JSON.stringify(`Bearer ${key}`)}
      }
    }
  }
}`;
}
