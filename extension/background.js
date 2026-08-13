// Service worker: FULL-PAGE screenshot the tab + POST the capture to /v1/tracker/capture.
//
// The content script gathered the URL + visible JD text; the SCREENSHOT is taken here (content
// scripts can't drive the DevTools protocol / captureVisibleTab). We grab the WHOLE page via the
// chrome.debugger CDP path (Page.getLayoutMetrics -> Page.captureScreenshot with
// captureBeyondViewport), falling back to the visible viewport (chrome.tabs.captureVisibleTab) if
// the debugger is denied/detached so a click never dead-ends. Long postings render tall, so we send
// JPEG (quality 80) for tall pages and PNG otherwise to keep the payload sane.
//
// Backend base URL / token come from the Options page (chrome.storage.local); the token lives only
// there and rides as an X-API-Key header. We never log the JD text or the screenshot bytes.
async function cfg() {
  const c = await chrome.storage.local.get(["apiBase", "apiToken"]);
  return {
    apiBase: (c.apiBase || "http://localhost:8000").replace(/\/+$/, ""),
    apiToken: c.apiToken || "",
  };
}

// --- chrome.debugger promise wrappers ---------------------------------------------------------
function attach(target) {
  return new Promise((resolve, reject) => {
    chrome.debugger.attach(target, "1.3", () => {
      const err = chrome.runtime.lastError;
      err ? reject(new Error(err.message)) : resolve();
    });
  });
}
function detach(target) {
  return new Promise((resolve) => {
    try { chrome.debugger.detach(target, () => { void chrome.runtime.lastError; resolve(); }); }
    catch { resolve(); }
  });
}
function cdp(target, method, params) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand(target, method, params || {}, (res) => {
      const err = chrome.runtime.lastError;
      err ? reject(new Error(err.message)) : resolve(res);
    });
  });
}

// Full-page shot via CDP. attach -> measure -> Page.captureScreenshot(captureBeyondViewport). The
// user's visible scroll position never moves (no visible scrolling, unlike the stitch fallback).
//
// The catch: many postings (LinkedIn's job "reader" especially) render the JD inside a NESTED,
// fixed-height scroll container (or a 100vh modal), so the DOCUMENT stays one screen tall and a
// plain captureBeyondViewport grabs only that slice. To reveal the whole posting we override the
// device metrics to a TALL layout viewport (`Emulation.setDeviceMetricsOverride`): vh-sized and
// inner-scroll containers then lay out at their true height, so everything becomes capturable. The
// target height is the max of the document height and `hintHeight` (the content script's measured
// tallest inner scroller). Cleared in `finally` so the user's page snaps back. The content script
// already clicked "see more"/expanders before this runs. Throws on any failure so the caller falls
// back. JPEG (q80) for tall postings; PNG (sharper) otherwise.
async function fullPageShot(tabId, hintHeight) {
  const target = { tabId };
  await attach(target);
  let overrode = false;
  try {
    const m0 = await cdp(target, "Page.getLayoutMetrics");
    const s0 = m0.cssContentSize || m0.contentSize || {};
    // Clamp to CDP's texture ceiling (~16k) so an enormous page can't fail the capture outright.
    const width = Math.min(Math.max(Math.ceil(s0.width || 0), 320), 16000);
    const docH = Math.ceil(s0.height || 0);
    const height = Math.min(Math.max(docH, Math.ceil(hintHeight || 0)), 16000);
    if (!width || !height) throw new Error("no layout metrics");

    // Force a tall layout viewport so inner-scroll / vh-locked containers reveal their full content.
    await cdp(target, "Emulation.setDeviceMetricsOverride",
      { width, height, deviceScaleFactor: 0, mobile: false });
    overrode = true;
    await new Promise((r) => setTimeout(r, 300));   // let the expanded layout reflow + paint

    const tall = height > 4000;                  // JPEG for long postings; PNG (sharper) otherwise
    const format = tall ? "jpeg" : "png";
    const params = { format, captureBeyondViewport: true,
      clip: { x: 0, y: 0, width, height, scale: 1 } };
    if (tall) params.quality = 80;
    const shot = await cdp(target, "Page.captureScreenshot", params);
    if (!shot || !shot.data) throw new Error("empty screenshot");
    return `data:image/${format};base64,${shot.data}`;
  } finally {
    // Restore the user's real viewport BEFORE detaching, so the page snaps back to normal.
    if (overrode) {
      try { await cdp(target, "Emulation.clearDeviceMetricsOverride"); } catch { /* ignore */ }
    }
    await detach(target);
  }
}

