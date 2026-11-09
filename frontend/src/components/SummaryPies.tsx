import { HelpCircle, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { Summary } from "../api";
import { CATEGORY_COLORS, Donut, SEVERITY_SLICES, type Slice } from "./charts";

const AREA = [
  { key: "execution_gap", label: "Execution gaps (work done badly)", color: "var(--series-1)" },
  { key: "negative_space", label: "Negative space (missing work or data)", color: "var(--series-2)" },
  { key: "anomaly", label: "Unusual operating profile", color: "var(--series-3)" },
];
const BANDS = [
  { key: "critical", label: "Critical risk", color: "var(--st-critical)" },
  { key: "high", label: "High risk", color: "var(--st-serious)" },
  { key: "medium", label: "Medium risk", color: "var(--st-warning)" },
  { key: "low", label: "Low risk", color: "var(--st-good)" },
];

const pick = <T extends { n: number }>(rows: T[], key: keyof T, v: string) => rows.find((r) => r[key] === v)?.n ?? 0;

/** One sentence about the user's own numbers: the biggest slice and its share. */
function reading(slices: Slice[], noun: string, empty: string): string {
  const data = slices.filter((s) => s.value > 0);
  const total = data.reduce((a, s) => a + s.value, 0);
  if (!total) return empty;
  const top = [...data].sort((a, b) => b.value - a.value)[0];
  const share = Math.round((top.value / total) * 100);
  if (data.length === 1) return `All ${total.toLocaleString()} ${noun} are "${top.label}".`;
  return `The largest part is "${top.label}": ${top.value.toLocaleString()} of ${total.toLocaleString()} ${noun} (${share}%).`;
}

function PieCard({ title, subtitle, what, how, read, children }: {
  title: string; subtitle: string; what: string; how: string; read: string; children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <section className="card-hover break-inside-avoid rounded-2xl border border-line bg-surface p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
          <p className="mt-0.5 text-xs text-ink-2">{subtitle}</p>
        </div>
        <button onClick={() => setOpen(!open)} aria-expanded={open}
          className="no-print inline-flex shrink-0 items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs font-medium text-ink-2 hover:border-[var(--accent)] hover:text-accent">
          {open ? <X className="h-3.5 w-3.5" /> : <HelpCircle className="h-3.5 w-3.5" />} {open ? "Close" : "Explain"}
        </button>
      </div>
      {open && (
        <div className="mb-3 space-y-1.5 rounded-xl bg-accent-wash p-3 text-xs text-ink-2" role="note">
          <p><b className="text-ink">What it shows: </b>{what}</p>
          <p><b className="text-ink">How to read it: </b>{how}</p>
          <p><b className="text-ink">In your data: </b>{read}</p>
        </div>
      )}
      {children}
    </section>
  );
}

export default function SummaryPies({ s }: { s: Summary }) {
  const nice = (c: string) => c.replace(/_/g, " ").replace(/^\w/, (m) => m.toUpperCase());
  const sev = SEVERITY_SLICES.map((x) => ({ ...x, value: pick(s.by_severity, "severity", x.key) }));
  const area = AREA.map((x) => ({ ...x, value: pick(s.by_category, "category", x.key) }));
  const bands = BANDS.map((x) => ({ ...x, value: pick(s.bands, "band", x.key) }));
  const alertSev = SEVERITY_SLICES.map((x) => ({ ...x, value: pick(s.alert_severity, "severity", x.key) }));
  const cats = s.alert_category.map((c, i) => ({
    key: c.category, label: nice(c.category), value: c.n,
    color: c.category === "other" ? "var(--muted)" : CATEGORY_COLORS[i % CATEGORY_COLORS.length],
  }));
  const ent = s.totals.entities === 1 ? "entity" : "entities";
  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
      <PieCard title="Security concerns by severity" subtitle="Warnings raised by the analysis"
        what="Every warning SOCAssess raised, split by how urgent it is."
        how="Red (critical) means act now, orange (high) means serious, yellow (medium) means worth checking. A large red or orange share means urgent work."
        read={reading(sev, "warnings", "No warnings were raised. Nothing urgent to do.")}>
        <Donut centerLabel="warnings" empty="No security concerns found." slices={sev} />
      </PieCard>
      <PieCard title="Concern areas" subtitle="What kind of weakness the warnings point to"
        what="The type of problem behind each warning."
        how="Execution gaps = work is being done badly (closed too fast, not escalated, copy-paste notes). Negative space = something is missing (systems sending no logs, attack types never detected, missing records). Unusual profile = the SOC behaves very differently from its peers."
        read={reading(area, "warnings", "No warnings, so there is nothing to split.")}>
        <Donut centerLabel="warnings" empty="No security concerns found." slices={area} />
      </PieCard>
      <PieCard title="Entity risk levels" subtitle="Organisations by overall risk level"
        what="How many organisations fall into each overall risk level."
        how="The level comes from the risk score (the sum of points for every warning), and is never lower than the organisation's most serious warning. Green is low risk."
        read={reading(bands, ent, "No organisations in this view.")}>
        <Donut centerLabel={ent} slices={bands} />
      </PieCard>
      <PieCard title="Alerts by severity" subtitle="Severity mix of the alerts in the data"
        what="The alerts in the data itself (not SOCAssess's warnings), split by the severity your tools gave them."
        how="Most SOCs see mostly low and medium alerts. A very large critical share can mean noisy detection rules; almost no high or critical alerts can mean detection is missing."
        read={reading(alertSev, "alerts", "No alerts in this view.")}>
        <Donut centerLabel="alerts" slices={alertSev} />
      </PieCard>
      <PieCard title="Alerts by category" subtitle="Six largest categories; the rest grouped as Other"
        what="Which kinds of activity the alerts are about (phishing, malware, scans...)."
        how="Compare with what you would expect for the sector. A kind of attack that is completely missing here (for example lateral movement) can point to a blind spot. See the 'Missing types of alerts' warning."
        read={reading(cats, "alerts", "No alerts in this view.")}>
        <Donut centerLabel="alerts" slices={cats} />
      </PieCard>
    </div>
  );
}
