import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, sessionEmail } from "@/lib/accounts";

// The site is private: every page and the /api it forwards needs an approved account.
export function proxy(request: NextRequest) {
  if (sessionEmail(request.cookies.get(SESSION_COOKIE)?.value)) return NextResponse.next();
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ detail: "Sign in to use EnerZen." }, { status: 401 });
  }
  return NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  // Everything but the sign-in page and what it needs to render.
  matcher: ["/((?!login|_next/static|_next/image|brand/|favicon.ico).*)"],
};