// Visible-viewport fallback: resolves to a data URL or null (capture blocked -> optional screenshot).
function captureVisible(windowId) {
  return new Promise((resolve) => {
    try {
      chrome.tabs.captureVisibleTab(windowId, { format: "png" }, (dataUrl) => {
        resolve(chrome.runtime.lastError || !dataUrl ? null : dataUrl);
      });
    } catch { resolve(null); }
  });
}

// --- scroll-and-stitch fallback (no debugger needed) ------------------------------------------
// chrome.debugger.attach FAILS while DevTools is open on the tab (DevTools owns the debug channel),
// so fullPageShot silently degrades. This path captures the whole page WITHOUT the debugger: it asks
// the content script for the page geometry, scrolls the page in viewport-sized steps, grabs each
// frame with chrome.tabs.captureVisibleTab, and stitches them top->bottom onto one tall
// OffscreenCanvas (scaled by devicePixelRatio). captureVisibleTab is rate-limited to ~2/s
// (MAX_CAPTURE_VISIBLE_TAB_CALLS_PER_SECOND), so frames are paced ~600ms apart - which doubles as a
// dwell for lazy content. NOTE: sticky/fixed headers render in EVERY frame, so they can appear
// duplicated down the stitched image - an accepted tradeoff; the debugger path (primary) avoids it.
const CAPTURE_INTERVAL_MS = 600;      // >= 1000/2 to respect the captureVisibleTab rate limit
const STITCH_MAX_HEIGHT = 16000;      // device-px cap on the tall canvas (matches CDP's texture ceiling)

// Promise wrapper for messaging the content script (resolves undefined if it isn't there / errors).
function tabMessage(tabId, msg) {
  return new Promise((resolve) => {
    try {
      chrome.tabs.sendMessage(tabId, msg, (res) => { void chrome.runtime.lastError; resolve(res); });
    } catch { resolve(undefined); }
  });
}

// Decode a base64 data URL to an ImageBitmap without fetch()/FileReader (unreliable in a module SW).
async function dataUrlToBitmap(dataUrl) {
  const comma = dataUrl.indexOf(",");
  const meta = dataUrl.slice(0, comma);
  const bin = atob(dataUrl.slice(comma + 1));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const mime = (meta.match(/data:([^;]+)/) || [])[1] || "image/png";
  return createImageBitmap(new Blob([bytes], { type: mime }));
}

// Encode a Blob to a base64 data URL (btoa is available in the service worker; FileReader may not be).
async function blobToDataUrl(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const CHUNK = 0x8000;                // chunk to avoid String.fromCharCode arg-count limits
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return `data:${blob.type || "image/jpeg"};base64,${btoa(binary)}`;
}

