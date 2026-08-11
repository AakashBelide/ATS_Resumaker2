// Service worker: add the current job URL to the ATS Resumaker tracker. Two backends, all
// configurable from the Options page (so pointing at a backend hosted elsewhere is just a
// setting change):
//   - "cli"  : native messaging host runs the CLI (`track add`) locally - works even if the
//              FastAPI server is NOT running. This is the CLI-first path.
//   - "api"  : POST /v1/tracker to the configured API base (needs the server up).
//   - "auto" : try CLI first, fall back to API. (default)
const NATIVE_HOST = "com.resumaker.host";

async function cfg() {
  const c = await chrome.storage.local.get(["mode", "apiBase", "apiToken", "runMatch"]);
  return {
    mode: c.mode || "auto",
    apiBase: (c.apiBase || "http://localhost:8000").replace(/\/+$/, ""),
    apiToken: c.apiToken || "",
    runMatch: c.runMatch !== false, // default true
  };
}

function trackViaCLI(url, runMatch) {
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendNativeMessage(
        NATIVE_HOST, { action: "track", url, no_match: !runMatch },
        (resp) => {
          if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
          if (!resp || resp.ok !== true) return reject(new Error(resp?.error || "native host error"));
          resolve({ via: "cli", ...resp });
        });
    } catch (e) { reject(e); }
  });
}

async function trackViaAPI(url, c) {
  const headers = { "Content-Type": "application/json" };
  if (c.apiToken) headers["X-API-Key"] = c.apiToken;
  const r = await fetch(`${c.apiBase}/v1/tracker`, {
    method: "POST", headers, body: JSON.stringify({ url, run_match: c.runMatch }),
  });
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new Error(`API ${r.status} ${body}`.slice(0, 200));
  }
  return { via: "api", ok: true, entry: await r.json() };
}

async function track(url) {
  const c = await cfg();
  if (c.mode === "cli") return trackViaCLI(url, c.runMatch);
  if (c.mode === "api") return trackViaAPI(url, c);
  try { return await trackViaCLI(url, c.runMatch); }        // auto: CLI first
  catch { return await trackViaAPI(url, c); }                // ...then API
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "track") {
    track(msg.url)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((e) => sendResponse({ ok: false, error: String(e.message || e) }));
    return true; // async
  }
});
