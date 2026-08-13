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

  // The full content height the screenshot must cover. On most pages that's just the document, but
  // LinkedIn (and many ATS) put the JD inside a NESTED, fixed-height scroll container - so the
  // document stays one screen tall while the real content scrolls INSIDE that box. Find the tallest
  // such inner scroller (a big element whose scrollHeight overflows its clientHeight and that
  // actually scrolls) and report its full scrollHeight, so the service worker can size a tall layout
  // viewport and capture everything. Falls back to the document height when there's no inner scroller.
  function fullContentHeight() {
    let max = Math.max(
      document.documentElement.scrollHeight,
      document.body ? document.body.scrollHeight : 0);
    const all = document.body ? document.body.getElementsByTagName("*") : [];
    for (const el of all) {
      const ch = el.clientHeight;
      if (ch < 300) continue;                     // ignore small widgets; we want big content panels
      const sh = el.scrollHeight;
      if (sh <= ch + 50) continue;                // not meaningfully scrollable
      const oy = getComputedStyle(el).overflowY;
      if (oy === "auto" || oy === "scroll" || oy === "overlay") {
        // The inner box's own top offset + its full scroll height = how tall the page must be to show it.
        const top = el.getBoundingClientRect().top + (window.scrollY || 0);
        if (top + sh > max) max = top + sh;
      }
    }
    return Math.ceil(max);
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

  // Reveal collapsed content before we read text + screenshot. Many postings truncate the JD behind
  // a "see more"/"…more" button (LinkedIn especially), so the visible page is short and the full-page
  // screenshot stops early. Click those expanders first. Conservative: only buttons/links whose short
  // label reads like "more"/"see more"/"show more"/"expand", plus LinkedIn's known JD toggle classes,
  // so we never fire unrelated UI. A couple of passes handle nested/newly-revealed expanders.
  async function expandCollapsibles() {
    const looksLikeMore = (elm) => {
      const t = ((elm.textContent || "") + " " + (elm.getAttribute("aria-label") || "")).toLowerCase();
      return t.length < 40 && /(see|show|read)\s+more|…\s*more|\bmore\b|expand/.test(t);
    };
    const KNOWN = "button.jobs-description__footer-button, button.show-more-less-html__button";
    for (let pass = 0; pass < 2; pass++) {
      document.querySelectorAll(KNOWN).forEach((b) => { try { b.click(); } catch { /* ignore */ } });
      document.querySelectorAll('button, a[role="button"], [aria-expanded="false"]').forEach((b) => {
        if (looksLikeMore(b)) { try { b.click(); } catch { /* ignore */ } }
      });
      await new Promise((r) => setTimeout(r, 300));   // let the revealed content render
    }
  }

  // Gather text -> hand off to the service worker (screenshot + POST). Returns {ok} / {ok,error}.
  async function doCapture() {
    busy = true;
    showToast("expanding…", "muted");
    await expandCollapsibles();                   // reveal the full JD before text + screenshot
    if (pill) pill.style.opacity = "0";           // hide the pill so it's not in the screenshot
    showToast("capturing…", "muted");
    const url = location.href;
    const title = document.title || "";
    const rawText = allText(document.body).trim();
    const fullHeight = fullContentHeight();       // covers nested/inner scroll containers (LinkedIn)
    let result;
    try {
      if (!rawText) throw new Error("no visible text on this page");
      result = await chrome.runtime.sendMessage({ type: "capture", url, title, rawText, fullHeight });
      if (result && result.ok) {
        // Tell the user which screenshot path ran: "full" = clean CDP full-page (best); "stitched" =
        // scroll-and-stitch full-page (DevTools was open, so the view scrolled); "viewport" = only the
        // visible slice (capture was fully blocked -> close DevTools + retry for a full-page shot).
        const note = result.mode === "full" ? "full page"
          : result.mode === "stitched" ? "full page (stitched)"
          : result.mode === "viewport" ? "viewport only — close DevTools for full page"
          : "";
        showToast("✓ tracked" + (note ? " · " + note : "") + " — fit fills in shortly", "ok");
        flashLabel("✓");
      } else { showToast("error: " + ((result && result.error) || "unknown"), "err"); }
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

  // The toolbar popup delegates here so the button and the pill share ONE capture path. The service
  // worker's stitch-capture fallback (background.js) also messages us: it can't scroll the page or
  // read its geometry without the debugger, so it asks us for page metrics and to scroll to each
  // viewport offset between captureVisibleTab shots.
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg && msg.type === "triggerCapture") {
      if (busy) { sendResponse({ ok: false, error: "already capturing" }); return; }
      doCapture().then(sendResponse).catch((e) => sendResponse({ ok: false, error: String(e) }));
      return true;   // async response
    }
    if (msg && msg.type === "pageMetrics") {
      const body = document.body;
      sendResponse({
        scrollHeight: Math.max(document.documentElement.scrollHeight, body ? body.scrollHeight : 0),
        innerHeight: window.innerHeight,
        innerWidth: window.innerWidth,
        dpr: window.devicePixelRatio || 1,
        scrollY: window.scrollY || 0,
      });
      return;   // synchronous response
    }
    if (msg && msg.type === "scrollTo") {
      window.scrollTo(0, msg.y || 0);
      // Report the ACTUAL post-scroll position: the browser clamps at max scroll, so the last frame
      // lands short of the requested y - the stitcher needs the real offset to place it correctly.
      sendResponse({ y: window.scrollY || 0 });
      return;   // synchronous response
    }
  });

  if (document.readyState === "complete" || document.readyState === "interactive") mountPill();
  else window.addEventListener("DOMContentLoaded", mountPill);
})();
