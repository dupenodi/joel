import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE, classifyPath } from "@/lib/auth/routes";

/** Coarse cookie gate. Fine-grained status still lives in AuthGate.

Later: JWT claims, SSO callbacks, or a BFF can replace the cookie check
without touching page components.
*/
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const kind = classifyPath(pathname);
  const hasSession = request.cookies.has(SESSION_COOKIE);

  if ((kind === "product" || kind === "session" || kind === "onboarding") && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    if (pathname !== "/") {
      url.searchParams.set("next", pathname);
    }
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|brand-kit/|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
