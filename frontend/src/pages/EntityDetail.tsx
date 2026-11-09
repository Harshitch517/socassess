import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { HBars, PeerStrip } from "../components/charts";
import {
  Async, Button, Card, CATEGORY_LABEL, fmtDate, fmtInt, fmtNum, PageHeader, SeverityBadge, StatTile, Table, typeLabel, useAsync,
} from "../components/ui";

export default function EntityDetail() {
  const { id = "" } = useParams();
  const st = useAsync(() => api.entity(id), [id]);
  return (
    <Async state={st}>
      {(d) => {
        const e = d.entity;
        const s = d.score;
        return (
          <>
            <PageHeader
              title={`${e.entity_id} · ${e.name}`}
              subtitle={`${e.sector} · ${e.size} · source ${e.source}${s.has_case_data ? "" : " · no case-management data"}`}
              actions={
                <>
                  <Button href={api.reportUrl(`entity/${e.entity_id}.pdf`)}>Entity PDF</Button>
                  <Link to={`/review?entity_id=${e.entity_id}`} className="inline-flex items-center rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-2">
                    Review queue
                  </Link>
                </>
              }
            />
            <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile label="Risk score" value={fmtNum(s.risk_score, 1)} hint={<SeverityBadge severity={s.band} label={`${s.band} · rank ${s.rank}`} />} />
              <StatTile label="Findings" value={s.n_findings} hint={s.anomaly_score != null ? `anomaly score ${s.anomaly_score.toFixed(2)} (~0.5 typical)` : "anomaly score n/a"} />
              <StatTile label="Alerts / cases" value={`${fmtInt(d.counts.alerts as number)} / ${fmtInt(d.counts.cases as number)}`} hint={`${fmtInt(d.counts.escalations as number)} escalations`} />
              <StatTile label="Assets" value={fmtInt(d.counts.assets as number)} hint={`${d.counts.critical_assets} critical · data ${fmtDate(d.counts.first_alert as string).slice(0, 10)} → ${fmtDate(d.counts.last_alert as string).slice(0, 10)}`} />
            </div>
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <Card title="Findings" subtitle="Why this entity was flagged. Open a finding for its evidence.">
                {d.findings.length === 0 ? (
                  <p className="py-4 text-sm text-ink-2">No findings: this entity is in line with its peers on every detector.</p>
                ) : (
                  <ul className="space-y-3">
                    {d.findings.map((f) => (
                      <li key={f.finding_id} className="rounded-lg border border-line p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <SeverityBadge severity={f.severity} />
                          <span className="text-xs text-muted">
                            {CATEGORY_LABEL[f.category] ?? f.category} · {typeLabel(f.type)} · {f.points.toFixed(1)} pts
                          </span>
                        </div>
                        <Link to={`/findings/${f.finding_id}`} className="mt-1 block font-medium text-ink hover:text-accent hover:underline">
                          {f.title}
                        </Link>
                        <p className="mt-1 text-sm text-ink-2">{f.rationale}</p>
                        {f.n_evidence > 0 && (
                          <Link to={`/findings/${f.finding_id}`} className="mt-1 inline-block text-xs font-medium text-accent hover:underline">
                            {fmtInt(f.n_evidence)} evidence records →
                          </Link>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
              <div className="space-y-5">
                <Card title="Score breakdown" subtitle="weight × severity multiplier per finding">
                  {s.breakdown.length ? (
                    <HBars
                      rows={s.breakdown.map((b) => ({
                        key: b.finding_id,
                        label: typeLabel(b.type),
                        value: b.points,
                        tip: `${b.title}: weight ${b.weight} × ${b.multiplier} (${b.severity}) = ${b.points.toFixed(2)}`,
                      }))}
                    />
                  ) : (
                    <p className="text-sm text-ink-2">Score 0: no findings.</p>
                  )}
                </Card>
                <Card title="Alert categories" subtitle="Alert count per category in the period">
                  <HBars rows={d.categories.map((c) => ({ key: c.category, label: c.category.replace(/_/g, " "), value: c.alerts }))} format={(v) => fmtInt(v)} />
                </Card>
              </div>
            </div>
            <Card className="mt-5" title="Peer comparison" subtitle="Each row compares this entity with peers from the same source. Grey dots are peers; the tick is the peer median. Sorted by how unusual the entity is (|z|). The marker turns red when |z| ≥ 3 in the worse direction.">
              <Table
                rows={[...d.benchmarks].sort((x, y) => Math.abs(y.z) - Math.abs(x.z)) as unknown as Record<string, unknown>[]}
                columns={[
                  { key: "description", label: "Metric" },
                  { key: "value", label: "This entity", align: "right", render: (b) => fmtNum(b.value as number, 3) },
                  { key: "peer_median_all", label: "Peer median", align: "right", render: (b) => fmtNum(b.peer_median_all as number, 3) },
                  { key: "peer_median_size", label: "Same-size median", align: "right", render: (b) => fmtNum(b.peer_median_size as number, 3) },
                  { key: "z", label: "z", align: "right", render: (b) => fmtNum(b.z as number, 1) },
                  {
                    key: "strip",
                    label: "Distribution",
                    render: (b) => <PeerStrip b={b as never} peers={d.peer_values?.[b.metric as string] ?? []} />,
                  },
                ]}
              />
            </Card>
          </>
        );
      }}
    </Async>
  );
}
