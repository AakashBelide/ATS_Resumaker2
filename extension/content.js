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
  const SIZE = 46;                               // square edge (px) — the reference's docked tab
  const PAD = 8;                                 // min gap from the top/bottom viewport edge
  const DRAG_SLOP = 4;                           // px of pointer travel before a press becomes a drag
  let pill = null, toast = null, busy = false;

  function el(tag, css) {
    const n = document.createElement(tag);
    n.style.cssText = css;
    return n;
  }

  // Keep the button's top within the viewport (it's pinned to the right edge; only y is free).
  function clampY(y) {
    const max = Math.max(PAD, window.innerHeight - SIZE - PAD);
    return Math.min(Math.max(y, PAD), max);
  }

  // --- floating "⬡" trigger: a SQUARE button docked to the RIGHT edge (rounded on the left only),
  // our electric→azure theme. It's DRAGGABLE but rail-locked: x stays pinned right, y follows the
  // pointer (clamped). A quick press = capture; a drag just repositions. y persists in storage. -----
  function mountPill() {
    if (pill) return;
    pill = el("div",
      `position:fixed;right:0;top:40vh;z-index:${Z};width:${SIZE}px;height:${SIZE}px;
       display:flex;align-items:center;justify-content:center;cursor:grab;user-select:none;
       touch-action:none;border-radius:12px 0 0 12px;color:#EAF2FF;
       background:linear-gradient(135deg,#3B74FF,#5B93FF);
       box-shadow:-4px 0 18px rgba(59,116,255,.45);border:1px solid rgba(143,187,255,.5);
       border-right:none;transition:box-shadow .15s ease, opacity .15s ease, width .12s ease;`);
    pill.innerHTML =
      '<span data-ats-glyph style="font-size:20px;line-height:1">⬡</span>';   // ⬡ brand glyph
    pill.title = "ATS Resumaker — capture this posting (drag to move)";
    pill.onmouseenter = () => { pill.style.boxShadow = "-6px 0 22px rgba(59,116,255,.62)"; };
    pill.onmouseleave = () => { pill.style.boxShadow = "-4px 0 18px rgba(59,116,255,.45)"; };

    // Restore the saved y (else default to ~40vh), then wire up the drag/click behaviour.
    chrome.storage.local.get(["pillY"], (c) => {
      const y = typeof c.pillY === "number" ? clampY(c.pillY) : clampY(Math.round(window.innerHeight * 0.4));
      pill.style.top = `${y}px`;
    });
    attachDrag(pill);
    document.documentElement.appendChild(pill);

    // If the viewport shrinks, pull the button back on-screen (re-clamp its current y).
    window.addEventListener("resize", () => {
      if (!pill) return;
      pill.style.top = `${clampY(parseFloat(pill.style.top) || 0)}px`;
    });
  }

  // Press-and-hold drag along the right rail. A press that never crosses DRAG_SLOP is treated as a
  // click (capture); once it does, we move (y only) and, on release, persist without triggering.
  function attachDrag(node) {
    let active = false, moved = false, startY = 0, startTop = 0;
    const onDown = (e) => {
      if (busy || (e.button != null && e.button !== 0)) return;
      active = true; moved = false;
      startY = e.clientY;
      startTop = parseFloat(node.style.top) || 0;
      node.style.transition = "none";       // no lag while dragging
      node.style.cursor = "grabbing";
      try { node.setPointerCapture(e.pointerId); } catch { /* older engines */ }
      e.preventDefault();
    };
    const onMove = (e) => {
      if (!active) return;
      const dy = e.clientY - startY;
      if (!moved && Math.abs(dy) > DRAG_SLOP) moved = true;
      if (moved) node.style.top = `${clampY(startTop + dy)}px`;
    };
    const onUp = (e) => {
      if (!active) return;
      active = false;
      node.style.transition = "";
      node.style.cursor = "grab";
      try { node.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
      if (moved) {
        chrome.storage.local.set({ pillY: clampY(parseFloat(node.style.top) || 0) });  // stays put across pages
      } else if (!busy) {
        doCapture();                          // a real click -> capture
      }
    };
    node.addEventListener("pointerdown", onDown);
    node.addEventListener("pointermove", onMove);
    node.addEventListener("pointerup", onUp);
    node.addEventListener("pointercancel", onUp);
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

  // Briefly swap the ⬡ glyph (e.g. to a ✓) as an inline success/error cue on the square button.
  function flashLabel(label) {
    const inner = pill && pill.querySelector("[data-ats-glyph]");
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
      if (result && result.ok) { showToast("✓ tracked — fit fills in shortly", "ok"); flashLabel("✓"); }
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
