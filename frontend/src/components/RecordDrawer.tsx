import { useEffect } from "react";
import { api } from "../api";
import { Sparkline } from "./charts";
import { Async, fmtDate, Table, useAsync } from "./ui";

const HIDE = new Set(["telemetry", "recent_alerts", "alert", "case", "escalations"]);

function Fields({ obj }: { obj: Record<string, unknown> }) {
  return (
    <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1.5 text-sm">
      {Object.entries(obj)
        .filter(([k, v]) => !HIDE.has(k) && typeof v !== "object")
        .map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-ink-2">{k.replace(/_/g, " ")}</dt>
            <dd className="min-w-0 break-words text-ink">
              {typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v) ? fmtDate(v) : v === null ? "–" : String(v)}
            </dd>
          </div>
        ))}
    </dl>
  );
}

export default function RecordDrawer({ kind, id, onClose }: { kind: string; id: string; onClose: () => void }) {
  const state = useAsync(() => api.record(kind, id), [kind, id]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${kind} ${id}`}
        className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-wide text-muted">{kind}</div>
            <h2 className="text-lg font-semibold text-ink">{id}</h2>
          </div>
          <button className="rounded-md border border-line px-2 py-1 text-sm text-ink-2 hover:text-ink" onClick={onClose}>
            Close
          </button>
        </div>
        <Async state={state}>
          {(r) => (
            <div className="space-y-5">
              <Fields obj={r} />
              {"alert" in r && r.alert != null && (
                <section>
                  <h3 className="mb-2 text-sm font-semibold">Linked alert</h3>
                  <Fields obj={r.alert as Record<string, unknown>} />
                </section>
              )}
              {"case" in r && (
                <section>
                  <h3 className="mb-2 text-sm font-semibold">Linked case</h3>
                  {r.case ? <Fields obj={r.case as Record<string, unknown>} /> : (
                    <p className="text-sm text-ink-2">No case record exists for this alert.</p>
                  )}
                </section>
              )}
              {"escalations" in r && (
                <section>
                  <h3 className="mb-2 text-sm font-semibold">Escalation records</h3>
                  <Table
                    rows={r.escalations as Record<string, unknown>[]}
                    empty="No escalation record."
                    columns={[
                      { key: "escalation_id", label: "Id" },
                      { key: "escalated_at", label: "When", render: (x) => fmtDate(x.escalated_at as string) },
                      { key: "escalated_to", label: "To" },
                    ]}
                  />
                </section>
              )}
              {"telemetry" in r && (
                <section>
                  <h3 className="mb-1 text-sm font-semibold">Daily telemetry events</h3>
                  {(r.telemetry as unknown[]).length ? (
                    <Sparkline data={r.telemetry as Record<string, unknown>[]} xKey="date" yKey="event_count" label="events" />
                  ) : (
                    <p className="text-sm text-ink-2">No telemetry rows at all for this asset.</p>
                  )}
                </section>
              )}
              {"recent_alerts" in r && (
                <section>
                  <h3 className="mb-2 text-sm font-semibold">Recent alerts on this asset</h3>
                  <Table
                    rows={r.recent_alerts as Record<string, unknown>[]}
                    empty="No alerts on this asset."
                    columns={[
                      { key: "ts", label: "Time", render: (x) => fmtDate(x.ts as string) },
                      { key: "rule_name", label: "Rule" },
                      { key: "severity", label: "Severity" },
                    ]}
                  />
                </section>
              )}
            </div>
          )}
        </Async>
      </aside>
    </div>
  );
}
