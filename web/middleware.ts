// Login gate (RB.1). Runs on every request except static assets (see `matcher`). Public routes are
// allowed through; everything else requires a valid signed session cookie. This protects BOTH the
// app pages AND the `/api/*` BFF proxy — so an unauthenticated user can neither view the dashboard
// nor use the proxy to reach the backend. (The backend itself is separately protected by its own
// API token; the proxy only ever runs for a logged-in user.)
import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, verifySession } from "@/lib/session";

// Public (no session required): the landing, login + setup pages, and the login/logout endpoints.
const PUBLIC_PAGES = new Set(["/", "/login", "/setup"]);
const PUBLIC_API = new Set(["/api/login", "/api/logout"]);

function isPublic(pathname: string): boolean {
  if (PUBLIC_PAGES.has(pathname)) return true;
  if (PUBLIC_API.has(pathname)) return true;
  // allow the setup docs sub-paths (e.g. /setup/local) if they exist later
  if (pathname.startsWith("/setup/")) return true;
  return false;
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (isPublic(pathname)) return NextResponse.next();

  const token = req.cookies.get(SESSION_COOKIE)?.value;
  const session = await verifySession(token, process.env.SESSION_SECRET);
  if (session) return NextResponse.next();

  // Unauthenticated. API → 401 (no HTML redirect for fetch()); pages → redirect to /login?next=…
  if (pathname.startsWith("/api/")) {
    return new NextResponse("unauthorized", { status: 401 });
  }
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.searchParams.set("next", pathname);
  return NextResponse.redirect(url);
}

// Skip Next internals + static files; everything else runs through the gate.
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
