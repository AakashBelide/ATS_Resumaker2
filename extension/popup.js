// Popup: show the active tab's URL (the JD), let the user trigger a run, and store the
// API base/token. Human-in-the-loop: this only STARTS tailoring; it never auto-applies.

const $ = (id) => document.getElementById(id);

async function activeTabUrl() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.url ?? "";
}

(async function init() {
  const url = await activeTabUrl();
  $("url").textContent = url || "no active tab";
  const { apiBase, apiToken } = await chrome.storage.local.get(["apiBase", "apiToken"]);
  $("apiBase").value = apiBase || "http://localhost:8000";
  $("apiToken").value = apiToken || "";
})();

$("save").addEventListener("click", async () => {
  await chrome.storage.local.set({ apiBase: $("apiBase").value, apiToken: $("apiToken").value });
  $("status").textContent = "settings saved";
  $("status").className = "ok";
});

$("go").addEventListener("click", async () => {
  const url = await activeTabUrl();
  $("status").textContent = "starting…";
  $("status").className = "muted";
  const resp = await chrome.runtime.sendMessage({ type: "start", url });
  if (resp?.error) {
    $("status").textContent = `error: ${resp.error}`;
    $("status").className = "err";
  } else {
    $("status").textContent = `started run ${resp.run_id} — review in the dashboard`;
    $("status").className = "ok";
  }
});
