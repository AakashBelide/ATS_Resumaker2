// Options: persist the backend configuration in chrome.storage.local. Nothing is hardcoded -
// the extension reads these at runtime, so retargeting a differently-hosted backend is just a
// settings change here.
const $ = (id) => document.getElementById(id);

const DEFAULTS = {
  apiBase: "http://localhost:8000",
  apiToken: "",
  webBase: "http://localhost:3002",
};

(async function load() {
  const c = { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
  $("apiBase").value = c.apiBase;
  $("apiToken").value = c.apiToken;
  $("webBase").value = c.webBase;
})();

$("save").addEventListener("click", async () => {
  await chrome.storage.local.set({
    apiBase: $("apiBase").value.trim() || DEFAULTS.apiBase,
    apiToken: $("apiToken").value,
    webBase: $("webBase").value.trim() || DEFAULTS.webBase,
  });
  const s = $("status");
  s.textContent = "saved ✓";
  setTimeout(() => { s.textContent = ""; }, 1800);
});
