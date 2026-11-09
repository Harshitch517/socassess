// Plain-language explanations for each kind of finding: a friendly headline, why it matters,
// and what to do. Numbers come from the finding's measured values; technical detail stays
// behind "Show details" in the UI.
import type { Finding } from "./api";

type MV = Record<string, unknown>;
const n = (v: unknown) => (typeof v === "number" ? v.toLocaleString("en-US") : String(v ?? "?"));
const pct = (v: unknown) => (typeof v === "number" ? `${Math.round(v * 100)}%` : "?");
const list = (v: unknown) =>
  Array.isArray(v) ? v.map((x) => String(x).replace(/_/g, " ")).join(", ") : String(v ?? "");

interface Explainer {
  check: string; // name used in the "which checks" selector
  about: string; // one-line description of the check
  headline: (m: MV) => string;
  why: string;
  todo: string;
}

export const EXPLAIN: Record<string, Explainer> = {
  fast_closure: {
    check: "Alerts closed too quickly",
    about: "Serious alerts closed in minutes, too fast to have been investigated.",
    headline: (m) => `${n(m.count)} serious alerts were closed within minutes (${pct(m.rate)} of them)`,
    why: "A real investigation of a high or critical alert takes time. Closing it in a couple of minutes usually means nobody looked, and a real attack may have been dismissed.",
    todo: "Re-open a sample of these cases and check whether they were investigated. Agree a minimum investigation standard for high and critical alerts.",
  },
  critical_no_escalation: {
    check: "Critical incidents not escalated",
    about: "Confirmed critical incidents that were never reported upwards.",
    headline: (m) => `${n(m.count)} confirmed critical incidents were never escalated`,
    why: "Confirmed critical incidents must reach the incident-response team, management and, where required, CERT-In / NCIIPC. If they stay inside the SOC, nobody with authority can act.",
    todo: "Review these incidents with the SOC lead, escalate the ones still open, and check the escalation procedure is being followed.",
  },
  template_notes: {
    check: "Copy-paste investigation notes",
    about: "Many cases closed with the same template text instead of real notes.",
    headline: (m) => `${n(m.count)} cases have copy-pasted investigation notes (${pct(m.rate)})`,
    why: "Identical notes on different alerts suggest the cases were closed without a real investigation, and they leave no useful record for audits or later incidents.",
    todo: "Talk to the analysts named in the details, check a sample of their cases, and require notes that describe what was actually checked.",
  },
  repeated_no_remediation: {
    check: "Repeat alerts with no fix",
    about: "The same alert keeps firing on the same machine and nothing is fixed.",
    headline: (m) => `The same alerts keep firing on ${n(Array.isArray(m.pairs) ? m.pairs.length : "?")} machine(s) with no fix (${n(m.alerts)} alerts)`,
    why: "An alert that repeats for weeks on one machine means the root cause (malware, a misconfiguration, a weak password) was never removed. Each repeat is wasted analyst time, or an ongoing compromise.",
    todo: "Fix the root cause on the listed machines, or tune the rule if it is a known false alarm, and record the remediation.",
  },
  sla_gaming: {
    check: "Closed just before the deadline",
    about: "Cases bunched just inside the response deadline, as if closed to meet the target.",
    headline: (m) => `${n(m.count)} cases were closed just before their deadline (${pct(m.rate)})`,
    why: "Genuine work finishes at different times. A spike right before the deadline suggests cases are being closed to meet the target rather than because the work is done.",
    todo: "Check a sample of these cases for completeness, and review whether the SLA targets encourage rushing.",
  },
  sla_breach: {
    check: "Deadlines missed",
    about: "Many cases closed after their response deadline.",
    headline: (m) => `${n(m.count)} cases missed their response deadline (${pct(m.rate)})`,
    why: "Slow responses give attackers more time. A high breach rate often means the SOC is under-staffed or overloaded.",
    todo: "Look at workload and staffing, and at which alert types take longest.",
  },
  silent_critical_assets: {
    check: "Critical systems sending no logs",
    about: "Important systems that are not sending security logs (blind spots).",
    headline: (m) => `${n(m.silent_assets)} critical systems are sending no security logs`,
    why: "If a critical system (for example a domain controller, SCADA HMI or database) sends no logs, an attack on it would not be seen at all.",
    todo: "Check the log agents and forwarding for the listed systems and restore monitoring as a priority.",
  },
  missing_categories: {
    check: "Missing types of alerts",
    about: "Types of attack that similar organisations detect but this one never reports.",
    headline: (m) => `No alerts at all for: ${list(m.missing)}`,
    why: "Similar organisations regularly see these types of activity. Seeing none usually means the detection rules or log sources for them are missing, not that the organisation is never targeted.",
    todo: "Check that detection rules and log sources exist for these attack types (for example EDR coverage for lateral movement).",
  },
  missing_records: {
    check: "Missing case or escalation records",
    about: "Serious alerts with no case, or escalations with no record.",
    headline: (m) =>
      `${n(Number(m.uncased_high_critical_alerts ?? 0) + Number(m.escalated_without_record ?? 0))} serious alerts or escalations have no record`,
    why: "Work that leaves no record cannot be checked, and may never have happened. It also breaks the audit trail regulators expect.",
    todo: "Find out why these alerts have no case and make case creation automatic for high and critical alerts.",
  },
  low_activity: {
    check: "Unusually low alert volume",
    about: "Far fewer alerts than comparable organisations.",
    headline: (m) => `Alert volume is only ${pct(m.ratio)} of comparable organisations`,
    why: "Very few alerts for the number of systems usually means detection is switched off, badly tuned or not covering everything, rather than that nothing is happening.",
    todo: "Review which detection rules are enabled and whether all systems are covered.",
  },
  operational_anomaly: {
    check: "Unusual overall pattern",
    about: "The organisation's overall SOC behaviour is very different from its peers.",
    headline: () => "This SOC works very differently from comparable organisations",
    why: "Several of its key numbers (shown in the details) are far from what peers do. On its own this is not proof of a problem, but it points to where to look.",
    todo: "Look at the listed metrics first. They usually overlap with the other warnings above.",
  },
};

export function explain(f: Finding) {
  const e = EXPLAIN[f.type];
  if (!e) return { headline: f.title, why: "", todo: "", check: f.type };
  let headline = f.title;
  try {
    headline = e.headline(f.metric_values as MV);
  } catch {
    /* fall back to the technical title */
  }
  return { headline, why: e.why, todo: e.todo, check: e.check };
}

export const SEVERITY_WORDS: Record<string, string> = {
  critical: "Act now",
  high: "Serious",
  medium: "Worth checking",
  low: "Minor",
};
