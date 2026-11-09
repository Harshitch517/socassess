import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Benchmark, EntityScore, Severity } from "../api";
import { fmtNum, SeverityBadge, typeLabel } from "./ui";

// ---------------------------------------------------------------- floating tooltip
export function useTip() {
  const [tip, setTip] = useState<{ x: number; y: number; content: ReactNode } | null>(null);
  const show = (e: React.MouseEvent | React.FocusEvent, content: ReactNode) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setTip({ x: r.left + r.width / 2, y: r.top, content });
  };
  const node = tip && (
    <div
      role="tooltip"
      className="pointer-events-none fixed z-50 max-w-xs -translate-x-1/2 -translate-y-full rounded-lg border border-line bg-surface px-3 py-2 text-xs text-ink shadow-lg"
      style={{ left: tip.x, top: tip.y - 6 }}
    >
      {tip.content}
    </div>
  );
  return { show, hide: () => setTip(null), node };
}

// ---------------------------------------------------------------- risk ranking (single series, horizontal bars)
export function RiskBars({ entities }: { entities: EntityScore[] }) {
  const tip = useTip();
  const max = Math.max(50, ...entities.map((e) => e.risk_score));
  return (
    <div>
      <ul className="space-y-1.5">
        {entities.map((e) => (
          <li key={e.entity_id} className="grid grid-cols-[minmax(0,11rem)_1fr_3rem] items-center gap-3 text-sm">
            <Link to={`/entities/${e.entity_id}`} className="truncate text-ink hover:text-accent hover:underline" title={e.name}>
              <span className="tnum text-muted">{e.rank}.</span> {e.entity_id}{" "}
              <span className="text-ink-2">{e.name}</span>
            </Link>
            <div className="relative h-5">
              {e.risk_score > 0 ? (
                <div
                  tabIndex={0}
                  aria-label={`${e.entity_id} risk ${e.risk_score}`}
                  className="absolute top-1/2 left-0 h-3 -translate-y-1/2 rounded-r-[4px] bg-[var(--series-1)]"
                  style={{ width: `${(e.risk_score / max) * 100}%` }}
                  onMouseEnter={(ev) => tip.show(ev, <Breakdown e={e} />)}
                  onFocus={(ev) => tip.show(ev, <Breakdown e={e} />)}
                  onMouseLeave={tip.hide}
                  onBlur={tip.hide}
                />
              ) : (
                <div className="absolute top-1/2 left-0 h-px w-full -translate-y-1/2 bg-grid" />
              )}
            </div>
            <span className="tnum text-right text-ink">{fmtNum(e.risk_score, 1)}</span>
          </li>
        ))}
      </ul>
      <div className="mt-2 grid grid-cols-[minmax(0,11rem)_1fr_3rem] gap-3 text-[11px] text-muted">
        <span />
        <div className="flex justify-between border-t border-[var(--axis)] pt-1 tnum">
          <span>0</span>
          <span>{max / 2}</span>
          <span>{max}</span>
        </div>
        <span className="text-right">score</span>
      </div>
      {tip.node}
    </div>
  );
}

