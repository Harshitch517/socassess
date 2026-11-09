import { useMemo, useState } from "react";
import { api, type Week } from "../api";
import { SERIES, TrendLines } from "../components/charts";
import { Async, Card, fmtNum, PageHeader, Segmented, Table, useAsync } from "../components/ui";

const METRICS: { key: keyof Week; label: string; unit: string }[] = [
  { key: "alerts", label: "Alerts", unit: "alerts / week" },
  { key: "high_critical", label: "High/critical alerts", unit: "alerts / week" },
  { key: "cases_closed", label: "Cases closed", unit: "cases / week" },
  { key: "median_ttc_hours", label: "Median time to close", unit: "hours" },
  { key: "fast_closures", label: "Fast closures", unit: "cases / week" },
  { key: "sla_breaches", label: "SLA breaches", unit: "cases / week" },
  { key: "escalated", label: "Escalations", unit: "cases / week" },
];
const MAX_SERIES = 4;

export default function Trends() {
  const ents = useAsync(() => api.entities(), []);
  const [picked, setPicked] = useState<string[] | null>(null);
  const [metric, setMetric] = useState<keyof Week>("fast_closures");
  const [view, setView] = useState<"chart" | "table">("chart");
  const defaultPick = ents.data?.entities.filter((e) => e.has_case_data).slice(0, 3).map((e) => e.entity_id) ?? [];
  const sel = picked ?? defaultPick;
  const st = useAsync(() => (sel.length ? api.trends(sel) : Promise.resolve({ run_id: "", weeks: [] as Week[] })), [sel.join(",")]);
  const m = METRICS.find((x) => x.key === metric)!;

  const data = useMemo(() => {
    const byWeek = new Map<string, Record<string, number | string | null>>();
    for (const w of st.data?.weeks ?? []) {
      const row = byWeek.get(w.week) ?? { week: w.week };
      row[w.entity_id] = (w[metric] as number | null) ?? null;
      byWeek.set(w.week, row);
    }
    return [...byWeek.values()].sort((a, b) => String(a.week).localeCompare(String(b.week)));
  }, [st.data, metric]);

  // colour follows the entity (its position in the stable selection order), never its rank
  const series = sel.map((id, i) => ({ key: id, name: id, color: SERIES[i] }));
  const toggle = (id: string) => {
    const cur = [...sel];
    const i = cur.indexOf(id);
    if (i >= 0) cur.splice(i, 1);
    else if (cur.length < MAX_SERIES) cur.push(id);
    setPicked(cur);
  };

  return (
    <>
      <PageHeader title="Trends" subtitle="Weekly operating metrics. Compare up to four entities." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-ink-2">
          Metric
          <select value={metric} onChange={(e) => setMetric(e.target.value as keyof Week)} className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink">
            {METRICS.map((x) => (
              <option key={x.key} value={x.key}>{x.label}</option>
            ))}
          </select>
        </label>
        <Segmented label="View" value={view} onChange={setView} options={[{ value: "chart", label: "Chart" }, { value: "table", label: "Table" }]} />
      </div>
      <Async state={ents}>
        {(d) => (
          <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label="Entities">
            {d.entities.map((e) => {
              const on = sel.includes(e.entity_id);
              const i = sel.indexOf(e.entity_id);
              return (
                <button
                  key={e.entity_id}
                  onClick={() => toggle(e.entity_id)}
                  aria-pressed={on}
                  disabled={!on && sel.length >= MAX_SERIES}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs disabled:opacity-40 ${on ? "border-[var(--accent)] bg-accent-wash text-ink" : "border-line bg-surface text-ink-2 hover:text-ink"}`}
                  title={e.name}
                >
                  {on && <span className="h-2 w-2 rounded-full" style={{ background: SERIES[i] }} />}
                  {e.entity_id}
                </button>
              );
            })}
          </div>
        )}
      </Async>
      <Card title={`${m.label} per week`} subtitle={`${m.unit}. Weeks start on Monday.`}>
        {sel.length === 0 ? (
          <p className="py-6 text-sm text-ink-2">Select at least one entity.</p>
        ) : (
          <Async state={st}>
            {() =>
              view === "chart" ? (
                <TrendLines data={data} series={series} yLabel={m.unit} />
              ) : (
                <Table
                  rows={data}
                  columns={[{ key: "week", label: "Week" }, ...sel.map((id) => ({ key: id, label: id, align: "right" as const, render: (r: Record<string, unknown>) => fmtNum(r[id] as number, 2) }))]}
                />
              )
            }
          </Async>
        )}
      </Card>
    </>
  );
}
