import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type EvidenceRecord } from "../api";
import RecordDrawer from "../components/RecordDrawer";
import { Async, Button, Card, CATEGORY_LABEL, fmtDate, fmtInt, fmtNum, PageHeader, SeverityBadge, Table, typeLabel, useAsync } from "../components/ui";

const PAGE = 50;
const isTable = (v: unknown) => Array.isArray(v) && v.length > 0 && typeof v[0] === "object";

function Value({ v }: { v: unknown }): ReactNode {
  if (v === null || v === undefined) return "–";
  if (typeof v === "number") return Math.abs(v) < 1 && v !== 0 && !Number.isInteger(v) ? fmtNum(v, 4) : fmtNum(v, 2);
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v)) {
    if (v.length && typeof v[0] === "object") {
      const rows = v as Record<string, unknown>[];
      const cols = Object.keys(rows[0]);
      return (
        <Table rows={rows.slice(0, 25)} columns={cols.map((c) => ({ key: c, label: c.replace(/_/g, " "), render: (r) => <Value v={r[c]} /> }))} />
      );
    }
    return v.length ? v.slice(0, 30).join(", ") + (v.length > 30 ? ` … (+${v.length - 30})` : "") : "none";
  }
  if (typeof v === "object")
    return (
      <span className="flex flex-wrap gap-x-3 gap-y-1">
        {Object.entries(v as Record<string, unknown>).map(([k, x]) => (
          <span key={k}>
            <span className="text-ink-2">{k}:</span> <Value v={x} />
          </span>
        ))}
      </span>
    );
  return String(v);
}

const EVIDENCE_COLS: Record<string, { key: string; label: string; render?: (r: Record<string, unknown>) => ReactNode; align?: "right" }[]> = {
  case: [
    { key: "case_id", label: "Case" },
    { key: "severity", label: "Severity" },
    { key: "rule_name", label: "Rule" },
    { key: "asset_id", label: "Asset", render: (r) => `${r.asset_id ?? "–"}${r.criticality === "critical" ? " (critical)" : ""}` },
    { key: "opened_at", label: "Opened", render: (r) => fmtDate(r.opened_at as string) },
    { key: "minutes_to_close", label: "Min to close", align: "right", render: (r) => fmtNum(r.minutes_to_close as number, 1) },
    { key: "disposition", label: "Disposition" },
    { key: "escalated", label: "Escalated", render: (r) => (r.escalated ? (r.escalation_recorded ? "yes" : "yes, no record") : "no") },
    { key: "assignee", label: "Analyst" },
    { key: "notes", label: "Notes", render: (r) => <span className="line-clamp-2 max-w-sm text-ink-2">{r.notes as string}</span> },
  ],
  alert: [
    { key: "alert_id", label: "Alert" },
    { key: "ts", label: "Time", render: (r) => fmtDate(r.ts as string) },
    { key: "severity", label: "Severity" },
    { key: "category", label: "Category" },
    { key: "rule_name", label: "Rule" },
    { key: "asset_id", label: "Asset" },
    { key: "case_id", label: "Case", render: (r) => (r.case_id as string) ?? "none" },
  ],
  asset: [
    { key: "asset_id", label: "Asset" },
    { key: "hostname", label: "Hostname" },
    { key: "asset_type", label: "Type" },
    { key: "criticality", label: "Criticality" },
    { key: "telemetry_days", label: "Telemetry days", align: "right" },
    { key: "zero_day_share", label: "Zero-event days", align: "right", render: (r) => `${Math.round((r.zero_day_share as number) * 100)}%` },
    { key: "median_events", label: "Median events/day", align: "right", render: (r) => fmtNum(r.median_events as number, 0) },
    { key: "alerts", label: "Alerts", align: "right" },
  ],
};

export default function FindingDetail() {
  const { id = "" } = useParams();
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<{ kind: string; id: string } | null>(null);
  const st = useAsync(() => api.finding(id, 0, 1), [id]);
  const ev = useAsync(() => api.evidence(id, offset, PAGE), [id, offset]);
  return (
    <Async state={st}>
      {({ finding: f }) => (
        <>
          <PageHeader
            title={f.title}
            subtitle={
              <span className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={f.severity} />
                <Link to={`/entities/${f.entity_id}`} className="text-accent hover:underline">{f.entity_id}</Link>
                <span>· {typeLabel(f.type)} · {CATEGORY_LABEL[f.category]} · {f.points.toFixed(1)} risk points · detector {f.detector}</span>
              </span>
            }
            actions={<Button href={api.reportUrl("findings.csv")}>Findings CSV</Button>}
          />
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Card title="Why this was flagged">
              <p className="text-sm leading-relaxed text-ink">{f.rationale}</p>
            </Card>
            <Card title="Measured values" subtitle="The numbers the detector used">
              <dl className="grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-4 gap-y-2 text-sm">
                {Object.entries(f.metric_values).filter(([, v]) => !isTable(v)).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-ink-2">{k.replace(/_/g, " ")}</dt>
                    <dd className="tnum min-w-0 text-ink"><Value v={v} /></dd>
                  </div>
                ))}
              </dl>
            </Card>
          </div>
          {Object.entries(f.metric_values).filter(([, v]) => isTable(v)).map(([k, v]) => (
            <Card key={k} className="mt-5" title={k.replace(/_/g, " ")} subtitle="Detail computed by the detector">
              <Value v={v} />
            </Card>
          ))}
          <Card
            className="mt-5"
            title="Evidence"
            subtitle={f.n_evidence ? `${fmtInt(f.n_evidence)} records. Click a row to see the full record.` : "This finding is about something missing, so it has no individual records. The measured values above are the evidence."}
          >
            {f.n_evidence > 0 && (
              <Async state={ev}>
                {(e) => {
                  const kinds = [...new Set(e.records.map((r) => r.record_type))];
                  return (
                    <>
                      {kinds.map((k) => (
                        <div key={k} className="mb-4">
                          {kinds.length > 1 && <h3 className="mb-1 text-xs font-semibold uppercase text-muted">{k}s</h3>}
                          <Table
                            rows={e.records.filter((r: EvidenceRecord) => r.record_type === k)}
                            columns={EVIDENCE_COLS[k] ?? []}
                            onRowClick={(r) => setOpen({ kind: k, id: r.record_id as string })}
                          />
                        </div>
                      ))}
                      <div className="flex items-center justify-between text-sm text-ink-2">
                        <span>
                          {e.offset + 1}–{Math.min(e.offset + PAGE, e.total)} of {fmtInt(e.total)}
                        </span>
                        <div className="flex gap-2">
                          <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
                          <Button disabled={offset + PAGE >= e.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
                        </div>
                      </div>
                    </>
                  );
                }}
              </Async>
            )}
          </Card>
          {open && <RecordDrawer kind={open.kind} id={open.id} onClose={() => setOpen(null)} />}
        </>
      )}
    </Async>
  );
}