// Stitched full-page shot. Returns a JPEG (quality 80) data URL, or throws so the caller can fall
// back to a single visible-viewport shot. Restores the user's original scroll position at the end.
async function stitchPageShot(tabId, windowId) {
  const m = await tabMessage(tabId, { type: "pageMetrics" });
  if (!m || !m.innerHeight) throw new Error("no page metrics");
  const dpr = m.dpr || 1;
  const vh = m.innerHeight;
  const originalScrollY = m.scrollY || 0;
  const total = Math.min(m.scrollHeight || vh, Math.floor(STITCH_MAX_HEIGHT / dpr));  // cap ~16000 device px
  const canvas = new OffscreenCanvas(
    Math.round(m.innerWidth * dpr), Math.min(Math.round(total * dpr), STITCH_MAX_HEIGHT));
  const ctx = canvas.getContext("2d");
  try {
    let y = 0, lastY = -1, first = true;
    while (y < total) {
      const res = await tabMessage(tabId, { type: "scrollTo", y });
      const actualY = res && typeof res.y === "number" ? res.y : y;   // clamped at the bottom
      // Pace for the capture rate-limit AND let lazy content paint (first frame settles faster).
      await new Promise((r) => setTimeout(r, first ? 250 : CAPTURE_INTERVAL_MS));
      first = false;
      let dataUrl = await captureVisible(windowId);
      if (!dataUrl) {                   // likely the ~2/s rate-limit: wait past the window, retry once
        await new Promise((r) => setTimeout(r, 700));
        dataUrl = await captureVisible(windowId);
      }
      if (!dataUrl) { if (y === 0) throw new Error("captureVisibleTab blocked"); break; }
      const bmp = await dataUrlToBitmap(dataUrl);
      ctx.drawImage(bmp, 0, Math.round(actualY * dpr));   // place at the REAL offset (last frame overlaps)
      bmp.close();
      if (actualY <= lastY) break;      // couldn't scroll further -> reached the bottom, done
      lastY = actualY;
      y += vh;
    }
    return await blobToDataUrl(await canvas.convertToBlob({ type: "image/jpeg", quality: 0.8 }));
  } finally {
    await tabMessage(tabId, { type: "scrollTo", y: originalScrollY });   // restore the user's view
  }
}

async function capture({ url, title, rawText, tabId, windowId, fullHeight }) {
  // Small delay so the content script's pill-hide has painted before we grab the page.
  await new Promise((r) => setTimeout(r, 150));
  let screenshot = null, mode = "none";        // mode surfaces to the UI which path actually ran
  if (tabId != null) {
    // PRIMARY: debugger/CDP full-page (cleanest - whole page, no visible scrolling, no sticky-header
    // dupes). `fullHeight` is the content script's measured tallest inner scroller, used to size a
    // tall layout viewport so nested/vh-locked scroll containers reveal all content. Denied when
    // DevTools is open on the tab (it owns the debug channel) -> fall to stitch.
    try { screenshot = await fullPageShot(tabId, fullHeight); if (screenshot) mode = "full"; }
    catch { screenshot = null; }
    // FALLBACK: scroll-and-stitch via captureVisibleTab - needs NO debugger, so it works even with
    // DevTools open. Yields a full-page image (with possible sticky-header dupes) instead of a
    // single visible slice. This DOES scroll the visible view while it runs.
    if (!screenshot) {
      try { screenshot = await stitchPageShot(tabId, windowId); if (screenshot) mode = "stitched"; }
      catch { screenshot = null; }
    }
  }
  // LAST RESORT: a single visible-viewport shot, if even stitching failed (capture fully blocked).
  if (!screenshot) { screenshot = await captureVisible(windowId); if (screenshot) mode = "viewport"; }

  const c = await cfg();
  const headers = { "Content-Type": "application/json" };
  if (c.apiToken) headers["X-API-Key"] = c.apiToken;
  const r = await fetch(`${c.apiBase}/v1/tracker/capture`, {
    method: "POST", headers,
    body: JSON.stringify({ url, raw_text: rawText, title, screenshot }),
  });
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new Error(`API ${r.status} ${body}`.slice(0, 200));   // truncate; never surface the JD/shot
  }
  return { ok: true, entry: await r.json(), mode };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "capture") {
    capture({ url: msg.url, title: msg.title, rawText: msg.rawText, fullHeight: msg.fullHeight,
              tabId: sender.tab ? sender.tab.id : undefined,
              windowId: sender.tab ? sender.tab.windowId : undefined })
      .then((result) => sendResponse(result))
      .catch((e) => sendResponse({ ok: false, error: String((e && e.message) || e) }));
    return true;   // keep the channel open for the async response
  }
});
