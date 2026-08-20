/** Route kinds for the session cookie gate.

  public     — marketing, static assets
  anonymous  — login / setup (bounce away once signed in)
  join       — invite link; cookie optional
  session    — picker; cookie required, org optional
  onboarding — optional setup rail; needs an actor
  product    — the app; needs an actor

Next middleware uses the cookie coarsely. AuthGate still asks /api/auth/status
because a cookie is not a valid session and is not an active workspace.
SSO / magic-link later: add a kind, don't scatter redirects.
*/
export const SESSION_COOKIE = "joel_session";

export type RouteKind =
  | "public"
  | "anonymous"
  | "join"
  | "session"
  | "onboarding"
  | "product";

const ANONYMOUS = new Set(["/login", "/setup"]);
const SESSION = new Set(["/workspaces"]);
const OAUTH_HTTP = new Set([
  "/authorize",
  "/token",
  "/register",
  "/revoke",
]);

export function classifyPath(pathname: string): RouteKind {
  if (pathname === "/join" || pathname.startsWith("/join/")) return "join";
  if (ANONYMOUS.has(pathname) || pathname.startsWith("/login/")) {
    return "anonymous";
  }
  if (SESSION.has(pathname)) return "session";
  if (pathname === "/onboarding" || pathname.startsWith("/onboarding/")) {
    return "onboarding";
  }
  if (
    pathname.startsWith("/brand-kit") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/.well-known/oauth-") ||
    pathname === "/mcp" ||
    pathname.startsWith("/mcp/") ||
    OAUTH_HTTP.has(pathname)
  ) {
    return "public";
  }
  return "product";
}

/** Login `next` and workspace-switch `next`. Reject protocol-relative URLs. */
export function safeInternalNext(
  raw: string | null | undefined,
  fallback = "/",
): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return fallback;
  return raw;
}

export function pathAfterWorkspaceSwitch(pathname: string): string {
  const path = pathname.split("?")[0] || "/";
  if (path === "/" || path.startsWith("/?")) return "/";
  return path;
}

export function slugPreview(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  if (slug.length >= 3) return slug;
  return slug ? `${slug}-ws` : "";
}
