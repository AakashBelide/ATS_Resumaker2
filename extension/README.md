# ATS Resumaker — browser extension (MV3)

From any job posting, click the toolbar button → **+ Track this job** and it's added to your
ATS Resumaker tracker (which then runs the match). Two backends, and everything is
**configurable** (Options page) so you can point it at a backend hosted anywhere:

- **CLI-first** — a native messaging host runs the project CLI locally, so tracking works
  **even when the FastAPI server is not running**.
- **API fallback** — `POST /v1/tracker` to the configured server.
- **Auto** (default) — try CLI first, fall back to API.

## 1. Load the extension (unpacked)
1. Chrome / Edge / Brave → `chrome://extensions` → enable **Developer mode** → **Load unpacked**
   → select this `extension/` folder.
2. Copy the extension's **ID** (shown under its name). Pin the extension for easy access.

## 2a. CLI mode (recommended — works offline, no server needed)
Register the native messaging host once, passing the extension ID from step 1:

```bash
extension/native-host/install.sh <extension-id>
```

This writes the host manifest into your browser's `NativeMessagingHosts` folder (Chrome/Edge/
Brave/Chromium, macOS or Linux). Reload the extension. The host runs
`.venv/bin/python -m apps.cli track add --url <url>` in the project, so the project's `.venv`
must exist (`uv sync`). Then, in the extension **Options**, set method = **Auto** or **CLI**.

## 2b. API mode (server running)
1. Run the API: `uv run python -m apps.cli serve` (or the deploy stack). Note its URL and, if
   set, `RESUMAKER_API_TOKEN`.
2. Extension **Options** → set **API base URL** (default `http://localhost:8000`) + **API token**
   (only if the server requires one) → **Save**. Method = **Auto** or **API**.

## Hosting the backend elsewhere
It's all in Options — change **API base URL** / **token** / **Web app URL** to your host. For a
non-`https` remote origin, add it to `host_permissions` in `manifest.json` (localhost and any
`https://*` are already allowed).

## Files
- `manifest.json` — MV3 manifest (activeTab / storage / nativeMessaging).
- `background.js` — service worker; the track flow + backend selection (cli / api / auto).
- `popup.html` / `popup.js` — the **+ Track this job** button, status, “copy CLI command”
  fallback, and an “open tracker” link.
- `options.html` / `options.js` — configurable backend (method, API base/token, web URL, run-match).
- `native-host/` — the native messaging host (`resumaker_host.py`), its manifest template, and
  `install.sh` to register it.

Human-in-the-loop: the extension only **tracks** a job (and runs the match). It never applies.
