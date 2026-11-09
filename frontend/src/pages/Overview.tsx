import { Link } from "react-router-dom";
import { api } from "../api";
import { HBars, Heatmap, RiskBars } from "../components/charts";
import SummaryPies from "../components/SummaryPies";
import { Async, Button, Card, CATEGORY_LABEL, fmtDate, fmtInt, PageHeader, SeverityBadge, StatTile, typeLabel, useAsync } from "../components/ui";

export default function Overview() {
  const ents = useAsync(() => api.entities(), []);
  const heat = useAsync(() => api.heatmap(), []);
  const sum = useAsync(() => api.summary(), []);
  return (
    <>
      <PageHeader
        title="Overview"
        subtitle={sum.data ? `Analysis run ${sum.data.run.run_id} · ${fmtDate(sum.data.run.started_at)}` : "Supervisory risk across all entities"}
        actions={<Button href={api.reportUrl("summary.pdf")}>Download summary PDF</Button>}
      />
      <Async state={sum}>
        {(s) => {
          const bands = Object.fromEntries(s.bands.map((b) => [b.band, b.n]));
          return (
            <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile label="Entities assessed" value={fmtInt(s.totals.entities)} hint={`${fmtInt(s.totals.alerts)} alerts · ${fmtInt(s.totals.cases)} cases`} />
              <StatTile label="Findings" value={fmtInt(s.totals.findings)} hint={s.by_severity.map((x) => `${x.n} ${x.severity}`).join(" · ")} />
              <StatTile
                label="Entities at high or critical risk"
                value={fmtInt((bands.high ?? 0) + (bands.critical ?? 0))}
                hint={`${bands.medium ?? 0} medium · ${bands.low ?? 0} low`}
              />
              <StatTile label="Records queued for review" value={fmtInt(s.totals.review_items)} hint={<Link className="text-accent hover:underline" to="/review">Open review queue</Link>} />
            </div>
          );
        }}
      </Async>
      <Async state={sum}>{(s) => <div className="mb-5"><SummaryPies s={s} /></div>}</Async>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <Card title="Risk ranking" subtitle="Score = sum of finding points (capped at 100). Hover a bar for its breakdown.">
          <Async state={ents}>{(d) => <RiskBars entities={d.entities} />}</Async>
        </Card>
        <Card title="Where the risk comes from" subtitle="Risk points by entity and finding type. Click a cell to see the findings.">
          <Async state={heat}>{(h) => <Heatmap entities={h.entities} types={h.types} cells={h.cells} />}</Async>
        </Card>
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card title="Findings by type" subtitle="Total risk points contributed across all entities">
          <Async state={sum}>
            {(s) => (
              <HBars
                rows={s.by_type.map((t) => ({
                  key: t.type,
                  label: (
                    <Link to={`/findings?type=${t.type}`} className="hover:text-accent hover:underline">
                      {typeLabel(t.type)}
                    </Link>
                  ),
                  value: t.points,
                  tip: `${typeLabel(t.type)} (${CATEGORY_LABEL[t.category] ?? t.category}): ${t.n} finding(s), ${t.points.toFixed(1)} points`,
                }))}
                format={(v) => v.toFixed(1)}
              />
            )}
          </Async>
        </Card>
        <Card title="Top findings" subtitle="Highest-impact findings in this run">
          <TopFindings />
        </Card>
      </div>
    </>
  );
}

function TopFindings() {
  const st = useAsync(() => api.findings({ limit: 8 }), []);
  return (
    <Async state={st}>
      {(d) => (
        <ul className="divide-y divide-[var(--border)]">
          {d.findings.map((f) => (
            <li key={f.finding_id} className="flex items-start gap-3 py-2">
              <SeverityBadge severity={f.severity} />
              <div className="min-w-0">
                <Link to={`/findings/${f.finding_id}`} className="text-sm font-medium text-ink hover:text-accent hover:underline">
                  {f.title}
                </Link>
                <div className="text-xs text-ink-2">
                  {f.entity_id} · {typeLabel(f.type)} · {f.points.toFixed(1)} pts
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Async>
  );
}
