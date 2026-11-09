import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { Button, Card, ErrorBox, fmtDate, PageHeader, Table, useAsync } from "../components/ui";

type Result = Awaited<ReturnType<typeof api.upload>>;

export default function Upload() {
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [analyse, setAnalyse] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [drag, setDrag] = useState(false);
  const health = useAsync(() => api.health(), []);
  const hist = useAsync(() => api.ingestions(), [result]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.upload(files, analyse));
      setFiles([]);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  };
  const rerun = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.runAnalysis();
      setResult({ run_id: "", entity_ids: [], row_counts: {}, warnings: [], analysis_run_id: r.run_id });
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  };
  const ro = health.data?.read_only;

  return (
    <>
      <PageHeader title="Data upload" subtitle="Add an entity's SOC export. It is validated, stored locally, and the analysis re-runs." />
      {ro && (
        <div className="mb-4 rounded-lg border border-line bg-surface-2 p-3 text-sm text-ink-2">
          This is a read-only demo deployment with sample data. Uploads and analysis runs are disabled.
        </div>
      )}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card title="Upload an export">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              setFiles([...e.dataTransfer.files]);
            }}
            className={`rounded-xl border-2 border-dashed p-8 text-center ${drag ? "border-[var(--accent)] bg-accent-wash" : "border-line"}`}
          >
            <p className="text-sm text-ink">Drop files here, or</p>
            <button className="mt-2 text-sm font-medium text-accent hover:underline" onClick={() => input.current?.click()} disabled={ro}>
              choose files
            </button>
            <input ref={input} type="file" multiple className="hidden"
              accept=".zip,.csv,.json,.jsonl,.sqlite,.sqlite3,.db,.duckdb,.parquet"
              onChange={(e) => setFiles([...(e.target.files ?? [])])} />
            {files.length > 0 && (
              <ul className="mt-4 text-left text-sm text-ink-2">
                {files.map((f) => (
                  <li key={f.name}>{f.name} · {(f.size / 1024).toFixed(0)} KB</li>
                ))}
              </ul>
            )}
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-ink-2">
              <input type="checkbox" checked={analyse} onChange={(e) => setAnalyse(e.target.checked)} />
              Re-run analysis after upload
            </label>
            <div className="flex gap-2">
              <Button onClick={rerun} disabled={busy || ro}>Re-run analysis only</Button>
              <Button variant="primary" onClick={submit} disabled={busy || ro || files.length === 0}>
                {busy ? "Working…" : "Upload and validate"}
              </Button>
            </div>
          </div>
          {error && <div className="mt-4"><ErrorBox error={error instanceof ApiError ? error : new Error(String(error))} /></div>}
          {result && (
            <div className="mt-4 rounded-lg border border-line bg-surface-2 p-4 text-sm">
              {result.run_id && (
                <>
                  <p className="font-medium text-ink">Stored {Object.entries(result.row_counts).map(([k, v]) => `${v} ${k}`).join(", ")}</p>
                  <p className="mt-1 text-ink-2">Entities: {result.entity_ids.join(", ")} · ingest {result.run_id}</p>
                  {result.warnings.length > 0 && (
                    <ul className="mt-2 list-disc pl-5 text-ink-2">
                      {result.warnings.map((w) => <li key={w}>{w}</li>)}
                    </ul>
                  )}
                </>
              )}
              {result.analysis_run_id && (
                <p className="mt-2 text-ink">
                  Analysis run {result.analysis_run_id} done. <Link className="text-accent hover:underline" to="/">See the overview</Link>
                </p>
              )}
            </div>
          )}
        </Card>
        <Card title="What to upload" subtitle="Full schema in docs/data_schema.md">
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">
            <li>A <b className="text-ink">.zip</b> of table files, a <b className="text-ink">SQLite/DuckDB</b> export, or several CSV/JSON files at once.</li>
            <li>Tables: <code>entities</code> and <code>alerts</code> are required; <code>assets</code>, <code>cases</code>, <code>escalations</code> and <code>telemetry</code> enable more checks.</li>
            <li>Errors name the table, column and row. Nothing is stored unless the whole upload is valid.</li>
            <li>Gaps such as alerts with no case are accepted on purpose: they are what the tool looks for.</li>
          </ul>
        </Card>
      </div>
      <Card className="mt-5" title="Upload history" subtitle="Every ingest, with the SHA-256 of its input">
        {hist.data ? (
          <Table
            rows={hist.data}
            columns={[
              { key: "started_at", label: "When", render: (r) => fmtDate(r.started_at as string) },
              { key: "source_name", label: "Source" },
              { key: "entity_ids", label: "Entities", render: (r) => (r.entity_ids as string[]).join(", ") },
              { key: "row_counts", label: "Rows", render: (r) => Object.entries(r.row_counts as Record<string, number>).map(([k, v]) => `${k} ${v}`).join(" · ") },
              { key: "input_sha256", label: "Input SHA-256", render: (r) => <code className="text-xs">{(r.input_sha256 as string).slice(0, 16)}…</code> },
            ]}
          />
        ) : hist.error ? <ErrorBox error={hist.error} /> : null}
      </Card>
    </>
  );
}
