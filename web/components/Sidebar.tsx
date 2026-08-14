"use client";
// Left rail navigation for the 6 platform pages. Active state from the current path.
// - Desktop: a collapse toggle shrinks the rail to an icon strip (body.rail-collapsed drives
//   the .app grid so the content reflows). Persisted in localStorage.
// - Mobile: the rail is an off-canvas drawer toggled by the hamburger.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

// Per-page glyphs (stroke paths inside a 24x24 viewBox) so the collapsed icon-rail is legible.
const NAV = [
  { href: "/discovery", label: "Discovery", idx: "01", icon: <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></> },
  { href: "/tracker", label: "Tracker", idx: "02", icon: <><rect x="3" y="4" width="7" height="16" rx="1" /><rect x="14" y="4" width="7" height="10" rx="1" /></> },
  { href: "/onboard", label: "Onboarding", idx: "03", icon: <><rect x="4" y="3" width="16" height="18" rx="1.5" /><path d="M9 21v-4h6v4M9 8h.01M15 8h.01M9 12h.01M15 12h.01" /></> },
  { href: "/profile", label: "Profile", idx: "04", icon: <><circle cx="12" cy="8" r="4" /><path d="M4.5 21c0-4 3.6-6 7.5-6s7.5 2 7.5 6" /></> },
  { href: "/profile-agent", label: "Assistant", idx: "05", icon: <><path d="M12 3a4 4 0 0 1 4 4v1a4 4 0 0 1-8 0V7a4 4 0 0 1 4-4z" /><path d="M5 21v-1a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v1" /><path d="M9 10h.01M15 10h.01" /></> },
  { href: "/mailer", label: "Mailer", idx: "06", icon: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 7l9 6 9-6" /></> },
  { href: "/dashboard", label: "Dashboard", idx: "07", icon: <><rect x="3" y="3" width="8" height="8" rx="1" /><rect x="13" y="3" width="8" height="5" rx="1" /><rect x="13" y="10" width="8" height="11" rx="1" /><rect x="3" y="13" width="8" height="8" rx="1" /></> },
  { href: "/metrics", label: "Metrics", idx: "08", icon: <><path d="M3 21h18" /><path d="M7 21V11M12 21V5M17 21v-7" /></> },
];

export default function Sidebar() {
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);          // mobile drawer
  const [collapsed, setCollapsed] = useState(false); // desktop icon-rail

  async function logout() {
    try { await fetch("/api/logout", { method: "POST" }); } catch { /* clear anyway */ }
    router.push("/login");
    router.refresh();
  }

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
            <b>ATS Resumaker</b>
          </div>
          <button className="rail-collapse" aria-label="collapse sidebar" title="collapse / expand"
                  onClick={() => setCollapsed((c) => !c)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
              <path d={collapsed ? "M9 6l6 6-6 6" : "M15 6l-6 6 6 6"} />
            </svg>
          </button>
        </div>

        {NAV.map((n) => {
          const active = path === n.href || path.startsWith(n.href + "/");
          return (
            <Link key={n.href} href={n.href} className={`rail-link${active ? " active" : ""}`} title={n.label}>
              <span className="ico" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                     strokeLinecap="round" strokeLinejoin="round" width="18" height="18">
                  {n.icon}
                </svg>
              </span>
              <span className="rail-label">{n.label}</span>
              <span className="rail-idx">{n.idx}</span>
            </Link>
          );
        })}

        <button className="rail-link rail-logout" onClick={logout} title="Log out">
          <span className="ico" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                 strokeLinecap="round" strokeLinejoin="round" width="18" height="18">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
            </svg>
          </span>
          <span className="rail-label">Log out</span>
        </button>
      </nav>
    </>
  );
}
