import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import Report from "../components/Report";
import { fmtDate, PageHeader, useAsync } from "../components/ui";

export default function Results() {
  const [sp, setSp] = useSearchParams();
  const ids = (sp.get("entity_id") ?? "").split(",").filter(Boolean);
  const ents = useAsync(() => api.entities(), []);
  const health = useAsync(() => api.health(), []);
  const names = Object.fromEntries((ents.data?.entities ?? []).map((e) => [e.entity_id, e.name]));
  const title = ids.length === 0 ? "All organisations" : ids.length === 1 ? names[ids[0]] ?? ids[0] : `${ids.length} organisations`;
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title={`Results: ${title}`}
        subtitle={health.data?.latest_run ? `Latest analysis ${health.data.latest_run}` : undefined}
        actions={
          <label className="flex items-center gap-2 text-sm text-ink-2">
            Show results for
            <select
              value={ids.length === 1 ? ids[0] : ""}
              onChange={(e) => setSp(e.target.value ? { entity_id: e.target.value } : {})}
              className="rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink"
            >
              <option value="">All organisations</option>
              {ents.data?.entities.map((e) => (
                <option key={e.entity_id} value={e.entity_id}>{e.name} ({e.entity_id})</option>
              ))}
            </select>
          </label>
        }
      />
      <Report ids={ids} />
      {ents.data && <p className="mt-6 text-xs text-muted">Data as of {fmtDate(new Date().toISOString())}.</p>}
    </div>
  );
}
