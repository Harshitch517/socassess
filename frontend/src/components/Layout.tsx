import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api, type Health } from "../api";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/review", label: "Review queue" },
  { to: "/findings", label: "Findings" },
  { to: "/clusters", label: "Alert clusters" },
  { to: "/trends", label: "Trends" },
  { to: "/upload", label: "Data upload" },
  { to: "/reports", label: "Reports & audit" },
];

type Theme = "light" | "dark" | "system";

function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem("theme") as Theme) || "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    try {
      if (theme === "system") localStorage.removeItem("theme");
      else localStorage.setItem("theme", theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);
  return [theme, setTheme];
}

export default function Layout() {
  const [theme, setTheme] = useTheme();
  const [health, setHealth] = useState<Health | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    api.health().then(setHealth, () => setHealth(null));
  }, []);
  const link = ({ isActive }: { isActive: boolean }) =>
    `block rounded-lg px-3 py-1.5 text-sm ${
      isActive ? "bg-accent-wash font-medium text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink"
    }`;
  return (
    <div className="min-h-screen lg:flex">
      <aside className="border-b border-line bg-surface lg:sticky lg:top-0 lg:h-screen lg:w-56 lg:shrink-0 lg:border-r lg:border-b-0">
        <div className="flex items-center justify-between px-4 py-3 lg:block lg:py-5">
          <div>
            <div className="text-base font-semibold tracking-tight text-ink">SOCAssess</div>
            <div className="text-xs text-muted">Supervisory SOC analytics</div>
          </div>
          <button
            className="rounded-md border border-line px-2 py-1 text-sm text-ink-2 lg:hidden"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-label="Toggle navigation"
          >
            Menu
          </button>
        </div>
        <nav className={`${open ? "block" : "hidden"} space-y-0.5 px-2 pb-3 lg:block`} onClick={() => setOpen(false)}>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={link}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className={`${open ? "block" : "hidden"} space-y-3 border-t border-line px-4 py-3 text-xs text-muted lg:absolute lg:bottom-0 lg:block lg:w-56`}>
          <label className="flex items-center justify-between gap-2">
            <span>Theme</span>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value as Theme)}
              className="rounded-md border border-line bg-surface px-1.5 py-0.5 text-ink"
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
          <div>
            {health ? (
              <>
                API v{health.version}
                {health.read_only && " · demo (read-only)"}
                <br />
                Run {health.latest_run ?? "none"}
              </>
            ) : (
              "API not reachable"
            )}
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-5 lg:px-8 lg:py-7">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
