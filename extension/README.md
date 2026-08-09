# resumaker extension (MV3 scaffold)

A Manifest V3 browser extension: from any job posting, click **Tailor for this JD** to
start a run on your resumaker API. **Scaffold only** — it captures the tab URL and starts
a run (the API scrapes/structures it); richer in-page JD extraction and an assisted-apply
flow (human-in-the-loop, never auto-submit) come in Phase 5.

## Load it (unpacked)
1. Run the API (`uv run python -m apps.cli serve`) and note its URL + `RESUMAKER_API_TOKEN`.
2. Chrome/Edge → `chrome://extensions` → enable Developer mode → **Load unpacked** → select this `extension/` folder.
3. Open the popup → **Settings** → set API base + token → Save.
4. On a job posting, click **Tailor for this JD**, then review the result in the web dashboard.

## Files
- `manifest.json` — MV3 manifest (activeTab/storage; host permission for the API).
- `background.js` — service worker; the only place with the API token; POSTs `/v1/runs`.
- `popup.html` / `popup.js` — trigger UI + settings (stored in `chrome.storage.local`).
