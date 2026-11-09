import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError, type Severity } from "../api";

// ---------------------------------------------------------------- data loading
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: ApiError | Error; loading: boolean }>({ loading: true });
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true, error: undefined }));
    fn().then(
      (data) => live && setState({ data, loading: false }),
      (error) => live && setState({ error, loading: false }),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { ...state, reload };
}

export function Loader({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-ink-2" role="status">
      <span className="h-3 w-3 animate-pulse rounded-full bg-accent" />
      {label}…
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const noRun = error instanceof ApiError && error.status === 404 && /No analysis run/.test(error.message);
  return (
    <div className="rounded-lg border border-line bg-surface p-5 text-sm" role="alert">
      <p className="font-medium text-ink">{noRun ? "No analysis results yet" : "Something went wrong"}</p>
      <p className="mt-1 text-ink-2">{error.message}</p>
      {error instanceof ApiError && error.errors.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-ink-2">
          {error.errors.slice(0, 20).map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex gap-3">
        {noRun && (
          <Link className="font-medium text-accent hover:underline" to="/">
            Upload data
          </Link>
        )}
        {onRetry && (
          <button className="font-medium text-accent hover:underline" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function Async<T>({
  state,
  children,
}: {
  state: { data?: T; error?: Error; loading: boolean; reload: () => void };
  children: (data: T) => ReactNode;
}) {
  if (state.error) return <ErrorBox error={state.error} onRetry={state.reload} />;
  if (state.data === undefined) return <Loader />;
  return <>{children(state.data)}</>;
}

// ---------------------------------------------------------------- layout bits
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Card({
  title,
  subtitle,
  children,
  actions,
  className = "",
}: {
  title?: string;
  subtitle?: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`min-w-0 rounded-xl border border-line bg-surface p-4 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-2">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatTile({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="text-xs text-ink-2">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function Button({
  children,
  onClick,
  href,
  variant = "secondary",
  disabled,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  href?: string;
  variant?: "primary" | "secondary";
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const cls =
    variant === "primary"
      ? "bg-accent text-white hover:opacity-90"
      : "border border-line bg-surface text-ink hover:bg-surface-2";
  const base = `inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${cls}`;
  if (href)
    return (
      <a className={base} href={href} download>
        {children}
      </a>
    );
  return (
    <button type={type} className={base} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

// ---------------------------------------------------------------- severity (status colours, always with a label)
const SEV_COLOR: Record<Severity, string> = {
  critical: "var(--st-critical)",
  high: "var(--st-serious)",
  medium: "var(--st-warning)",
  low: "var(--muted)",
};
const SEV_ICON: Record<Severity, string> = { critical: "▲", high: "◆", medium: "●", low: "○" };

export function SeverityBadge({ severity, label }: { severity: Severity; label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border border-line bg-surface-2 px-1.5 py-0.5 text-xs font-medium text-ink">
      <span aria-hidden style={{ color: SEV_COLOR[severity] }}>
        {SEV_ICON[severity]}
      </span>
      {label ?? severity}
    </span>
  );
}

export const sevColor = (s: Severity) => SEV_COLOR[s];

// ---------------------------------------------------------------- naming
export const TYPE_LABEL: Record<string, string> = {
  fast_closure: "Fast closure",
  critical_no_escalation: "Critical not escalated",
  template_notes: "Copy-paste notes",
  repeated_no_remediation: "Repeat alerts, no fix",
  sla_gaming: "SLA deadline bunching",
  sla_breach: "SLA breaches",
  silent_critical_assets: "Silent critical assets",
  missing_categories: "Missing alert categories",
  missing_records: "Missing records",
  low_activity: "Low activity",
  operational_anomaly: "Operational anomaly",
  spot_check: "Control spot-check",
};
export const typeLabel = (t: string) => TYPE_LABEL[t] ?? t.replace(/_/g, " ");

export const CATEGORY_LABEL: Record<string, string> = {
  execution_gap: "Execution gap",
  negative_space: "Negative space",
  anomaly: "Anomaly",
};

// ---------------------------------------------------------------- formatting
export const fmtInt = (n: number | null | undefined) => (n == null ? "–" : Math.round(n).toLocaleString("en-US"));
export const fmtNum = (n: number | null | undefined, d = 2) =>
  n == null || Number.isNaN(n) ? "–" : Math.abs(n) >= 100 ? fmtInt(n) : Number(n.toFixed(d)).toString();
export const fmtPct = (n: number | null | undefined, d = 1) => (n == null ? "–" : `${(n * 100).toFixed(d)}%`);
export const fmtDate = (s: string | null | undefined) =>
  s ? new Date(s).toISOString().replace("T", " ").slice(0, 16) + " UTC" : "–";

export function Table({
  columns,
  rows,
  empty = "Nothing to show",
  onRowClick,
}: {
  columns: { key: string; label: string; render?: (row: Record<string, unknown>) => ReactNode; align?: "right" }[];
  rows: Record<string, unknown>[];
  empty?: string;
  onRowClick?: (row: Record<string, unknown>) => void;
}) {
  if (!rows.length) return <p className="py-6 text-center text-sm text-muted">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-2">
            {columns.map((c) => (
              <th key={c.key} className={`whitespace-nowrap px-2 py-2 font-medium ${c.align === "right" ? "text-right" : ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              className={`border-b border-line last:border-0 hover:bg-surface-2 ${onRowClick ? "cursor-pointer" : ""}`}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(r) : undefined}
              tabIndex={onRowClick ? 0 : undefined}
            >
              {columns.map((c) => (
                <td key={c.key} className={`px-2 py-2 align-top ${c.align === "right" ? "tnum text-right" : ""}`}>
                  {c.render ? c.render(r) : String(r[c.key] ?? "–")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-line bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium ${
            value === o.value ? "bg-accent-wash text-ink" : "text-ink-2 hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
