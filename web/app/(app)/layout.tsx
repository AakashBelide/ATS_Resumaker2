// App-shell layout for the GATED pages (route group `(app)` — the parentheses don't affect URLs).
// Everything here sits behind the login middleware; public pages (landing `/`, `/login`, `/setup`)
// use the bare root layout instead, so they render without the sidebar/app grid.
import Sidebar from "@/components/Sidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <Sidebar />
      <div className="content">{children}</div>
    </div>
  );
}
