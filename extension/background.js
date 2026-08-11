// Service worker: add the current job URL to the ATS Resumaker tracker.
//
// The extension is a THIN HTTP CLIENT: it just POSTs the URL to the backend's `/v1/tracker`
// endpoint. The backend owns everything else (instant add, then the CLI-first LLM match in a
// background task). Backend base URL / token are configurable from the Options page, so
// pointing at a backend hosted anywhere is just a setting change.
async function cfg() {
  const c = await chrome.storage.local.get(["apiBase", "apiToken", "runMatch"]);
  return {
    apiBase: (c.apiBase || "http://localhost:8000").replace(/\/+$/, ""),
    apiToken: c.apiToken || "",
    runMatch: c.runMatch !== false, // default true
  };
}

async function track(url) {
  const c = await cfg();
  const headers = { "Content-Type": "application/json" };
  if (c.apiToken) headers["X-API-Key"] = c.apiToken;
  const r = await fetch(`${c.apiBase}/v1/tracker`, {
    method: "POST", headers, body: JSON.stringify({ url, run_match: c.runMatch }),
  });
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new Error(`API ${r.status} ${body}`.slice(0, 200));
  }
  return { ok: true, entry: await r.json() };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "track") {
    track(msg.url)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((e) => sendResponse({ ok: false, error: String(e.message || e) }));
    return true; // async
  }
});
