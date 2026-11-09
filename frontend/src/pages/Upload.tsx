import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import SummaryPies from "../components/SummaryPies";
import { Async, Button, Card, ErrorBox, fmtDate, PageHeader, Segmented, Table, useAsync } from "../components/ui";

type Result = Awaited<ReturnType<typeof api.upload>>;

const TEMPLATE = `timestamp,severity,category,rule_name,host,organisation
2026-06-01T10:00:00Z,high,malware,EDR malware detection,web01,My SOC
2026-06-01T10:20:00Z,low,recon,Port scan detected,fw01,My SOC
2026-06-02T08:05:00Z,critical,lateral_movement,PsExec remote execution,dc01,My SOC
`;

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "socassess_alerts_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export default function Upload() {
  const input = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<"file" | "paste">("file");
  const [files, setFiles] = useState<File[]>([]);
  const [text, setText] = useState("");
  const [org, setOrg] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [drag, setDrag] = useState(false);
  const health = useAsync(() => api.health(), []);
  const hist = useAsync(() => api.ingestions(), [result]);
  const ro = health.data?.read_only;

  const ready = mode === "file" ? files.length > 0 : text.trim().split("\n").length >= 2;
  const submit = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const payload =
        mode === "file"
          ? files
          : [new File([text], text.trim().startsWith("[") || text.trim().startsWith("{") ? "pasted_data.json" : "pasted_data.csv")];
      setResult(await api.upload(payload, true, org.trim() || undefined));
      setFiles([]);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  };

  const mapping = result?.warnings.filter((w) => w.startsWith("auto-mapping:")).map((w) => w.slice(14)) ?? [];
  const other = result?.warnings.filter((w) => !w.startsWith("auto-mapping:")) ?? [];

  return (
    <>
      <PageHeader
        title="Analyze data"
        subtitle="Give SOCAssess your SOC data (a file or pasted rows) and get a security-concern report with charts. Nothing leaves this machine."
        actions={<Link to="/results" className="inline-flex items-center rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-2">See results for the demo dataset</Link>}
      />
      {ro && (
        <div className="mb-4 rounded-lg border border-line bg-surface-2 p-3 text-sm text-ink-2">
          This is a read-only demo with synthetic data. Adding data is turned off here; run SOCAssess locally to analyse your own.
        </div>
      )}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card
          title="1. Your data"
          actions={<Segmented label="Input method" value={mode} onChange={setMode}
            options={[{ value: "file", label: "Upload file" }, { value: "paste", label: "Paste data" }]} />}
        >
          {mode === "file" ? (
            <div
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); setFiles([...e.dataTransfer.files]); }}
              className={`rounded-xl border-2 border-dashed p-8 text-center ${drag ? "border-[var(--accent)] bg-accent-wash" : "border-line"}`}
            >
              <p className="text-sm text-ink">Drop a file here (CSV, Excel, JSON, SQLite, Parquet or .zip)</p>
              <button className="mt-2 text-sm font-medium text-accent hover:underline disabled:opacity-50" onClick={() => input.current?.click()} disabled={ro}>
                or choose files
              </button>
              <input ref={input} type="file" multiple className="hidden"
                accept=".zip,.csv,.xlsx,.xlsm,.json,.jsonl,.sqlite,.sqlite3,.db,.duckdb,.parquet"
                onChange={(e) => setFiles([...(e.target.files ?? [])])} />
              {files.length > 0 && (
                <ul className="mt-4 text-left text-sm text-ink-2">
                  {files.map((f) => <li key={f.name}>{f.name} · {(f.size / 1024).toFixed(0)} KB</li>)}
                </ul>
              )}
            </div>
          ) : (
            <div>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={10}
                spellCheck={false}
                placeholder={TEMPLATE}
                aria-label="Paste CSV or JSON data"
                className="w-full rounded-lg border border-line bg-surface-2 p-3 font-mono text-xs text-ink placeholder:text-muted"
              />
              <p className="mt-1 text-xs text-muted">CSV with a header row, or a JSON array of objects. One row per alert.</p>
            </div>
          )}
          <label className="mt-4 flex flex-col gap-1 text-sm text-ink-2">
            Organisation name <span className="text-xs text-muted">(used when your data has no organisation column)</span>
            <input value={org} onChange={(e) => setOrg(e.target.value)} placeholder="e.g. State Power Utility" maxLength={80}
              className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink" />
          </label>
          <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
            <Button variant="primary" onClick={submit} disabled={busy || ro || !ready}>
              {busy ? "Analysing…" : "2. Analyse"}
            </Button>
          </div>
          {error && <div className="mt-4"><ErrorBox error={error instanceof ApiError ? error : new Error(String(error))} /></div>}
        </Card>
        <Card title="What data works" subtitle="Your columns are recognised automatically">
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">
            <li><b className="text-ink">Any alert export</b> from a SIEM/EDR/IDS: needs a <b className="text-ink">time</b> column. Severity, category, rule/title, host and organisation are used when present (common names such as <i>Timestamp, Priority, AlertTitle, DeviceId, OrgId</i> are understood).</li>
            <li><b className="text-ink">Full SOC export</b> (alerts + cases + escalations + assets + telemetry) unlocks every check, including closure speed, escalation and blind-spot detection. Schema: <code>docs/data_schema.md</code>.</li>
            <li>Results compare each organisation with peers. With only one organisation, it is compared with the built-in reference population.</li>
          </ul>
          <button className="mt-3 text-sm font-medium text-accent hover:underline" onClick={downloadTemplate}>Download a CSV template</button>
        </Card>
      </div>

      {result && (
        <div className="mt-5 space-y-5">
          <Card title="How your data was read"
            subtitle={`Stored ${Object.entries(result.row_counts).map(([k, v]) => `${v.toLocaleString()} ${k}`).join(", ")} for ${result.entity_ids.join(", ")}`}
            actions={<Link to={`/results?entity_id=${result.entity_ids.join(",")}`} className="inline-flex items-center rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90">Open full results</Link>}>
            {mapping.length > 0 ? (
              <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">{mapping.map((m) => <li key={m}>{m}</li>)}</ul>
            ) : (
              <p className="text-sm text-ink-2">The data already followed the SOCAssess format; nothing had to be assumed.</p>
            )}
            {other.length > 0 && (
              <details className="mt-2 text-xs text-muted">
                <summary className="cursor-pointer">{other.length} note(s)</summary>
                <ul className="mt-1 list-disc pl-5">{other.map((w) => <li key={w}>{w}</li>)}</ul>
              </details>
            )}
          </Card>
          <UploadSummary ids={result.entity_ids} />
        </div>
      )}

      <Card className="mt-5" title="Upload history" subtitle="Every input, with a SHA-256 fingerprint for audit">
        {hist.data ? (
          <Table
            rows={hist.data}
            columns={[
              { key: "started_at", label: "When", render: (r) => fmtDate(r.started_at as string) },
              { key: "source_name", label: "Source" },
              { key: "entity_ids", label: "Organisations", render: (r) => (r.entity_ids as string[]).join(", ") },
              { key: "row_counts", label: "Rows", render: (r) => Object.entries(r.row_counts as Record<string, number>).map(([k, v]) => `${k} ${v}`).join(" · ") },
              { key: "input_sha256", label: "Input SHA-256", render: (r) => <code className="text-xs">{(r.input_sha256 as string).slice(0, 16)}…</code> },
            ]}
          />
        ) : hist.error ? <ErrorBox error={hist.error} /> : null}
      </Card>
    </>
  );
}

function UploadSummary({ ids }: { ids: string[] }) {
  const st = useAsync(() => api.summary(ids), [ids.join(",")]);
  return <Async state={st}>{(s) => <SummaryPies s={s} />}</Async>;
}
