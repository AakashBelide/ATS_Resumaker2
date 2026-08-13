// ATS Resumaker capture content script (reference-style, OUR dark theme).
//
// Injects a floating "⬡ Track" pill into every page. On click it grabs the page's VISIBLE JD text
// (best-effort including same-origin iframes) and asks the service worker to screenshot the tab and
// POST everything to `<apiBase>/v1/tracker/capture`. The extension does the heavy lifting in the
// browser (the page is already loaded), so the backend skips server-side scraping. Human-in-the-
// loop: this only TRACKS the posting (the backend then runs the match); it never applies.
(() => {
  if (window.__atsResumakerInjected) return;   // guard against double-injection (SPA re-nav, etc.)
  window.__atsResumakerInjected = true;

  const Z = 2147483647;                          // sit above page chrome
  let pill = null, toast = null, busy = false;

  function el(tag, css) {
    const n = document.createElement(tag);
    n.style.cssText = css;
    return n;
  }

  // --- floating "⬡ Track" pill (our electric→azure gradient, mono label) --------------------
  function mountPill() {
    if (pill) return;
    pill = el("div",
      `position:fixed;right:18px;bottom:18px;z-index:${Z};display:flex;align-items:center;gap:8px;
       padding:10px 15px;border-radius:999px;cursor:pointer;user-select:none;
       font:600 13px/1 ui-sans-serif,system-ui,-apple-system,sans-serif;color:#061024;
       background:linear-gradient(135deg,#3B74FF,#5B93FF);
       box-shadow:0 6px 22px rgba(59,116,255,.45);border:1px solid rgba(143,187,255,.5);
       transition:transform .15s ease, box-shadow .15s ease, opacity .15s ease;`);
    pill.innerHTML =
      '<span style="font-size:15px;line-height:1">⬡</span>' +   // ⬡ brand glyph
      '<span data-ats-label style="letter-spacing:.3px">Track</span>';
    pill.title = "ATS Resumaker — capture this posting";
    pill.onmouseenter = () => {
      pill.style.transform = "translateY(-1px)";
      pill.style.boxShadow = "0 8px 26px rgba(59,116,255,.6)";
    };
    pill.onmouseleave = () => {
      pill.style.transform = "none";
      pill.style.boxShadow = "0 6px 22px rgba(59,116,255,.45)";
    };
    pill.onclick = () => { if (!busy) doCapture(); };
    document.documentElement.appendChild(pill);
  }

  function showToast(text, tone) {
    if (!toast) {
      toast = el("div",
        `position:fixed;right:18px;bottom:66px;z-index:${Z};max-width:280px;
         padding:9px 13px;border-radius:10px;
         font:500 12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
         background:#0E1728;color:#E9F0FB;border:1px solid rgba(126,164,224,.22);
         box-shadow:0 8px 24px rgba(0,0,0,.4);`);
      document.documentElement.appendChild(toast);
    }
    toast.style.color = tone === "ok" ? "#8FBBFF" : tone === "err" ? "#ff7a8a" : "#93A7C9";
    toast.style.borderColor = tone === "err" ? "rgba(255,122,138,.4)" : "rgba(126,164,224,.22)";
    toast.textContent = text;
    toast.style.display = "block";
  }
  function hideToastSoon(ms) { setTimeout(() => { if (toast) toast.style.display = "none"; }, ms); }

  function flashLabel(label) {
    const inner = pill && pill.querySelector("[data-ats-label]");
    if (!inner) return;
    const prev = inner.textContent;
    inner.textContent = label;
    setTimeout(() => { inner.textContent = prev; }, 2000);
  }

  // Best-effort visible text: the body + any SAME-ORIGIN iframes (cross-origin access throws,
  // so those frames are silently skipped). Mirrors the reference extension's getText.
  function allText(root) {
    let text = "";
    try {
      text += root.innerText || "";
      const frames = root.getElementsByTagName ? root.getElementsByTagName("iframe") : [];
      for (const f of frames) {
        try {
          const doc = f.contentDocument || (f.contentWindow && f.contentWindow.document);
          if (doc && doc.body) text += "\n" + allText(doc.body);
        } catch { /* cross-origin frame - skip */ }
      }
    } catch { /* ignore extraction hiccups */ }
    return text;
  }

  // Gather text -> hand off to the service worker (screenshot + POST). Returns {ok} / {ok,error}.
  async function doCapture() {
    busy = true;
    if (pill) pill.style.opacity = "0";           // hide the pill so it's not in the screenshot
    showToast("capturing…", "muted");
    const url = location.href;
    const title = document.title || "";
    const rawText = allText(document.body).trim();
    let result;
    try {
      if (!rawText) throw new Error("no visible text on this page");
      result = await chrome.runtime.sendMessage({ type: "capture", url, title, rawText });
      if (result && result.ok) { showToast("✓ tracked — fit fills in shortly", "ok"); flashLabel("✓ Tracked"); }
      else { showToast("error: " + ((result && result.error) || "unknown"), "err"); }
    } catch (e) {
      result = { ok: false, error: String((e && e.message) || e) };
      showToast("error: " + result.error, "err");
    } finally {
      if (pill) pill.style.opacity = "1";
      busy = false;
      hideToastSoon(4000);
    }
    return result || { ok: false, error: "unknown" };
  }

  // The toolbar popup delegates here so the button and the pill share ONE capture path.
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg && msg.type === "triggerCapture") {
      if (busy) { sendResponse({ ok: false, error: "already capturing" }); return; }
      doCapture().then(sendResponse).catch((e) => sendResponse({ ok: false, error: String(e) }));
      return true;   // async response
    }
  });

  if (document.readyState === "complete" || document.readyState === "interactive") mountPill();
  else window.addEventListener("DOMContentLoaded", mountPill);
})();
