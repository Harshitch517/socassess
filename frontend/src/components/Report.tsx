import { AlertTriangle, ChevronDown, ChevronRight, Info, ShieldAlert, ShieldCheck, Wrench } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type EntityScore, type Finding, type Guess, type Severity, type Summary } from "../api";
import { explain, SEVERITY_WORDS } from "../explain";
import SummaryPies from "./SummaryPies";
import { Async, Card, fmtInt, SeverityBadge, useAsync } from "./ui";

/** Everything a report shows. Fetched live, or loaded from a snapshot saved on this computer. */
export interface ReportData {
  summary: Summary;
  findings: Finding[];
  entities: EntityScore[];
}

export async function fetchReportData(ids: string[]): Promise<ReportData> {
  const key = ids.join(",");
  const [summary, f, e] = await Promise.all([
    api.summary(ids),
    api.findings({ entity_id: key || undefined, limit: 1000 }),
    api.entities(),
  ]);
  return {
    summary,
    findings: f.findings,
    entities: e.entities.filter((x) => ids.length === 0 || ids.includes(x.entity_id)),
  };
}

const VERDICT: Record<Severity | "none", { title: string; text: string; color: string; Icon: typeof ShieldAlert }> = {
  critical: { title: "Act now", text: "Serious weaknesses were found that could hide a real attack.", color: "var(--st-critical)", Icon: ShieldAlert },
  high: { title: "High risk", text: "Important problems need attention soon.", color: "var(--st-serious)", Icon: AlertTriangle },
  medium: { title: "Some problems to check", text: "A few things are worth looking into.", color: "var(--st-warning)", Icon: Info },
  low: { title: "Mostly fine", text: "Only minor points were found.", color: "var(--st-good)", Icon: ShieldCheck },
  none: { title: "Looks healthy", text: "No security concerns were found by any check.", color: "var(--st-good)", Icon: ShieldCheck },
};
const RANK: Record<string, number> = { low: 1, medium: 2, high: 3, critical: 4 };

export function ClassifyNote({ classification, auto }: { classification: Record<string, Guess>; auto: string[] }) {
  if (!auto.length) return null;
  const names: Record<string, string> = { data_type: "type of data", sector: "sector", size: "size" };
  return (
    <div className="flex gap-3 rounded-2xl border border-[var(--st-warning)] bg-[color-mix(in_srgb,var(--st-warning)_10%,transparent)] p-4 text-sm" role="note">
      <Info className="mt-0.5 h-5 w-5 shrink-0" style={{ color: "var(--st-warning)" }} aria-hidden />
      <div>
        <p className="font-semibold text-ink">Please classify your input for a better result</p>
        <p className="mt-1 text-ink-2">
          You didn't choose the {auto.map((k) => names[k]).join(", ")}, so SOCAssess guessed:{" "}
          {auto.map((k, i) => (
            <span key={k}>
              {i > 0 && "; "}
              <b className="text-ink">{classification[k].label}</b>
              {classification[k].reasons[0] && <> (because {classification[k].reasons[0]})</>}
            </span>
          ))}
          . The sector and size decide which organisations yours is compared with, so a wrong guess can hide or exaggerate problems.
        </p>
      </div>
    </div>
  );
}

