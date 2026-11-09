import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { RiskBars } from "../components/charts";
import SummaryPies from "../components/SummaryPies";
import {
  Async, Button, Card, CATEGORY_LABEL, fmtDate, fmtInt, PageHeader, SeverityBadge, StatTile, typeLabel, useAsync,
} from "../components/ui";

export default function Results() {
  const [sp, setSp] = useSearchParams();
  const ids = (sp.get("entity_id") ?? "").split(",").filter(Boolean);
  const key = ids.join(",");
  const sum = useAsync(() => api.summary(ids), [key]);
  const ents = useAsync(() => api.entities(), []);
  const finds = useAsync(() => api.findings({ entity_id: key || undefined, limit: 200 }), [key]);
  const scope = ids.length === 0 ? "all organisations" : ids.length === 1 ? ids[0] : `${ids.length} organisations`;
  const shown = (ents.data?.entities ?? []).filter((e) => ids.length === 0 || ids.includes(e.entity_id));

  return (
    <>
      <PageHeader
        title="Analysis results"
        subtitle={sum.data ? `For ${scope} · analysis run ${sum.data.run.run_id} · ${fmtDate(sum.data.run.started_at)}` : `For ${scope}`}
        actions={
          <>
            <label className="flex items-center gap-2 text-sm text-ink-2">
              Show
              <select
                value={ids.length === 1 ? ids[0] : ids.length ? "__sel" : ""}
                onChange={(e) => setSp(e.target.value && e.target.value !== "__sel" ? { entity_id: e.target.value } : {})}
                className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
              >
                <option value="">All organisations</option>
                {ids.length > 1 && <option value="__sel">Uploaded ({ids.length})</option>}
                {ents.data?.entities.map((e) => (
                  <option key={e.entity_id} value={e.entity_id}>{e.entity_id} · {e.name}</option>
                ))}
              </select>
            </label>
            <Button href={ids.length === 1 ? api.reportUrl(`entity/${ids[0]}.pdf`) : api.reportUrl("summary.pdf")}>
              Download PDF report
            </Button>
          </>
        }
      />
      <Async state={sum}>
        {(s) => (
          <>
            <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile label="Organisations" value={fmtInt(s.totals.entities)} />
              <StatTile label="Alerts analysed" value={fmtInt(s.totals.alerts)} hint={`${fmtInt(s.totals.cases)} cases`} />
              <StatTile label="Security concerns found" value={fmtInt(s.totals.findings)}
                hint={s.by_severity.length ? s.by_severity.map((x) => `${x.n} ${x.severity}`).join(" · ") : "none"} />
              <StatTile label="Records to check by hand" value={fmtInt(s.totals.review_items)}
                hint={<Link className="text-accent hover:underline" to={ids.length === 1 ? `/review?entity_id=${ids[0]}` : "/review"}>Open review queue</Link>} />
            </div>
            <SummaryPies s={s} />
          </>
        )}
      </Async>
      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card title="Security warnings" subtitle="Each warning says why it was raised. Open one to see the records behind it.">
          <Async state={finds}>
            {(d) =>
              d.findings.length === 0 ? (
                <div className="rounded-lg bg-surface-2 p-4 text-sm text-ink-2">
                  No security concerns were found: the data is in line with comparable organisations on every check.
                  {sum.data && sum.data.totals.entities < 3 && (
                    <> Note that most checks compare an organisation with its peers, so they need data from at least 3 organisations.</>
                  )}
                </div>
              ) : (
                <ul className="space-y-3">
                  {d.findings.map((f) => (
                    <li key={f.finding_id} className="rounded-lg border border-line p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <SeverityBadge severity={f.severity} />
                        <span className="text-xs text-muted">
                          {f.entity_id} · {typeLabel(f.type)} · {CATEGORY_LABEL[f.category] ?? f.category}
                        </span>
                      </div>
                      <Link to={`/findings/${f.finding_id}`} className="mt-1 block font-medium text-ink hover:text-accent hover:underline">
                        {f.title}
                      </Link>
                      <p className="mt-1 text-sm text-ink-2">{f.rationale}</p>
                    </li>
                  ))}
                </ul>
              )
            }
          </Async>
        </Card>
        <Card title="Risk ranking" subtitle="Score = sum of finding points. Hover a bar for its breakdown.">
          <Async state={ents}>{() => <RiskBars entities={shown} />}</Async>
        </Card>
      </div>
    </>
  );
}
