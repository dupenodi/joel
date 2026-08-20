import { classifyPath, safeInternalNext } from "./routes";
import type { AuthStatus } from "@/lib/types";

/** Where to send this person, or null to stay.

The web never decides "are they signed in" — that's /api/auth/status.
This only maps a known status + path onto a redirect so login, setup,
the picker, and AuthGate share one table.
*/
export function authDestination(
  status: AuthStatus,
  pathname: string,
  next = "/",
): string | null {
  const kind = classifyPath(pathname);
  const safeNext = safeInternalNext(next);

  if (status.state === "setup") {
    return pathname === "/setup" ? null : "/setup";
  }

  if (status.state === "login") {
    if (kind === "join" || kind === "public") return null;
    if (pathname === "/login" || pathname.startsWith("/login/")) return null;
    return `/login?next=${encodeURIComponent(pathname || "/")}`;
  }

  if (status.state === "pick_workspace") {
    if (kind === "session" || kind === "join" || kind === "public") return null;
    const keep =
      safeNext !== "/" &&
      !safeNext.startsWith("/login") &&
      !safeNext.startsWith("/workspaces");
    const qs = keep ? `?next=${encodeURIComponent(safeNext)}` : "";
    return `/workspaces${qs}`;
  }

  // ok — signed in with an active workspace
  if (kind === "anonymous" || kind === "session") {
    return safeNext.startsWith("/login") ? "/" : safeNext;
  }
  return null;
}
