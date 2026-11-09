import type { Summary } from "../api";
import { CATEGORY_COLORS, Donut, SEVERITY_SLICES } from "./charts";
import { Card } from "./ui";

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

export default function SummaryPies({ s }: { s: Summary }) {
  const nice = (c: string) => c.replace(/_/g, " ").replace(/^\w/, (m) => m.toUpperCase());
  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
      <Card title="Security concerns by severity" subtitle="Findings raised by the analysis">
        <Donut centerLabel="findings" empty="No security concerns found."
          slices={SEVERITY_SLICES.map((x) => ({ ...x, value: pick(s.by_severity, "severity", x.key) }))} />
      </Card>
      <Card title="Concern areas" subtitle="What kind of weakness the findings point to">
        <Donut centerLabel="findings" empty="No security concerns found."
          slices={AREA.map((x) => ({ ...x, value: pick(s.by_category, "category", x.key) }))} />
      </Card>
      <Card title="Entity risk levels" subtitle="Organisations by overall risk band">
        <Donut centerLabel={s.totals.entities === 1 ? "entity" : "entities"}
          slices={BANDS.map((x) => ({ ...x, value: pick(s.bands, "band", x.key) }))} />
      </Card>
      <Card title="Alerts by severity" subtitle="Severity mix of the alerts in the data">
        <Donut centerLabel="alerts"
          slices={SEVERITY_SLICES.map((x) => ({ ...x, value: pick(s.alert_severity, "severity", x.key) }))} />
      </Card>
      <Card title="Alerts by category" subtitle="Six largest categories; the rest grouped as Other">
        <Donut centerLabel="alerts"
          slices={s.alert_category.map((c, i) => ({
            key: c.category, label: nice(c.category), value: c.n,
            color: c.category === "other" ? "var(--muted)" : CATEGORY_COLORS[i % CATEGORY_COLORS.length],
          }))} />
      </Card>
    </div>
  );
}
