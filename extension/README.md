# ATS Resumaker — browser extension (MV3)

From any job posting, click the floating **⬡ Track** pill (bottom-right) — or the toolbar button —
and the extension **captures the page** (its visible text + a screenshot + the URL) and posts it to
your ATS Resumaker backend. The backend structures the JD with the LLM and runs the match
(fit / gap / sponsorship / keywords); the tailored résumé/cover stay a manual, on-demand trigger.

Because the page is already loaded in your browser, the **extension does the capture** and the
backend **skips server-side scraping** — more reliable on JS-heavy / auth-walled postings. The
endpoint is **configurable** (Options page), so you can point it at a backend hosted anywhere.

Human-in-the-loop: the extension only **tracks** a job. It never applies.

## 1. Load the extension (unpacked)
1. Chrome / Edge / Brave → `chrome://extensions` → enable **Developer mode** → **Load unpacked**
   → select this `extension/` folder.
2. Pin the extension for easy access.

## 2. Point it at your backend
1. Run the API: `uv run uvicorn apps.api.main:app --port 8000` (or the deploy stack). Note its URL
   and, if set, `RESUMAKER_API_TOKEN`.
2. Extension **Options** → set **API base URL** (default `http://localhost:8000`) + **API token**
   (only if the server sets `RESUMAKER_API_TOKEN`) + **Web app URL** → **Save**.

Now open any posting and click **⬡ Track**. A toast confirms the capture; the fit score fills in on
the next Tracker refresh, and the report page shows the captured screenshot.

## What gets sent
`POST <apiBase>/v1/tracker/capture` with header `X-API-Key: <token>` and body:

```jsonc
{ "url": "<page url>", "raw_text": "<document.body.innerText + same-origin iframes>",
  "title": "<document.title>", "screenshot": "data:image/(png|jpeg);base64,..." }
```

The screenshot is a **full-page** capture (the whole scrollable posting, via the DevTools protocol),
sent as PNG for normal pages and JPEG (quality 80) for tall ones to keep the payload reasonable. The
raw JD text is kept server-side (in the tracker DB row); the screenshot lands in the run's artifact
folder (`{run_id}/screenshot.png` or `screenshot.jpg`). Nothing is stored in the extension beyond
your settings.

## Hosting the backend elsewhere
It's all in Options — change **API base URL** / **token** / **Web app URL** to your host. For a
non-`https` remote origin, add it to `host_permissions` in `manifest.json` (localhost and any
`https://*` are already allowed).

## Files
- `manifest.json` — MV3 manifest (activeTab / storage / tabs / debugger; content script on all
  http(s) pages).
- `content.js` — injects the floating **⬡ Track** pill; extracts the visible JD text + shows inline
  loading / success / error toasts (our dark theme).
- `background.js` — service worker; takes a full-page screenshot via the `chrome.debugger` CDP path
  (falling back to `captureVisibleTab`) and POSTs the capture to `/v1/tracker/capture`.
- `popup.html` / `popup.js` — toolbar button; delegates to the same capture path, plus an
  “open tracker” link and settings.
- `options.html` / `options.js` — configurable backend (API base / token, web URL).

## Notes
- **Full-page capture uses the debugger.** Chrome shows a “… started debugging this browser” banner
  while the shot is taken (it detaches immediately after). This is inherent to the CDP screenshot
  API; if the debugger is denied, the extension falls back to a visible-viewport shot automatically.
