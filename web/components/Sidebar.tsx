"use client";
// Left rail navigation for the 6 platform pages. Active state from the current path.
import Link from "next/link";
import { usePathname } from "next/navigation";

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
  return (
    <nav className="rail">
      <div className="rail-brand">
        <span className="rail-hex" aria-hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z" />
            <path d="M12 7l4.33 2.5v5L12 17l-4.33-2.5v-5L12 7z" fill="currentColor" opacity="0.35" stroke="none" />
          </svg>
        </span>
        <div>
          <b>resumaker</b>
          <span>ATS · watchlist</span>
        </div>
      </div>

      {NAV.map((n) => {
        const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
        return (
          <Link key={n.href} href={n.href} className={`rail-link${active ? " active" : ""}`}>
            <span className="ico" aria-hidden>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                   strokeLinecap="round" strokeLinejoin="round" width="17" height="17">
                <circle cx="12" cy="12" r="9" />
                <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
              </svg>
            </span>
            {n.label}
            <span className="rail-idx">{n.idx}</span>
          </Link>
        );
      })}

      <div className="rail-foot">v0.1 · self-hosted</div>
    </nav>
  );
}
