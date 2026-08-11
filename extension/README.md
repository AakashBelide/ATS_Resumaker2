# ATS Resumaker — browser extension (MV3)

From any job posting, click the toolbar button → **+ Track this job** and it's added to your
ATS Resumaker tracker (the backend then runs the match).

The extension is a **thin HTTP client**: it only `POST`s the current tab's URL to your backend's
`/v1/tracker` endpoint. Everything else — the instant add, then the CLI-first LLM match — happens
on the **backend**. The endpoint is **configurable** (Options page), so you can point it at a
backend hosted anywhere.

## 1. Load the extension (unpacked)
1. Chrome / Edge / Brave → `chrome://extensions` → enable **Developer mode** → **Load unpacked**
   → select this `extension/` folder.
2. Pin the extension for easy access.

## 2. Point it at your backend
1. Run the API: `uv run python -m apps.cli serve` (or the deploy stack). Note its URL and, if
   set, `RESUMAKER_API_TOKEN`.
2. Extension **Options** → set **API base URL** (default `http://localhost:8000`) + **API token**
   (only if the server sets `RESUMAKER_API_TOKEN`) → **Save**.

That's it — click **+ Track this job** on any posting.

## Hosting the backend elsewhere
It's all in Options — change **API base URL** / **token** / **Web app URL** to your host. For a
non-`https` remote origin, add it to `host_permissions` in `manifest.json` (localhost and any
`https://*` are already allowed).

## Files
- `manifest.json` — MV3 manifest (activeTab / storage only).
- `background.js` — service worker; posts the URL to `/v1/tracker`.
- `popup.html` / `popup.js` — the **+ Track this job** button, status, and an “open tracker” link.
- `options.html` / `options.js` — configurable backend (API base/token, web URL, run-match).

Human-in-the-loop: the extension only **tracks** a job (the backend runs the match). It never applies.
