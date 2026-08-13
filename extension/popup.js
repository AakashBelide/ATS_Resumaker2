// Popup: capture the active tab's posting. It DELEGATES to the in-page content script (which grabs
// the visible JD text + screenshot and posts to the backend), so the toolbar button and the
// floating "⬡ Track" pill share ONE capture path. Human-in-the-loop: this only TRACKS the job.
const $ = (id) => document.getElementById(id);
let tab = null;

function setStatus(text, cls) {
  const s = $("status");
  s.textContent = text;
  s.className = "status " + (cls || "muted");
}

(async function init() {
  const [t] = await chrome.tabs.query({ active: true, currentWindow: true });
  tab = t;
  $("url").textContent = (t && t.url) || "no active tab";
  const { webBase } = await chrome.storage.local.get(["webBase"]);
  $("open").href = (webBase || "http://localhost:3002").replace(/\/+$/, "") + "/tracker";
})();

$("track").addEventListener("click", async () => {
  if (!tab || !tab.id) { setStatus("no active tab", "err"); return; }
  $("track").disabled = true;
  setStatus("capturing…", "muted");
  try {
    // The content script isn't injected on restricted pages (chrome://, the web store, ...);
    // sendMessage rejects there, which we surface as a friendly hint.
    const resp = await chrome.tabs.sendMessage(tab.id, { type: "triggerCapture" });
    if (resp && resp.ok) setStatus("✓ tracked. Fit fills in shortly.", "ok");
    else setStatus("error: " + ((resp && resp.error) || "unknown"), "err");
  } catch {
    setStatus("can't capture this page — open a job posting first", "err");
  } finally {
    $("track").disabled = false;
  }
});

$("opts").addEventListener("click", (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); });
