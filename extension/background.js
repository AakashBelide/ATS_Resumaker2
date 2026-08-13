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

// Evaluate a JS expression in the page via CDP and return its numeric value (0 on anything odd).
async function evalNum(target, expression) {
  try {
    const res = await cdp(target, "Runtime.evaluate", { expression, returnByValue: true });
    const v = res && res.result && res.result.value;
    return typeof v === "number" && isFinite(v) ? v : 0;
  } catch { return 0; }
}

// Lazy-loaded pages (LinkedIn, Ashby, etc.) don't render their full height until scrolled, so a
// single captureBeyondViewport clip would miss the un-rendered tail. Walk the page top->bottom in
// viewport-sized steps, pausing so lazy content can load/settle and the document keeps growing,
// then return to the top so the capture's origin (and the user's view) is correct. Bounded by a
// step cap so a pathological infinite-scroll feed can't spin forever.
async function autoScroll(target) {
  const step = (await evalNum(target, "window.innerHeight")) || 800;
  let height = await evalNum(target, "document.documentElement.scrollHeight");
  let y = 0;
  for (let i = 0; i < 40; i++) {                 // cap: ~40 screens is plenty for any real posting
    y = Math.min(y + step, height);
    await cdp(target, "Runtime.evaluate", { expression: `window.scrollTo(0, ${y});` });
    await new Promise((r) => setTimeout(r, 240));   // let lazy content fetch + paint
    const grown = await evalNum(target, "document.documentElement.scrollHeight");
    const atBottom = y >= height - 1;
    height = grown;
    if (atBottom && grown <= y + 1) break;        // reached the end AND it stopped growing -> done
  }
  await cdp(target, "Runtime.evaluate", { expression: "window.scrollTo(0, 0);" });
  await new Promise((r) => setTimeout(r, 150));   // let sticky headers/top content re-settle
  return height;
}

// Full-page shot via CDP. Returns a data URL (PNG, or JPEG for tall pages). Throws on any failure
// so the caller can fall back to the visible viewport.
async function fullPageShot(tabId) {
  const target = { tabId };
  await attach(target);
  try {
    await autoScroll(target);                    // trigger lazy-load + settle BEFORE measuring
    const metrics = await cdp(target, "Page.getLayoutMetrics");
    const size = metrics.cssContentSize || metrics.contentSize || {};
    // Clamp to CDP's texture ceiling (~16k) so an enormous page can't fail the capture outright.
    const width = Math.min(Math.ceil(size.width || 0), 16000);
    const height = Math.min(Math.ceil(size.height || 0), 16000);
    if (!width || !height) throw new Error("no layout metrics");
    const tall = height > 4000;                  // JPEG for long postings; PNG (sharper) otherwise
    const format = tall ? "jpeg" : "png";
    const params = { format, captureBeyondViewport: true,
      clip: { x: 0, y: 0, width, height, scale: 1 } };
    if (tall) params.quality = 80;
    const shot = await cdp(target, "Page.captureScreenshot", params);
    if (!shot || !shot.data) throw new Error("empty screenshot");
    return `data:image/${format};base64,${shot.data}`;
  } finally {
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

async function capture({ url, title, rawText, tabId, windowId }) {
  // Small delay so the content script's pill-hide has painted before we grab the page.
  await new Promise((r) => setTimeout(r, 150));
  let screenshot = null;
  if (tabId != null) {
    try { screenshot = await fullPageShot(tabId); }
    catch { screenshot = null; }               // debugger denied/detached -> fall back below
  }
  if (!screenshot) screenshot = await captureVisible(windowId);

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
  return { ok: true, entry: await r.json() };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "capture") {
    capture({ url: msg.url, title: msg.title, rawText: msg.rawText,
              tabId: sender.tab ? sender.tab.id : undefined,
              windowId: sender.tab ? sender.tab.windowId : undefined })
      .then((result) => sendResponse(result))
      .catch((e) => sendResponse({ ok: false, error: String((e && e.message) || e) }));
    return true;   // keep the channel open for the async response
  }
});
