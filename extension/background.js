// Service worker: the only place that talks to the API (keeps the token out of page
// context). The popup sends {type:"start", url}; we POST /v1/runs and return the run_id.

async function config() {
  const { apiBase, apiToken } = await chrome.storage.local.get(["apiBase", "apiToken"]);
  return { apiBase: apiBase || "http://localhost:8000", apiToken: apiToken || "" };
}

async function startRun(url) {
  const { apiBase, apiToken } = await config();
  const headers = { "Content-Type": "application/json" };
  if (apiToken) headers["X-API-Key"] = apiToken;
  const r = await fetch(`${apiBase}/v1/runs`, {
    method: "POST", headers, body: JSON.stringify({ url }),
  });
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r.json();
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "start") {
    startRun(msg.url).then(sendResponse).catch((e) => sendResponse({ error: String(e) }));
    return true; // async response
  }
});
