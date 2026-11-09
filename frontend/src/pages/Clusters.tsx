import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type Cluster } from "../api";
import { useTip } from "../components/charts";
import { Async, Card, fmtInt, fmtNum, fmtPct, PageHeader, Segmented, Table, useAsync } from "../components/ui";

function LogBar({ value, max }: { value: number; max: number }) {
  const tip = useTip();
  const w = (Math.log10(Math.max(1, value)) / Math.log10(Math.max(10, max))) * 100;
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-4 w-32 shrink-0">
        <div
          className="absolute top-1/2 left-0 h-2.5 -translate-y-1/2 rounded-r-[4px] bg-[var(--series-1)]"
          style={{ width: `${Math.max(2, w)}%` }}
          onMouseEnter={(e) => tip.show(e, `${fmtInt(value)} alerts`)}
          onMouseLeave={tip.hide}
        />
      </div>
      <span className="tnum text-ink">{fmtInt(value)}</span>
      {tip.node}
    </div>
  );
}

export default function Clusters() {
  const st = useAsync(() => api.clusters(), []);
  const [sel, setSel] = useState<number | null>(null);
  const [scope, setScope] = useState<"all" | "cross">("all");
  const detail = useAsync(() => (sel === null ? Promise.resolve(null) : api.cluster(sel)), [sel]);
  return (
    <>
      <PageHeader
        title="Alert clusters"
        subtitle="Recurring alert patterns within and across entities. A pattern is one rule at one entity, described by volume, spread, timing and rule text, then grouped with HDBSCAN."
      />
      <Async state={st}>
        {(d) => {
          const rows = d.clusters.filter((c) => scope === "all" || c.n_entities > 1);
          const max = Math.max(...d.clusters.map((c) => c.alerts), 10);
          return (
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <Card
                title={`${d.clusters.length} clusters`}
                subtitle={`${fmtInt(d.unclustered.patterns)} one-off patterns (${fmtInt(d.unclustered.alerts)} alerts) did not fit any cluster. Bar length is on a log scale.`}
                actions={
                  <Segmented label="Cluster scope" value={scope} onChange={setScope}
                    options={[{ value: "all", label: "All" }, { value: "cross", label: "Cross-entity" }]} />
                }
              >
                <Table
                  rows={rows as unknown as Record<string, unknown>[]}
                  onRowClick={(c) => setSel(c.cluster_id as number)}
                  columns={[
                    { key: "cluster_id", label: "#", align: "right" },
                    { key: "label", label: "Pattern", render: (c) => <span className="font-medium text-ink">{c.label as string}</span> },
                    { key: "alerts", label: "Alerts (log)", render: (c) => <LogBar value={c.alerts as number} max={max} /> },
                    { key: "patterns", label: "Patterns", align: "right" },
                    { key: "n_entities", label: "Entities", align: "right" },
                  ]}
                />
              </Card>
              <Card title={sel === null ? "Cluster detail" : `Cluster ${sel}`} subtitle={sel === null ? "Select a cluster to see its patterns" : undefined}>
                {sel === null ? (
                  <p className="text-sm text-ink-2">Click a row on the left.</p>
                ) : (
                  <Async state={detail}>{(c) => (c ? <ClusterDetail c={c} /> : null)}</Async>
                )}
              </Card>
            </div>
          );
        }}
      </Async>
    </>
  );
}

function ClusterDetail({ c }: { c: Cluster & { patterns: import("../api").Pattern[] } }) {
  return (
    <div className="space-y-4">
      <p className="text-sm font-medium text-ink">{c.label}</p>
      <div className="text-sm text-ink-2">
        Entities:{" "}
        {c.entities?.map((e, i) => (
          <span key={e}>
            {i > 0 && ", "}
            <Link className="text-accent hover:underline" to={`/entities/${e}`}>{e}</Link>
          </span>
        ))}
      </div>
      {c.top_rules && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase text-muted">Top rules</h3>
          <ul className="space-y-0.5 text-sm">
            {Object.entries(c.top_rules).map(([r, n]) => (
              <li key={r} className="flex justify-between gap-3">
                <span className="truncate text-ink">{r}</span>
                <span className="tnum text-ink-2">{fmtInt(n)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase text-muted">Member patterns</h3>
        <Table
          rows={c.patterns as unknown as Record<string, unknown>[]}
          columns={[
            { key: "entity_id", label: "Entity" },
            { key: "rule_name", label: "Rule", render: (p) => <span className="line-clamp-1 max-w-[14rem]">{p.rule_name as string}</span> },
            { key: "alerts", label: "Alerts", align: "right", render: (p) => fmtInt(p.alerts as number) },
            { key: "asset_spread", label: "Assets hit", align: "right", render: (p) => fmtPct(p.asset_spread as number, 0) },
            { key: "burstiness", label: "Burst", align: "right", render: (p) => fmtNum(p.burstiness as number, 1) },
            { key: "after_hours_share", label: "After hrs", align: "right", render: (p) => fmtPct(p.after_hours_share as number, 0) },
          ]}
        />
      </div>
    </div>
  );
}
