import { ArrowLeft, Clock, HardDrive, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type Guess } from "../api";
import Report, { ClassifyNote, type ReportData } from "../components/Report";
import { PageHeader, Segmented, useAsync } from "../components/ui";
import {
  deleteReport, fmtBytes, getReport, HISTORY_LIMIT, listReports, type SavedReport,
} from "../lib/localStore";
import { ReportActions } from "./Analyze";

function SavedList({ onOpen }: { onOpen: (id: string) => void }) {
  const [items, setItems] = useState<SavedReport[] | null>(null);
  const load = () => listReports().then(setItems);
  useEffect(() => { load(); }, []);
  if (items === null) return null;
  const used = items.reduce((a, r) => a + r.bytes, 0);
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-line bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="flex items-center gap-2 text-ink"><HardDrive className="h-4 w-4 text-accent" /> Stored on this computer</span>
          <span className="tnum text-ink-2">{fmtBytes(used)} of {fmtBytes(HISTORY_LIMIT)}</span>
        </div>
        <div className="mt-2 h-2 rounded-full bg-[color-mix(in_srgb,var(--accent)_18%,transparent)]" role="meter"
          aria-valuemin={0} aria-valuemax={HISTORY_LIMIT} aria-valuenow={used} aria-label="Storage used">
          <div className="h-2 rounded-full bg-accent" style={{ width: `${Math.max(used ? 1 : 0, (used / HISTORY_LIMIT) * 100)}%` }} />
        </div>
        <p className="mt-2 text-xs text-muted">Reports are kept only in this browser. When the 1 GB limit is reached, the oldest are removed automatically.</p>
      </div>
      {items.length === 0 ? (
        <p className="rounded-2xl border border-line bg-surface p-6 text-center text-sm text-ink-2">
          No saved reports yet. Every analysis you run from <b>New analysis</b> is saved here automatically.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {items.map((r) => {
            const d = r.data as ReportData;
            const n = d.findings?.length ?? 0;
            return (
              <li key={r.id} className="card-hover flex items-start justify-between gap-3 rounded-2xl border border-line bg-surface p-4">
                <button className="min-w-0 flex-1 text-left" onClick={() => onOpen(r.id)}>
                  <div className="truncate font-semibold text-ink">{r.title}</div>
                  <div className="mt-1 flex items-center gap-1.5 text-xs text-muted">
                    <Clock className="h-3.5 w-3.5" /> {new Date(r.savedAt).toLocaleString()} · {fmtBytes(r.bytes)}
                  </div>
                  <div className="mt-2 text-sm text-ink-2">
                    {n === 0 ? "No warnings" : `${n} warning${n > 1 ? "s" : ""}`} · {(d.summary?.totals.alerts ?? 0).toLocaleString()} alerts
                  </div>
                </button>
                <button className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink" aria-label={`Delete saved report ${r.title}`}
                  onClick={async () => { await deleteReport(r.id); load(); }}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function SavedView({ id, onBack }: { id: string; onBack: () => void }) {
  const [rec, setRec] = useState<SavedReport | null | undefined>(undefined);
  useEffect(() => { getReport(id).then((r) => setRec(r ?? null)); }, [id]);
  if (rec === undefined) return null;
  if (rec === null) return <p className="text-sm text-ink-2">This saved report no longer exists.</p>;
  return (
    <div className="space-y-5">
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <button className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" /> All saved reports
        </button>
        <ReportActions ids={rec.entityIds} />
      </div>
      <p className="text-sm text-ink-2">
        Saved report <b className="text-ink">{rec.title}</b> from {new Date(rec.savedAt).toLocaleString()}. This is the
        result as it was then; the live data may have changed since.
      </p>
      <Report ids={rec.entityIds} snapshot={rec.data as ReportData} checks={rec.checks}
        note={rec.classification ? <ClassifyNote classification={rec.classification as Record<string, Guess>} auto={rec.autoClassified ?? []} /> : undefined} />
    </div>
  );
}

export default function Results() {
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") === "saved" ? "saved" : "live";
  const savedId = sp.get("saved");
  const ids = (sp.get("entity_id") ?? "").split(",").filter(Boolean);
  const ents = useAsync(() => api.entities(), []);
  const names = Object.fromEntries((ents.data?.entities ?? []).map((e) => [e.entity_id, e.name]));
  const title = ids.length === 0 ? "All organisations" : ids.length === 1 ? names[ids[0]] ?? ids[0] : `${ids.length} organisations`;
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="My results"
        subtitle={tab === "live" ? `Live results for ${title}` : "Reports saved in this browser"}
        actions={
          <Segmented label="Results source" value={tab}
            onChange={(v) => setSp(v === "saved" ? { tab: "saved" } : {})}
            options={[{ value: "live", label: "Current data" }, { value: "saved", label: "Saved on this computer" }]} />
        }
      />
      {tab === "live" ? (
        <div className="space-y-5">
          <div className="no-print flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-ink-2">
              Show results for
              <select value={ids.length === 1 ? ids[0] : ""} onChange={(e) => setSp(e.target.value ? { entity_id: e.target.value } : {})}
                className="rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink">
                <option value="">All organisations</option>
                {ents.data?.entities.map((e) => <option key={e.entity_id} value={e.entity_id}>{e.name} ({e.entity_id})</option>)}
              </select>
            </label>
            <ReportActions ids={ids} />
          </div>
          <Report ids={ids} />
        </div>
      ) : savedId ? (
        <SavedView id={savedId} onBack={() => setSp({ tab: "saved" })} />
      ) : (
        <SavedList onOpen={(id) => setSp({ tab: "saved", saved: id })} />
      )}
    </div>
  );
}