function FindingCard({ f, live }: { f: Finding; live: boolean }) {
  const [open, setOpen] = useState(false);
  const e = explain(f);
  const Icon = f.severity === "critical" ? ShieldAlert : f.severity === "high" ? AlertTriangle : Info;
  const color = f.severity === "critical" ? "var(--st-critical)" : f.severity === "high" ? "var(--st-serious)" : f.severity === "medium" ? "var(--st-warning)" : "var(--muted)";
  return (
    <li className="card-hover break-inside-avoid rounded-2xl border border-line bg-surface p-4">
      <div className="flex gap-3">
        <Icon className="mt-0.5 h-6 w-6 shrink-0" style={{ color }} aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <SeverityBadge severity={f.severity} label={SEVERITY_WORDS[f.severity]} />
            <span>{e.check}</span>
            <span>·</span>
            {live ? <Link to={`/entities/${f.entity_id}`} className="hover:text-accent hover:underline">{f.entity_id}</Link> : <span>{f.entity_id}</span>}
          </div>
          <h3 className="mt-1.5 text-base font-semibold text-ink">{e.headline}</h3>
          {e.why && <p className="mt-2 text-sm text-ink-2"><b className="text-ink">Why it matters: </b>{e.why}</p>}
          {e.todo && (
            <p className="mt-1.5 flex gap-1.5 text-sm text-ink-2">
              <Wrench className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
              <span><b className="text-ink">What to do: </b>{e.todo}</span>
            </p>
          )}
          <div className="no-print mt-3 flex flex-wrap items-center gap-4 text-sm">
            <button className="inline-flex items-center gap-1 font-medium text-accent hover:underline" onClick={() => setOpen(!open)} aria-expanded={open}>
              {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />} {open ? "Hide details" : "Show details"}
            </button>
            {live && f.n_evidence > 0 && (
              <Link to={`/findings/${f.finding_id}`} className="font-medium text-accent hover:underline">
                See the evidence ({fmtInt(f.n_evidence)} records) →
              </Link>
            )}
          </div>
          {open && (
            <div className="mt-3 rounded-xl bg-surface-2 p-3 text-sm text-ink-2">
              <p>{f.rationale}</p>
              <p className="mt-2 text-xs text-muted">Technical name: {f.type} · detector {f.detector} · {f.points.toFixed(1)} risk points</p>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function ReportBody({ data, checks, live }: { data: ReportData; checks?: string[]; live: boolean }) {
  const visible = data.findings.filter((f) => !checks || checks.length === 0 || checks.includes(f.type));
  const hidden = data.findings.length - visible.length;
  const worst = visible.reduce<Severity | "none">((w, f) => (w === "none" || RANK[f.severity] > RANK[w] ? f.severity : w), "none");
  const v = VERDICT[worst];
  const shown = data.entities;
  return (
    <div className="space-y-6">
      <section className="glow-panel break-inside-avoid flex flex-wrap items-center gap-4 rounded-2xl border border-line bg-surface p-5"
        style={{ borderLeft: `6px solid ${v.color}`, ["--glow" as string]: v.color }}>
        <v.Icon className="h-12 w-12 shrink-0" style={{ color: v.color }} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Overall result</p>
          <h2 className="text-2xl font-semibold text-ink">{v.title}</h2>
          <p className="text-ink-2">
            {v.text}{" "}
            {visible.length > 0 && `${visible.length} warning${visible.length > 1 ? "s" : ""} for ${shown.length === 1 ? shown[0].name : `${shown.length} organisations`}.`}
          </p>
        </div>
        <div className="flex gap-6 text-center">
          {(["critical", "high", "medium"] as Severity[]).map((s) => (
            <div key={s}>
              <div className="text-2xl font-semibold text-ink">{visible.filter((f) => f.severity === s).length}</div>
              <div className="text-xs text-muted">{SEVERITY_WORDS[s]}</div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-ink">What we found</h2>
        {visible.length === 0 ? (
          <Card>
            <p className="text-sm text-ink-2">
              No warnings{hidden > 0 ? ` for the checks you selected (${hidden} more are hidden by your check selection)` : ""}.
              {data.summary.totals.entities === 1 && " Your data was compared with the built-in reference organisations."}
            </p>
          </Card>
        ) : (
          <ul className="space-y-3">
            {visible.map((f) => <FindingCard key={f.finding_id} f={f} live={live} />)}
            {hidden > 0 && <li className="text-sm text-muted">{hidden} more warning(s) hidden by your check selection.</li>}
          </ul>
        )}
      </section>

      <section className="print-break-before">
        <h2 className="mb-3 text-lg font-semibold text-ink">In charts</h2>
        <SummaryPies s={data.summary} />
      </section>
    </div>
  );
}

export default function Report({ ids, checks, note, snapshot }: {
  ids: string[];
  checks?: string[];
  note?: React.ReactNode;
  snapshot?: ReportData;
}) {
  const key = ids.join(",");
  const live = useAsync(() => (snapshot ? Promise.resolve(snapshot) : fetchReportData(ids)), [key, snapshot]);
  return (
    <div className="space-y-6">
      {note}
      <Async state={live}>{(d) => <ReportBody data={d} checks={checks} live={!snapshot} />}</Async>
    </div>
  );
}
