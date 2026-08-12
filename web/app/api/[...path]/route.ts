// BFF proxy (server-side, runs on Vercel's runtime — never in the browser).
//
// Every `/api/*` call from the frontend lands here, gets the API token attached, and is forwarded
// to the real backend (Cloud Run). The token lives ONLY in the server env (API_TOKEN), so it's
// never in the client bundle — closing the NEXT_PUBLIC_ token-exposure hole — and since the
// browser only ever talks to this same origin, CORS disappears too.
//
// Config (server-only env; set on Vercel + web/.env.local for dev):
//   API_ORIGIN  base URL of the backend  (e.g. https://resumaker-api-….run.app; dev: http://localhost:8000)
//   API_TOKEN   the backend's single-user token (blank locally if the local API has no token)
import { NextRequest } from "next/server";

const ORIGIN = (process.env.API_ORIGIN ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN = process.env.API_TOKEN ?? "";

// Response headers worth forwarding to the browser (skip hop-by-hop / encoding-specific ones,
// which don't survive the re-stream and would corrupt the body if copied).
const PASS = ["content-type", "content-disposition", "cache-control"];

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await ctx.params;
  const url = `${ORIGIN}/${path.join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  const ct = req.headers.get("content-type");
  if (ct) headers.set("content-type", ct);
  if (TOKEN) headers.set("x-api-key", TOKEN);

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const upstream = await fetch(url, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    // follow the api's 302 -> GCS signed URL so downloads work on both storage backends
    redirect: "follow",
  });

  const out = new Headers();
  for (const h of PASS) {
    const v = upstream.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
