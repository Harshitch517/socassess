import {
  BarChart3, ChevronDown, ChevronRight, ClipboardCheck, FileText, Gauge, Layers, ListChecks, Moon, PlusCircle,
  ShieldCheck, Sun, TrendingUp,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api, type Health } from "../api";

const START = [
  { to: "/", label: "New analysis", Icon: PlusCircle, end: true },
  { to: "/results", label: "My results", Icon: BarChart3 },
];
const ADVANCED = [
  { to: "/overview", label: "Dashboard", Icon: Gauge },
  { to: "/review", label: "Review queue", Icon: ClipboardCheck },
  { to: "/findings", label: "All findings", Icon: ListChecks },
  { to: "/clusters", label: "Alert clusters", Icon: Layers },
  { to: "/trends", label: "Trends", Icon: TrendingUp },
  { to: "/reports", label: "Reports & audit", Icon: FileText },
];

type Theme = "light" | "dark";

function useTheme(): [Theme, (t: Theme) => void] {
  // dark by default; the viewer's choice is remembered in this browser only
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return localStorage.getItem("theme") === "light" ? "light" : "dark";
    } catch {
      return "dark";
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
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
  const loc = useLocation();
  const inAdvanced = ADVANCED.some((a) => loc.pathname.startsWith(a.to)) || /^\/(entities|findings)\//.test(loc.pathname);
  const [adv, setAdv] = useState(inAdvanced);
  useEffect(() => {
    if (inAdvanced) setAdv(true);
  }, [inAdvanced]);
  useEffect(() => {
    api.health().then(setHealth, () => setHealth(null));
  }, []);
  const link = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2.5 rounded-xl px-3 py-2 ${
      isActive ? "bg-accent-wash font-semibold text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink"
    }`;
  return (
    <div className="min-h-screen lg:flex">
      <aside className="border-b border-line bg-surface/80 backdrop-blur lg:sticky lg:top-0 lg:flex lg:h-screen lg:w-60 lg:shrink-0 lg:flex-col lg:border-r lg:border-b-0">
        <div className="flex items-center justify-between px-4 py-3 lg:py-5">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white">
              <ShieldCheck className="h-5 w-5" aria-hidden />
            </span>
            <div>
              <div className="text-base font-semibold tracking-tight text-ink">SOCAssess</div>
              <div className="text-xs text-muted">SOC security health check</div>
            </div>
          </div>
          <button className="rounded-lg border border-line px-3 py-1.5 text-sm text-ink-2 lg:hidden" onClick={() => setOpen(!open)}
            aria-expanded={open} aria-label="Toggle navigation">
            Menu
          </button>
        </div>
        <nav className={`${open ? "block" : "hidden"} flex-1 overflow-y-auto px-3 pb-3 lg:block`} onClick={() => setOpen(false)}>
          <div className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted">Start</div>
          <div className="space-y-0.5">
            {START.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={link}>
                <n.Icon className="h-5 w-5" aria-hidden /> {n.label}
              </NavLink>
            ))}
          </div>
          <button className="mt-5 flex w-full items-center gap-1 px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted hover:text-ink"
            onClick={(e) => { e.stopPropagation(); setAdv(!adv); }} aria-expanded={adv}>
            {adv ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />} Advanced (for analysts)
          </button>
          {adv && (
            <div className="space-y-0.5">
              {ADVANCED.map((n) => (
                <NavLink key={n.to} to={n.to} className={link}>
                  <n.Icon className="h-5 w-5" aria-hidden /> {n.label}
                </NavLink>
              ))}
            </div>
          )}
        </nav>
        <div className={`${open ? "flex" : "hidden"} items-center justify-between gap-2 border-t border-line px-4 py-3 text-xs text-muted lg:flex`}>
          <span title={health ? `API v${health.version} · run ${health.latest_run ?? "none"}` : "API not reachable"}>
            {health ? (health.read_only ? "Demo (read-only)" : "Running offline") : "API not reachable"}
          </span>
          <button className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-ink-2 hover:text-ink"
            onClick={() => setTheme(theme === "light" ? "dark" : "light")} aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}>
            {theme === "light" ? <Moon className="h-3.5 w-3.5" /> : <Sun className="h-3.5 w-3.5" />}
            {theme === "light" ? "Dark" : "Light"}
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
