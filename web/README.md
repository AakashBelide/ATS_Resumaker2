# resumaker web

Next.js 15 (App Router) dashboard for the ATS Resumaker API. Seven pages:
**Discovery** (deterministic feed + Track), **Tracker** (match outcomes + lifecycle +
on-demand resume/cover + captured screenshot + own-PDF upload), **Onboarding**,
**Profile**, **Mailer**, **Dashboard**, **Metrics**. Deployed on **Vercel**.

## Auth model (BFF proxy — token never reaches the browser)
Every `/api/*` call from the client hits a same-origin **BFF proxy**
(`app/api/[...path]/route.ts`) that attaches the API token **server-side** and forwards
to the backend. So the token lives only in server env (`API_TOKEN`), never in the client
bundle, and there's no CORS. Progress is by **polling** (`GET /v1/runs/{id}/progress`),
not SSE — a scale-to-zero backend can't hold a stream.

## Dev
```bash
cd web
cp .env.local.example .env.local   # set API_ORIGIN (e.g. http://localhost:8000) + API_TOKEN
npm install
npm run dev                        # http://localhost:3000  (API must be running)
```
Server-only env (set on Vercel + in `.env.local` for dev):
- `API_ORIGIN` — backend base URL (`https://…run.app`; dev: `http://localhost:8000`).
- `API_TOKEN` — the backend's single-user token (blank locally if the API has no token).

## Layout
- `lib/api.ts` — the single typed client for `/v1` (all pages talk only to this).
- `app/api/[...path]/route.ts` — the BFF proxy (attaches the token, follows GCS redirects).
- `app/<page>/page.tsx` — Discovery (`/`), Tracker, Onboarding, Profile, Mailer, Dashboard, Metrics.
- `app/report/[runId]/page.tsx` — match report + inline resume/cover + captured screenshot.
- `components/` — Sidebar, Select/MultiSelect, CompanyLogo, Spinner, Donut.

`node_modules`/`.next` are gitignored; run `npm install` before first `dev`.
