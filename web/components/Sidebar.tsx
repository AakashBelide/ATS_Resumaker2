"use client";
// Left rail navigation for the 6 platform pages. Active state from the current path.
// - Desktop: a collapse toggle shrinks the rail to an icon strip (body.rail-collapsed drives
//   the .app grid so the content reflows). Persisted in localStorage.
// - Mobile: the rail is an off-canvas drawer toggled by the hamburger.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const NAV = [
  { href: "/", label: "Discovery", idx: "01" },
  { href: "/tracker", label: "Tracker", idx: "02" },
  { href: "/onboard", label: "Onboarding", idx: "03" },
  { href: "/profile", label: "Profile", idx: "04" },
  { href: "/dashboard", label: "Dashboard", idx: "05" },
  { href: "/metrics", label: "Metrics", idx: "06" },
];

export default function Sidebar() {
  const path = usePathname();
  const [open, setOpen] = useState(false);          // mobile drawer
  const [collapsed, setCollapsed] = useState(false); // desktop icon-rail

  useEffect(() => { setOpen(false); }, [path]);      // close drawer on navigation
  useEffect(() => {
    const saved = localStorage.getItem("rail.collapsed") === "1";
    setCollapsed(saved);
  }, []);
  useEffect(() => {
    document.body.classList.toggle("rail-collapsed", collapsed);
    localStorage.setItem("rail.collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  return (
    <>
      <button className="rail-toggle" aria-label="menu" onClick={() => setOpen((o) => !o)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" width="20" height="20">
          <path d="M3 6h18M3 12h18M3 18h18" />
        </svg>
      </button>
      {open && <div className="rail-backdrop" onClick={() => setOpen(false)} />}
      <nav className="rail" data-open={open}>
        <div className="rail-brand">
          <span className="rail-hex" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z" />
              <path d="M12 7l4.33 2.5v5L12 17l-4.33-2.5v-5L12 7z" fill="currentColor" opacity="0.35" stroke="none" />
            </svg>
          </span>
          <div className="rail-brand-txt">
            <b>resumaker</b>
            <span>ATS · watchlist</span>
          </div>
          <button className="rail-collapse" aria-label="collapse sidebar" title="collapse / expand"
                  onClick={() => setCollapsed((c) => !c)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
              <path d={collapsed ? "M9 6l6 6-6 6" : "M15 6l-6 6 6 6"} />
            </svg>
          </button>
        </div>

        {NAV.map((n) => {
          const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
          return (
            <Link key={n.href} href={n.href} className={`rail-link${active ? " active" : ""}`} title={n.label}>
              <span className="ico" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                     strokeLinecap="round" strokeLinejoin="round" width="17" height="17">
                  <circle cx="12" cy="12" r="9" />
                  <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
                </svg>
              </span>
              <span className="rail-label">{n.label}</span>
              <span className="rail-idx">{n.idx}</span>
            </Link>
          );
        })}

        <div className="rail-foot">v0.1 · self-hosted</div>
      </nav>
    </>
  );
}
