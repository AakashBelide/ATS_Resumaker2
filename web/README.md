# resumaker web (scaffold)

Next.js 15 (App Router) dashboard for the resumaker API. **Scaffold only** — proves the
API contract (start a run, watch SSE progress, list runs, download artifacts). The full
review/approve/history/cost UI is built in the frontend pass (Phase 5).

## Dev
```bash
cd web
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_BASE + token
npm install
npm run dev                        # http://localhost:3000  (API must be running)
```

## Layout
- `lib/api.ts` — the single typed client for `/v1` (runs, SSE, artifacts, costs).
- `app/page.tsx` — dashboard: start a run, live progress, runs table with outcomes.
- `app/layout.tsx` — shell.

`node_modules`/`.next` are gitignored; run `npm install` before first `dev`.
