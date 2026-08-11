// Popup: show the active tab's URL and add it to the tracker via the configured backend.
// Human-in-the-loop: this only TRACKS the job (the backend then runs the match); it never applies.
const $ = (id) => document.getElementById(id);
let url = "";

function setStatus(text, cls) {
  const s = $("status");
  s.textContent = text;
  s.className = "status " + (cls || "muted");
}

async function activeTab() {
  const [t] = await chrome.tabs.query({ active: true, currentWindow: true });
  return t;
}

(async function init() {
  const t = await activeTab();
  url = t?.url || "";
  $("url").textContent = url || "no active tab";
  const { webBase } = await chrome.storage.local.get(["webBase"]);
  $("open").href = (webBase || "http://localhost:3002").replace(/\/+$/, "") + "/tracker";
})();

$("track").addEventListener("click", async () => {
  if (!url) { setStatus("no active tab", "err"); return; }
  $("track").disabled = true;
  setStatus("tracking…", "muted");
  const resp = await chrome.runtime.sendMessage({ type: "track", url });
  $("track").disabled = false;
  if (resp?.ok) {
    setStatus("✓ tracked. Fit fills in shortly.", "ok");
  } else {
    setStatus(`error: ${resp?.error || "unknown"}`, "err");
  }
});

$("opts").addEventListener("click", (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); });
