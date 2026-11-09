import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Async, Card, CATEGORY_LABEL, fmtInt, PageHeader, SeverityBadge, Table, TYPE_LABEL, typeLabel, useAsync } from "../components/ui";

const SEVS = ["critical", "high", "medium", "low"];

export default function Findings() {
  const [sp, setSp] = useSearchParams();
  const filters = {
    entity_id: sp.get("entity_id") ?? "",
    type: sp.get("type") ?? "",
    severity: sp.get("severity") ?? "",
    category: sp.get("category") ?? "",
  };
  const st = useAsync(() => api.findings({ ...filters, limit: 1000 }), [sp.toString()]);
  const ents = useAsync(() => api.entities(), []);
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(sp);
    if (v) n.set(k, v);
    else n.delete(k);
    setSp(n);
  };
  const select = (k: keyof typeof filters, label: string, opts: { value: string; label: string }[]) => (
    <label className="flex flex-col gap-1 text-xs text-ink-2">
      {label}
      <select value={filters[k]} onChange={(e) => set(k, e.target.value)} className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink">
        <option value="">All</option>
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <>
      <PageHeader title="Findings" subtitle="Every finding has a rationale and the records behind it" />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        {select("entity_id", "Entity", (ents.data?.entities ?? []).map((e) => ({ value: e.entity_id, label: `${e.entity_id} ${e.name}` })))}
        {select("type", "Type", Object.keys(TYPE_LABEL).filter((t) => t !== "spot_check").map((t) => ({ value: t, label: typeLabel(t) })))}
        {select("severity", "Severity", SEVS.map((s) => ({ value: s, label: s })))}
        {select("category", "Category", Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label })))}
        {sp.toString() && (
          <button className="pb-1.5 text-sm text-accent hover:underline" onClick={() => setSp(new URLSearchParams())}>
            Clear filters
          </button>
        )}
      </div>
      <Card>
        <Async state={st}>
          {(d) => (
            <>
              <p className="mb-2 text-xs text-muted">{d.total} finding(s)</p>
              <Table
                rows={d.findings as unknown as Record<string, unknown>[]}
                empty="No findings match these filters."
                columns={[
                  { key: "severity", label: "Severity", render: (f) => <SeverityBadge severity={f.severity as never} /> },
                  {
                    key: "title",
                    label: "Finding",
                    render: (f) => (
                      <div className="min-w-[16rem]">
                        <Link className="font-medium text-ink hover:text-accent hover:underline" to={`/findings/${f.finding_id}`}>
                          {f.title as string}
                        </Link>
                        <div className="text-xs text-ink-2">{typeLabel(f.type as string)} · {CATEGORY_LABEL[f.category as string]}</div>
                      </div>
                    ),
                  },
                  { key: "entity_id", label: "Entity", render: (f) => <Link className="hover:text-accent hover:underline" to={`/entities/${f.entity_id}`}>{f.entity_id as string}</Link> },
                  { key: "n_evidence", label: "Evidence", align: "right", render: (f) => fmtInt(f.n_evidence as number) },
                  { key: "points", label: "Points", align: "right", render: (f) => (f.points as number).toFixed(1) },
                ]}
              />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}
