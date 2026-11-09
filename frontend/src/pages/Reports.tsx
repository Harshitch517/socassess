import { useState } from "react";
import { api } from "../api";
import { Async, Button, Card, fmtDate, PageHeader, Table, useAsync } from "../components/ui";

export default function Reports() {
  const ents = useAsync(() => api.entities(), []);
  const runs = useAsync(() => api.runs(), []);
  const uploads = useAsync(() => api.ingestions(), []);
  const [entity, setEntity] = useState("");
  const [runOpen, setRunOpen] = useState<string | null>(null);
  const runDetail = useAsync(() => (runOpen ? api.run(runOpen) : Promise.resolve(null)), [runOpen]);
  const sel = entity || ents.data?.entities[0]?.entity_id || "";
  return (
    <>
      <PageHeader title="Reports & audit" subtitle="Exports for the latest analysis run, and the log of every run" />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card title="Supervisory reports">
          <div className="flex flex-wrap gap-2">
            <Button href={api.reportUrl("summary.pdf")}>Summary PDF (all entities)</Button>
            <Button href={api.reportUrl("entities.csv")}>Risk scores CSV</Button>
            <Button href={api.reportUrl("findings.csv")}>Findings CSV</Button>
            <Button href={api.reportUrl("review_queue.csv")}>Review queue CSV</Button>
            <Button href={api.reportUrl("benchmarks.csv")}>Peer benchmarks CSV</Button>
          </div>
        </Card>
        <Card title="Entity report">
          <div className="flex flex-wrap items-center gap-2">
            <select value={sel} onChange={(e) => setEntity(e.target.value)} className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink" aria-label="Entity">
              {ents.data?.entities.map((e) => (
                <option key={e.entity_id} value={e.entity_id}>{e.entity_id} {e.name}</option>
              ))}
            </select>
            <Button href={sel ? api.reportUrl(`entity/${sel}.pdf`) : undefined}>Download entity PDF</Button>
          </div>
        </Card>
      </div>
      <Card className="mt-5" title="Analysis audit log" subtitle="Every run records when it ran, a fingerprint of the input data, the exact parameters and the code version. Click a run to see its parameters.">
        <Async state={runs}>
          {(rs) => (
            <Table
              rows={rs as unknown as Record<string, unknown>[]}
              onRowClick={(r) => setRunOpen(runOpen === r.run_id ? null : (r.run_id as string))}
              columns={[
                { key: "started_at", label: "Started", render: (r) => fmtDate(r.started_at as string) },
                { key: "run_id", label: "Run", render: (r) => <code className="text-xs">{r.run_id as string}</code> },
                { key: "trigger", label: "Trigger" },
                { key: "input_hash", label: "Input fingerprint", render: (r) => <code className="text-xs">{(r.input_hash as string).slice(0, 16)}…</code> },
                { key: "params_hash", label: "Params", render: (r) => <code className="text-xs">{r.params_hash as string}</code> },
                { key: "code_version", label: "Code", render: (r) => <code className="text-xs">{r.code_version as string}</code> },
                { key: "n_findings", label: "Findings", align: "right" },
                { key: "duration_s", label: "Seconds", align: "right" },
                { key: "detector_errors", label: "Errors", render: (r) => (Object.keys((r.detector_errors as object) ?? {}).length ? "yes" : "none") },
              ]}
            />
          )}
        </Async>
        {runOpen && (
          <Async state={runDetail}>
            {(r) =>
              r ? (
                <pre className="mt-4 max-h-96 overflow-auto rounded-lg bg-surface-2 p-3 text-xs text-ink">{JSON.stringify(r.params, null, 2)}</pre>
              ) : null
            }
          </Async>
        )}
      </Card>
      <Card className="mt-5" title="Upload history" subtitle="Every input that was added, with a SHA-256 fingerprint of the file">
        <Async state={uploads}>
          {(rows) => (
            <Table
              rows={rows}
              columns={[
                { key: "started_at", label: "When", render: (r) => fmtDate(r.started_at as string) },
                { key: "source_name", label: "File" },
                { key: "entity_ids", label: "Organisations", render: (r) => (r.entity_ids as string[]).join(", ") },
                { key: "row_counts", label: "Rows", render: (r) => Object.entries(r.row_counts as Record<string, number>).map(([k, v]) => `${k} ${v}`).join(" · ") },
                { key: "input_sha256", label: "SHA-256", render: (r) => <code className="text-xs">{(r.input_sha256 as string).slice(0, 16)}…</code> },
              ]}
            />
          )}
        </Async>
      </Card>
    </>
  );
}
