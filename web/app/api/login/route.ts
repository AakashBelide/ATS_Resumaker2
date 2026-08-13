// POST /api/login — the static login check. Compares the submitted credentials against the
// server-only env (LOGIN_USERNAME / LOGIN_PASSWORD); on a match, sets a 30-day signed httpOnly
// session cookie. Fails CLOSED: if the env creds aren't configured, no login is possible.
//
// A static segment (`/api/login`) takes precedence over the catch-all proxy (`/api/[...path]`),
// so this handler — not the backend proxy — serves this path.
import { NextResponse } from "next/server";

import { SESSION_COOKIE, SESSION_MAX_AGE_S, signSession } from "@/lib/session";

export async function POST(req: Request) {
  const user = process.env.LOGIN_USERNAME;
  const pass = process.env.LOGIN_PASSWORD;
  const secret = process.env.SESSION_SECRET;
  if (!user || !pass || !secret) {
    return NextResponse.json({ ok: false, error: "login is not configured on the server" }, { status: 503 });
  }
  let body: { username?: string; password?: string };
  try { body = await req.json(); } catch { return NextResponse.json({ ok: false, error: "bad request" }, { status: 400 }); }

  if (body.username !== user || body.password !== pass) {
    return NextResponse.json({ ok: false, error: "invalid username or password" }, { status: 401 });
  }
  const token = await signSession({ u: user, exp: Date.now() + SESSION_MAX_AGE_S * 1000 }, secret);
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production",
    path: "/", maxAge: SESSION_MAX_AGE_S,
  });
  return res;
}