function Breakdown({ e }: { e: EntityScore }) {
  return (
    <div className="space-y-1">
      <div className="font-medium">
        {e.entity_id} {e.name}: {fmtNum(e.risk_score, 1)} pts
      </div>
      {e.breakdown.slice(0, 6).map((b) => (
        <div key={b.finding_id} className="flex justify-between gap-3">
          <span className="text-ink-2">{typeLabel(b.type)}</span>
          <span className="tnum">+{fmtNum(b.points, 2)}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- heatmap (sequential blue)
const HEAT_STEPS = [0, 3, 6, 10, 15];
export const heatVar = (pts: number) => {
  if (!pts) return "var(--heat-0)";
  const i = HEAT_STEPS.filter((s) => pts > s).length; // 1..5
  return `var(--heat-${i})`;
};

export function Heatmap({
  entities,
  types,
  cells,
}: {
  entities: { entity_id: string; name: string; risk_score: number }[];
  types: string[];
  cells: { entity_id: string; type: string; points: number; findings: number; severity: Severity }[];
}) {
  const tip = useTip();
  const map = new Map(cells.map((c) => [`${c.entity_id}|${c.type}`, c]));
  const used = types.filter((t) => cells.some((c) => c.type === t));
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-[2px] text-xs">
          <thead>
            <tr>
              <th />
              {used.map((t) => (
                <th key={t} className="h-28 w-9 align-bottom font-normal text-ink-2">
                  <div className="mx-auto w-4 [writing-mode:vertical-rl] rotate-180 whitespace-nowrap text-left">
                    {typeLabel(t)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entities.map((e) => (
              <tr key={e.entity_id}>
                <th className="whitespace-nowrap pr-2 text-left font-normal">
                  <Link to={`/entities/${e.entity_id}`} className="text-ink hover:text-accent hover:underline">
                    {e.entity_id}
                  </Link>
                </th>
                {used.map((t) => {
                  const c = map.get(`${e.entity_id}|${t}`);
                  const body = c ? (
                    <div className="space-y-1">
                      <div className="font-medium">
                        {e.entity_id} · {typeLabel(t)}
                      </div>
                      <SeverityBadge severity={c.severity} />
                      <div>
                        {fmtNum(c.points, 2)} risk points · {c.findings} finding{c.findings > 1 ? "s" : ""}
                      </div>
                      <div className="text-muted">Click to open</div>
                    </div>
                  ) : (
                    <div>
                      {e.entity_id} · {typeLabel(t)}: no finding
                    </div>
                  );
                  const cell = (
                    <div
                      className="h-7 w-9 rounded-[4px]"
                      style={{ background: heatVar(c?.points ?? 0) }}
                      tabIndex={0}
                      aria-label={`${e.entity_id} ${typeLabel(t)}: ${c ? `${c.points} points` : "none"}`}
                      onMouseEnter={(ev) => tip.show(ev, body)}
                      onFocus={(ev) => tip.show(ev, body)}
                      onMouseLeave={tip.hide}
                      onBlur={tip.hide}
                    />
                  );
                  return (
                    <td key={t} className="p-0">
                      {c ? <Link to={`/findings?entity_id=${e.entity_id}&type=${t}`}>{cell}</Link> : cell}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-ink-2">
        <span>Risk points:</span>
        {["0", "≤3", "≤6", "≤10", "≤15", ">15"].map((l, i) => (
          <span key={l} className="inline-flex items-center gap-1">
            <span className="h-3 w-4 rounded-[3px]" style={{ background: `var(--heat-${i})` }} />
            {l}
          </span>
        ))}
      </div>
      {used.length === 0 && <p className="py-4 text-sm text-muted">No findings in this run.</p>}
      {tip.node}
    </div>
  );
}

// ---------------------------------------------------------------- simple horizontal bars (single series)
export function HBars({
  rows,
  format = (v: number) => fmtNum(v, 2),
  unit,
}: {
  rows: { label: ReactNode; value: number; key: string; tip?: ReactNode }[];
  format?: (v: number) => string;
  unit?: string;
}) {
  const tip = useTip();
  const max = Math.max(...rows.map((r) => r.value), 1e-9);
  return (
    <div>
      <ul className="space-y-1.5">
        {rows.map((r) => (
          <li key={r.key} className="grid grid-cols-[minmax(0,14rem)_1fr_4rem] items-center gap-3 text-sm">
            <span className="truncate text-ink-2">{r.label}</span>
            <div className="relative h-5">
              <div
                tabIndex={0}
                className="absolute top-1/2 left-0 h-3 -translate-y-1/2 rounded-r-[4px] bg-[var(--series-1)]"
                style={{ width: `${Math.max(0.5, (r.value / max) * 100)}%` }}
                onMouseEnter={(ev) => tip.show(ev, r.tip ?? `${format(r.value)}${unit ? ` ${unit}` : ""}`)}
                onFocus={(ev) => tip.show(ev, r.tip ?? format(r.value))}
                onMouseLeave={tip.hide}
                onBlur={tip.hide}
              />
            </div>
            <span className="tnum text-right text-ink">{format(r.value)}</span>
          </li>
        ))}
      </ul>
      {tip.node}
    </div>
  );
}

// ---------------------------------------------------------------- peer comparison strip
export function PeerStrip({ b, peers }: { b: Benchmark; peers: number[] }) {
  const tip = useTip();
  const all = [...peers, b.value].filter((v) => v != null && Number.isFinite(v));
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (hi - lo < 1e-9) {
    lo -= 0.5;
    hi += 0.5;
  }
  const pos = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  // red only for metrics with a known "worse" direction; two-sided metrics stay neutral
  const bad = b.direction !== 0 && Math.abs(b.z) >= 3 && Math.sign(b.z) === b.direction;
  return (
    <div className="relative h-6 w-full min-w-[8rem]">
      <div className="absolute top-1/2 h-px w-full bg-grid" />
      {b.peer_median_all != null && (
        <div className="absolute top-1 h-4 w-px bg-[var(--axis)]" style={{ left: pos(b.peer_median_all) }} title="peer median" />
      )}
      {peers.map((p, i) => (
        <div
          key={i}
          className="absolute top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--muted)] opacity-60"
          style={{ left: pos(p) }}
        />
      ))}
      <div
        tabIndex={0}
        aria-label={`${b.description}: ${fmtNum(b.value, 3)}, peer median ${fmtNum(b.peer_median_all ?? NaN, 3)}`}
        className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-[var(--surface-1)]"
        style={{ left: pos(b.value), background: bad ? "var(--st-critical)" : "var(--series-1)" }}
        onMouseEnter={(ev) =>
          tip.show(
            ev,
            <div>
              <div className="font-medium">{b.description}</div>
              <div>This entity: {fmtNum(b.value, 3)}</div>
              <div>Peer median: {fmtNum(b.peer_median_all ?? NaN, 3)}</div>
              <div>
                Percentile {Math.round(b.percentile * 100)} · z {fmtNum(b.z, 1)}
              </div>
            </div>,
          )
        }
        onMouseLeave={tip.hide}
      />
      {tip.node}
    </div>
  );
}

// ---------------------------------------------------------------- multi-series line (<= 4 entities)
export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

export function TrendLines({
  data,
  series,
  yLabel,
}: {
  data: Record<string, number | string | null>[];
  series: { key: string; name: string; color: string }[];
  yLabel: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="week" tickMargin={6} minTickGap={24} />
        <YAxis width={48} tickFormatter={(v: number) => (v >= 10000 ? `${Math.round(v / 1000)}K` : String(v))}
          label={{ value: yLabel, angle: -90, position: "insideLeft", fill: "var(--muted)", fontSize: 11, dx: 8 }} />
        <Tooltip
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "var(--ink)", fontWeight: 600 }}
          itemStyle={{ color: "var(--ink)" }}
          cursor={{ stroke: "var(--axis)" }}
          formatter={(v) => (typeof v === "number" ? fmtNum(v, 2) : String(v))}
        />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }}
          formatter={(value) => <span style={{ color: "var(--ink-2)" }}>{value}</span>} />
        {series.map((s) => (
          <Line key={s.key} dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} dot={false}
            activeDot={{ r: 4, stroke: "var(--surface-1)", strokeWidth: 2 }} connectNulls isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function Sparkline({ data, xKey, yKey, label }: { data: Record<string, unknown>[]; xKey: string; yKey: string; label: string }) {
  return (
    <ResponsiveContainer width="100%" height={140}>
      <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={xKey} minTickGap={40} tickMargin={4} />
        <YAxis width={48} />
        <Tooltip
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "var(--ink)" }}
          itemStyle={{ color: "var(--ink)" }}
        />
        <Line dataKey={yKey} name={label} stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------- donut (part-to-whole, <= 7 slices)
export interface Slice {
  key: string;
  label: string;
  value: number;
  color: string;
  hint?: string;
}

export function Donut({ slices, total, centerLabel, empty = "Nothing to show" }: {
  slices: Slice[];
  total?: number;
  centerLabel: string;
  empty?: string;
}) {
  const tip = useTip();
  const data = slices.filter((s) => s.value > 0);
  const sum = data.reduce((a, s) => a + s.value, 0);
  const size = 168;
  const r = 70;
  const w = 20; // ring thickness: a thin mark, the hole carries the total
  const cx = size / 2;
  const C = 2 * Math.PI * r;
  const gap = data.length > 1 ? 2 : 0; // 2px surface gap between slices
  let acc = 0;
  const pct = (v: number) => (sum ? `${Math.round((v / sum) * 100)}%` : "0%");
  const fmt = (v: number) => v.toLocaleString("en-US");
  return (
    <div className="flex flex-wrap items-center gap-5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
        aria-label={`${centerLabel}: ${data.map((s) => `${s.label} ${fmt(s.value)}`).join(", ") || "none"}`}>
        <circle cx={cx} cy={cx} r={r} fill="none" stroke="var(--grid)" strokeWidth={w} />
        {data.map((s) => {
          const len = (s.value / sum) * C;
          const dash = Math.max(0, len - gap);
          const el = (
            <circle key={s.key} cx={cx} cy={cx} r={r} fill="none" stroke={s.color} strokeWidth={w}
              strokeDasharray={`${dash} ${C - dash}`} strokeDashoffset={-acc}
              transform={`rotate(-90 ${cx} ${cx})`} tabIndex={0} className="cursor-default outline-none"
              onMouseEnter={(e) => tip.show(e as never, <span><b>{s.label}</b>: {fmt(s.value)} ({pct(s.value)}){s.hint ? <><br />{s.hint}</> : null}</span>)}
              onFocus={(e) => tip.show(e as never, <span><b>{s.label}</b>: {fmt(s.value)} ({pct(s.value)})</span>)}
              onMouseLeave={tip.hide} onBlur={tip.hide} />
          );
          acc += len;
          return el;
        })}
        <text x={cx} y={cx - 2} textAnchor="middle" className="fill-[var(--ink)]" fontSize="26" fontWeight="600">
          {fmt(total ?? sum)}
        </text>
        <text x={cx} y={cx + 18} textAnchor="middle" className="fill-[var(--ink-2)]" fontSize="11">{centerLabel}</text>
      </svg>
      {data.length === 0 ? (
        <p className="text-sm text-muted">{empty}</p>
      ) : (
        <ul className="min-w-[10rem] flex-1 space-y-1.5 text-sm">
          {data.map((s) => (
            <li key={s.key} className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: s.color }} aria-hidden />
              <span className="min-w-0 flex-1 truncate text-ink-2" title={s.hint ?? s.label}>{s.label}</span>
              <span className="tnum text-ink">{fmt(s.value)}</span>
              <span className="tnum w-10 text-right text-muted">{pct(s.value)}</span>
            </li>
          ))}
        </ul>
      )}
      {tip.node}
    </div>
  );
}

export const SEVERITY_SLICES = [
  { key: "critical", label: "Critical", color: "var(--st-critical)" },
  { key: "high", label: "High", color: "var(--st-serious)" },
  { key: "medium", label: "Medium", color: "var(--st-warning)" },
  { key: "low", label: "Low", color: "var(--muted)" },
];
export const CATEGORY_COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)",
  "var(--series-5)", "var(--series-6)"];
