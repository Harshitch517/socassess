import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import RecordDrawer from "../components/RecordDrawer";
import { Async, Button, Card, PageHeader, SeverityBadge, Table, typeLabel, useAsync } from "../components/ui";

const KEY = "socassess.reviewed";

// Per-viewer "done" ticks kept in browser storage (a convenience; not shared or audited).
function useReviewed(): [Set<string>, (id: string) => void] {
  const [set, setSet] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(KEY) ?? "[]"));
    } catch {
      return new Set();
    }
  });
  const toggle = (id: string) => {
    const n = new Set(set);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    setSet(n);
    try {
      localStorage.setItem(KEY, JSON.stringify([...n]));
    } catch {
      /* storage unavailable */
    }
  };
  return [set, toggle];
}

export default function ReviewQueue() {
  const [sp, setSp] = useSearchParams();
  const entity = sp.get("entity_id") ?? "";
  const [spot, setSpot] = useState(true);
  const [open, setOpen] = useState<{ kind: string; id: string } | null>(null);
  const [done, toggle] = useReviewed();
  const ents = useAsync(() => api.entities(), []);
  const st = useAsync(() => api.queue({ entity_id: entity || undefined, include_spot_checks: spot, limit: 2000 }), [entity, spot]);
  return (
    <>
      <PageHeader
        title="Review queue"
        subtitle="What to check by hand, most important first: the strongest evidence for each finding, plus a random control sample of high/critical cases per entity."
        actions={<Button href={api.reportUrl("review_queue.csv")}>Export CSV</Button>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-ink-2">
          Entity
          <select
            value={entity}
            onChange={(e) => setSp(e.target.value ? { entity_id: e.target.value } : {})}
            className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option value="">All</option>
            {ents.data?.entities.map((e) => (
              <option key={e.entity_id} value={e.entity_id}>{e.entity_id} {e.name}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input type="checkbox" checked={spot} onChange={(e) => setSpot(e.target.checked)} />
          Include control spot-checks
        </label>
      </div>
      <Card>
        <Async state={st}>
          {(d) => (
            <>
              <p className="mb-2 text-xs text-muted">
                {d.total} items · {d.items.filter((i) => done.has(i.record_id)).length} ticked in this browser
              </p>
              <Table
                rows={d.items as unknown as Record<string, unknown>[]}
                empty="Nothing to review."
                columns={[
                  {
                    key: "done",
                    label: "Done",
                    render: (i) => (
                      <input
                        type="checkbox"
                        aria-label={`Mark ${i.record_id} reviewed`}
                        checked={done.has(i.record_id as string)}
                        onChange={() => toggle(i.record_id as string)}
                      />
                    ),
                  },
                  { key: "rank", label: "#", align: "right" },
                  { key: "entity_id", label: "Entity", render: (i) => <Link className="hover:text-accent hover:underline" to={`/entities/${i.entity_id}`}>{i.entity_id as string}</Link> },
                  {
                    key: "record_id",
                    label: "Record",
                    render: (i) =>
                      i.record_type === "finding" ? (
                        <Link className="text-accent hover:underline" to={`/findings/${i.finding_id}`}>whole finding</Link>
                      ) : (
                        <button className="text-left text-accent hover:underline" onClick={() => setOpen({ kind: i.record_type as string, id: i.record_id as string })}>
                          {i.record_type as string} {i.record_id as string}
                        </button>
                      ),
                  },
                  {
                    key: "reason",
                    label: "Why",
                    render: (i) =>
                      i.finding_id ? (
                        <Link className="hover:text-accent hover:underline" to={`/findings/${i.finding_id}`}>{typeLabel(i.finding_type as string)}: {i.finding_title as string}</Link>
                      ) : (
                        <span className="text-ink-2">{i.reason as string}</span>
                      ),
                  },
                  { key: "severity", label: "Severity", render: (i) => (i.finding_type === "spot_check" ? <span className="text-xs text-muted">control</span> : <SeverityBadge severity={i.severity as never} />) },
                  { key: "priority", label: "Priority", align: "right", render: (i) => (i.priority as number).toFixed(1) },
                ]}
              />
            </>
          )}
        </Async>
      </Card>
      {open && <RecordDrawer kind={open.kind} id={open.id} onClose={() => setOpen(null)} />}
    </>
  );
}
