"use client";
// Docs side-nav with scroll-spy (highlights the section you're in) and a top reading-progress bar.
import { useEffect, useState } from "react";

export default function DocNav({ items }: { items: [string, string][] }) {
  const [active, setActive] = useState(items[0]?.[0] ?? "");
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const sections = items
      .map(([id]) => document.getElementById(id))
      .filter((el): el is HTMLElement => el != null);
    const onScroll = () => {
      const doc = document.documentElement;
      const scrollable = doc.scrollHeight - doc.clientHeight;
      setProgress(scrollable > 0 ? Math.min(1, doc.scrollTop / scrollable) : 0);
      const y = window.scrollY + 130;
      let cur = sections[0]?.id ?? active;
      for (const s of sections) if (s.offsetTop <= y) cur = s.id;
      // near the very bottom, force the last section active
      if (scrollable > 0 && doc.scrollTop >= scrollable - 4) cur = sections[sections.length - 1]?.id ?? cur;
      setActive(cur);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    onScroll();
    return () => { window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  return (
    <>
      <div className="doc-progress" aria-hidden><span style={{ transform: `scaleX(${progress})` }} /></div>
      <aside className="doc-side">
        <p className="doc-side-h mono">On this page</p>
        {items.map(([id, label]) => (
          <a key={id} href={`#${id}`} className={`doc-side-link ${active === id ? "active" : ""}`}>{label}</a>
        ))}
      </aside>
    </>
  );
}
