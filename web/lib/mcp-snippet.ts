export function mcpOrigin(windowOrigin: string, apiBase = ""): string {
  const origin = (apiBase || windowOrigin).replace(/\/$/, "");
  return origin;
}

export function mcpUrl(windowOrigin: string, apiBase = ""): string {
  return `${mcpOrigin(windowOrigin, apiBase)}/mcp`;
}

/** URL-only config. Cursor/Claude sign in via OAuth on this origin. */
export function mcpSnippet(url: string): string {
  return `{
  "mcpServers": {
    "joel": {
      "url": ${JSON.stringify(url)}
    }
  }
}`;
}

/** Same URL plus a minted API key, for clients that cannot do OAuth. */
export function mcpKeySnippet(url: string, key: string): string {
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
