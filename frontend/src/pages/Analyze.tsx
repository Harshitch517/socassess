import {
  Banknote, Building2, Bus, Check, ClipboardList, Database, FileSpreadsheet, FileUp, FlaskConical, HeartPulse,
  FileDown, HardDrive, HelpCircle, Landmark, Loader2, Package, Paperclip, Printer, Radio, RotateCcw, ServerCog,
  ShieldCheck, Upload as UploadIcon, Waves, X, Zap,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError, type Detection, type UploadResult } from "../api";
import HeroArt from "../components/HeroArt";
import Report, { ClassifyNote, fetchReportData, type ReportData } from "../components/Report";
import { clearDraft, DRAFT_LIMIT, fmtBytes, loadDraft, saveDraft, saveReport, type SavedReport } from "../lib/localStore";
import { ErrorBox, useAsync } from "../components/ui";
import { EXPLAIN } from "../explain";

const DATA_TYPES = [
  { value: "alerts", label: "Security alerts", hint: "Export from a SIEM, EDR or IDS: one row per alert", Icon: ShieldCheck },
  { value: "cases", label: "Incident / case records", hint: "Tickets with who handled them, when, and the outcome", Icon: ClipboardList },
  { value: "assets", label: "Asset inventory", hint: "List of systems and how critical they are", Icon: ServerCog },
  { value: "full", label: "Full SOC export", hint: "Several tables: alerts, cases, escalations, assets, logs", Icon: Package },
];
const SECTORS = [
  { value: "power", label: "Power", Icon: Zap },
  { value: "banking", label: "Banking", Icon: Banknote },
  { value: "telecom", label: "Telecom", Icon: Radio },
  { value: "transport", label: "Transport", Icon: Bus },
  { value: "health", label: "Health", Icon: HeartPulse },
  { value: "government", label: "Government", Icon: Landmark },
  { value: "water", label: "Water", Icon: Waves },
  { value: "other", label: "Other", Icon: Building2 },
];
const SIZES = [
  { value: "small", label: "Small", hint: "under ~100 systems" },
  { value: "medium", label: "Medium", hint: "~100–300 systems" },
  { value: "large", label: "Large", hint: "300+ systems" },
];
const SAMPLES = [
  { file: "sample_grid_utility_alerts.csv", label: "Power utility: alert export", hint: "A plain SIEM export (2,000 alerts). Some attack types are never detected.", Icon: FileSpreadsheet },
  { file: "sample_bank_full_export.zip", label: "Bank: full SOC export", hint: "Alerts, cases, escalations, assets and logs. Has closure and escalation problems.", Icon: Database },
];
const ALL_CHECKS = Object.keys(EXPLAIN);

type Step = 1 | 2 | 3;

function Stepper({ step }: { step: Step }) {
  const steps = ["Describe your data", "Add your data", "See the report"];
  return (
    <ol className="no-print mb-6 flex flex-wrap items-center gap-2 text-sm" aria-label="Progress">
      {steps.map((s, i) => {
        const n = (i + 1) as Step;
        const done = n < step;
        const now = n === step;
        return (
          <li key={s} className="flex items-center gap-2" aria-current={now ? "step" : undefined}>
            <span className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
              now ? "bg-accent text-white" : done ? "bg-accent-wash text-accent" : "bg-surface-2 text-muted"}`}>
              {done ? <Check className="h-4 w-4" /> : n}
            </span>
            <span className={now ? "font-semibold text-ink" : "text-ink-2"}>{s}</span>
            {i < steps.length - 1 && <span className="mx-1 h-px w-8 bg-grid" aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}

function Choice({ selected, onClick, children, className = "" }: { selected: boolean; onClick: () => void; children: ReactNode; className?: string }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={selected}
      className={`card-hover rounded-xl border p-3 text-left ${selected
        ? "border-[var(--accent)] bg-accent-wash ring-1 ring-[var(--accent)]"
        : "border-line bg-surface hover:bg-surface-2"} ${className}`}>
      {children}
    </button>
  );
}

function Section({ title, help, children }: { title: string; help?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-surface/90 p-5 backdrop-blur">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      {help && <p className="mt-0.5 text-sm text-ink-2">{help}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function ReportActions({ ids, onAnother, saved }: { ids: string[]; onAnother?: () => void; saved?: SavedReport | null }) {
  return (
    <div className="no-print flex flex-wrap items-center gap-2">
      {saved && (
        <span className="inline-flex items-center gap-1 text-xs text-muted" title="Kept in this browser; see My results → Saved on this computer">
          <HardDrive className="h-3.5 w-3.5" aria-hidden /> Saved on this computer
        </span>
      )}
      <button className="btn-primary inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium" onClick={() => window.print()}>
        <Printer className="h-4 w-4" aria-hidden /> Save report as PDF
      </button>
      <a className="card-hover inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-4 py-2 text-sm font-medium text-ink"
        href={ids.length === 1 ? api.reportUrl(`entity/${ids[0]}.pdf`) : api.reportUrl("summary.pdf")} download>
        <FileDown className="h-4 w-4" aria-hidden /> Detailed PDF
      </a>
      {onAnother && (
        <button className="card-hover inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-4 py-2 text-sm font-medium text-ink" onClick={onAnother}>
          <RotateCcw className="h-4 w-4" aria-hidden /> Analyse another
        </button>
      )}
    </div>
  );
}

const CONF: Record<string, string> = { high: "sure", medium: "fairly sure", low: "a rough guess", user: "your choice" };

export default function Analyze() {
  const [step, setStep] = useState<Step>(1);
  const [dataType, setDataType] = useState<string>();
  const [sector, setSector] = useState<string>();
  const [size, setSize] = useState<string>();
  const [org, setOrg] = useState("");
  const [checks, setChecks] = useState<string[]>(ALL_CHECKS);
  const [showChecks, setShowChecks] = useState(false);
  const [mode, setMode] = useState<"file" | "paste" | "sample">("file");
  const [files, setFiles] = useState<File[]>([]);
  const [text, setText] = useState("");
  const [det, setDet] = useState<Detection | null>(null);
  const [busy, setBusy] = useState<"" | "reading" | "analysing">("");
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [drag, setDrag] = useState(false);
  const [restored, setRestored] = useState<string | null>(null);
  const [cacheNote, setCacheNote] = useState<"" | "too-big" | "unavailable">("");
  const [snapshot, setSnapshot] = useState<ReportData | null>(null);
  const [saved, setSaved] = useState<SavedReport | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const health = useAsync(() => api.health(), []);

  // Restore the last unfinished analysis (file + choices) kept in this browser.
  useEffect(() => {
    loadDraft().then((d) => {
      if (d) {
        setDataType(d.dataType); setSector(d.sector); setSize(d.size); setOrg(d.org ?? "");
        if (d.checks?.length) setChecks(d.checks);
        setMode(d.mode ?? "file"); setText(d.text ?? "");
        const fs = (d.files ?? []).map((f) => new File([f.blob], f.name, { type: f.type }));
        setFiles(fs);
        if (d.detection) setDet(d.detection as Detection);
        if (fs.length || d.text) {
          setRestored(fs.map((f) => f.name).join(", ") || "your pasted data");
          setStep(2);
        }
      }
      setHydrated(true);
    });
  }, []);

  // Keep the draft up to date (up to 200 MB) while the user moves between steps.
  useEffect(() => {
    if (!hydrated || step === 3) return;
    const t = setTimeout(() => {
      saveDraft({
        files: files.map((f) => ({ name: f.name, type: f.type, blob: f })), text, mode,
        dataType, sector, size, org, checks, detection: det ?? undefined,
      }).then((r) => setCacheNote(r === "saved" ? "" : r));
    }, 400);
    return () => clearTimeout(t);
  }, [hydrated, step, files, text, mode, dataType, sector, size, org, checks, det]);
  const ro = health.data?.read_only;

  const read = async (fs: File[]) => {
    setFiles(fs);
    setDet(null);
    setError(null);
    if (!fs.length) return;
    setBusy("reading");
    try {
      setDet(await api.detect(fs));
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy("");
    }
  };
  const fromPaste = () => {
    const t = text.trim();
    return [new File([t], t.startsWith("[") || t.startsWith("{") ? "pasted_data.json" : "pasted_data.csv")];
  };
  const loadSample = async (name: string) => {
    setError(null);
    try {
      const r = await fetch(`/samples/${name}`);
      if (!r.ok) throw new Error(`Sample not found (${r.status})`);
      const f = new File([await r.blob()], name);
      if (!org) setOrg(name.includes("bank") ? "Sample Bank" : "Sample Grid Utility");
      await read([f]);
    } catch (e) {
      setError(e as Error);
    }
  };
  const useGuesses = () => {
    if (!det) return;
    setDataType(dataType ?? det.data_type.value);
    setSector(sector ?? det.sector.value);
    setSize(size ?? det.size.value);
  };
  const analyse = async () => {
    setBusy("analysing");
    setError(null);
    try {
      const fs = mode === "paste" && !files.length ? fromPaste() : files;
      const r = await api.upload(fs, true, org.trim() || undefined, { data_type: dataType, sector, size });
      const data = await fetchReportData(r.entity_ids);
      setResult(r);
      setSnapshot(data);
      setStep(3);
      clearDraft(); // the analysed input is done with; the report itself is saved below
      saveReport({
        title: org.trim() || r.entity_ids.join(", "), entityIds: r.entity_ids, runId: r.analysis_run_id,
        classification: r.classification, autoClassified: r.auto_classified,
        checks: checks.length === ALL_CHECKS.length ? undefined : checks, data,
      }).then((rec) => setSaved(rec ?? null));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy("");
    }
  };
  const reset = () => {
    setStep(1); setFiles([]); setText(""); setDet(null); setResult(null); setError(null);
    setSnapshot(null); setSaved(null); setRestored(null); setOrg("");
    setDataType(undefined); setSector(undefined); setSize(undefined); setChecks(ALL_CHECKS);
    clearDraft();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const forgetFile = () => {
    setFiles([]); setText(""); setDet(null); setRestored(null);
  };

  const unclassified = [!dataType && "type of data", !sector && "sector", !size && "size"].filter(Boolean) as string[];

  return (
    <div className="mx-auto max-w-5xl">
      <header className="hero no-print mb-6 flex items-center gap-6 overflow-hidden rounded-3xl border border-line p-6 md:p-8">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-widest text-accent">SOC security health check</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink md:text-4xl">Check a SOC's security health</h1>
          <p className="mt-3 max-w-xl text-ink-2">
            Give SOCAssess your security-operations data and get a plain-language report with charts in seconds.
            Everything stays on this computer.
          </p>
        </div>
        <HeroArt className="hidden h-44 w-56 shrink-0 md:block" />
      </header>
      <Stepper step={step} />
      {ro && (
        <div className="mb-4 rounded-xl border border-line bg-surface-2 p-3 text-sm text-ink-2">
          This is a read-only demo. Adding data is turned off here, but you can open <a className="text-accent underline" href="/results">the demo results</a>.
        </div>
      )}

      {step === 1 && (
        <div className="space-y-5">
          <Section title="What kind of data do you have?" help="Optional. If you're not sure, skip it and we'll work it out.">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {DATA_TYPES.map((d) => (
                <Choice key={d.value} selected={dataType === d.value} onClick={() => setDataType(dataType === d.value ? undefined : d.value)}>
                  <div className="flex gap-3">
                    <d.Icon className="h-6 w-6 shrink-0 text-accent" aria-hidden />
                    <div>
                      <div className="font-medium text-ink">{d.label}</div>
                      <div className="text-sm text-ink-2">{d.hint}</div>
                    </div>
                  </div>
                </Choice>
              ))}
            </div>
          </Section>
          <Section title="Which sector is the organisation in?" help="Optional. Used to compare it with similar organisations.">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {SECTORS.map((s) => (
                <Choice key={s.value} selected={sector === s.value} onClick={() => setSector(sector === s.value ? undefined : s.value)} className="flex items-center gap-2">
                  <s.Icon className="h-5 w-5 text-accent" aria-hidden />
                  <span className="font-medium text-ink">{s.label}</span>
                </Choice>
              ))}
            </div>
          </Section>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <Section title="How big is it?" help="Optional.">
              <div className="grid grid-cols-3 gap-2">
                {SIZES.map((s) => (
                  <Choice key={s.value} selected={size === s.value} onClick={() => setSize(size === s.value ? undefined : s.value)}>
                    <div className="font-medium text-ink">{s.label}</div>
                    <div className="text-xs text-ink-2">{s.hint}</div>
                  </Choice>
                ))}
              </div>
            </Section>
            <Section title="Organisation name" help="Optional. Shown in the report.">
              <input value={org} onChange={(e) => setOrg(e.target.value)} maxLength={80} placeholder="e.g. State Power Utility"
                className="w-full rounded-xl border border-line bg-surface px-3 py-2.5 text-ink" />
            </Section>
          </div>
          <Section title="Which checks should the report include?" help={`${checks.length} of ${ALL_CHECKS.length} selected. All checks always run; this only chooses what the report shows.`}>
            <button className="text-sm font-medium text-accent hover:underline" onClick={() => setShowChecks(!showChecks)} aria-expanded={showChecks}>
              {showChecks ? "Hide the list" : "Choose checks"}
            </button>
            {showChecks && (
              <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                {ALL_CHECKS.map((c) => (
                  <label key={c} className="flex cursor-pointer gap-2 rounded-lg border border-line p-2.5 text-sm hover:bg-surface-2">
                    <input type="checkbox" className="mt-1" checked={checks.includes(c)}
                      onChange={() => setChecks(checks.includes(c) ? checks.filter((x) => x !== c) : [...checks, c])} />
                    <span>
                      <span className="font-medium text-ink">{EXPLAIN[c].check}</span>
                      <span className="block text-ink-2">{EXPLAIN[c].about}</span>
                    </span>
                  </label>
                ))}
                <div className="flex gap-3 text-sm md:col-span-2">
                  <button className="text-accent hover:underline" onClick={() => setChecks(ALL_CHECKS)}>Select all</button>
                  <button className="text-accent hover:underline" onClick={() => setChecks([])}>Clear</button>
                </div>
              </div>
            )}
          </Section>
          {(files.length > 0 || text.trim()) && (
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink-2">
              <Paperclip className="h-4 w-4 text-accent" aria-hidden />
              Your data is kept: <b className="text-ink">{files.map((f) => f.name).join(", ") || "pasted data"}</b>
              {files.length > 0 && <span className="text-muted">({fmtBytes(files.reduce((a, f) => a + f.size, 0))})</span>}
              <span className="text-muted">· change your choices freely, then press Next.</span>
            </div>
          )}
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-muted">
              {unclassified.length ? `Not chosen: ${unclassified.join(", ")}. We'll guess these from your data.` : "All set."}
            </p>
            <button className="btn-primary rounded-xl px-5 py-2.5 font-medium" onClick={() => setStep(2)}>
              Next: add your data →
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-5">
          {restored && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--accent)] bg-accent-wash px-4 py-3 text-sm">
              <span className="flex items-center gap-2 text-ink">
                <HardDrive className="h-4 w-4 text-accent" aria-hidden />
                We kept <b>{restored}</b> from last time on this computer.
              </span>
              <button className="inline-flex items-center gap-1 text-ink-2 hover:text-ink" onClick={forgetFile}>
                <X className="h-4 w-4" /> Remove
              </button>
            </div>
          )}
          {cacheNote === "too-big" && (
            <p className="text-xs text-muted">This file is larger than {fmtBytes(DRAFT_LIMIT)}, so it isn't kept if you leave the page. Going back a step still keeps it.</p>
          )}
          <Section title="Add your data">
            <div role="tablist" className="mb-4 inline-flex rounded-xl border border-line bg-surface-2 p-1">
              {([["file", "Upload a file", FileUp], ["paste", "Paste data", ClipboardList], ["sample", "Try a sample", FlaskConical]] as const).map(([m, label, Icon]) => (
                <button key={m} role="tab" aria-selected={mode === m} onClick={() => { setMode(m); setDet(null); setFiles([]); }}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium ${mode === m ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink"}`}>
                  <Icon className="h-4 w-4" aria-hidden /> {label}
                </button>
              ))}
            </div>

            {mode === "file" && (
              <div
                onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); read([...e.dataTransfer.files]); }}
                onClick={() => !ro && input.current?.click()}
                className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center ${drag ? "border-[var(--accent)] bg-accent-wash" : "border-line hover:bg-surface-2"}`}
              >
                <UploadIcon className="mx-auto h-10 w-10 text-accent" aria-hidden />
                <p className="mt-3 font-medium text-ink">Drag a file here, or click to choose</p>
                <p className="mt-1 text-sm text-ink-2">CSV, Excel, JSON, SQLite, Parquet or a .zip of several files</p>
                <input ref={input} type="file" multiple className="hidden"
                  accept=".zip,.csv,.xlsx,.xlsm,.json,.jsonl,.sqlite,.sqlite3,.db,.duckdb,.parquet"
                  onChange={(e) => read([...(e.target.files ?? [])])} />
                {files.length > 0 && <p className="mt-3 text-sm text-ink">{files.map((f) => f.name).join(", ")}</p>}
              </div>
            )}

            {mode === "paste" && (
              <div>
                <textarea value={text} onChange={(e) => setText(e.target.value)} rows={9} spellCheck={false}
                  placeholder={"timestamp,severity,alert name,host\n2026-06-01 10:00,high,Malware detected,web01\n2026-06-01 10:20,low,Port scan,fw01"}
                  aria-label="Paste CSV or JSON data"
                  className="w-full rounded-xl border border-line bg-surface-2 p-3 font-mono text-sm text-ink placeholder:text-muted" />
                <div className="mt-2 flex items-center justify-between gap-3">
                  <p className="text-sm text-muted">A header row, then one alert per line. Copying cells from Excel also works.</p>
                  <button className="rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-2 disabled:opacity-50"
                    disabled={text.trim().split("\n").length < 2} onClick={() => read(fromPaste())}>Check my data</button>
                </div>
              </div>
            )}

            {mode === "sample" && (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {SAMPLES.map((s) => (
                  <Choice key={s.file} selected={files[0]?.name === s.file} onClick={() => loadSample(s.file)}>
                    <div className="flex gap-3">
                      <s.Icon className="h-6 w-6 shrink-0 text-accent" aria-hidden />
                      <div>
                        <div className="font-medium text-ink">{s.label}</div>
                        <div className="text-sm text-ink-2">{s.hint}</div>
                      </div>
                    </div>
                  </Choice>
                ))}
              </div>
            )}

            {busy === "reading" && (
              <p className="mt-4 flex items-center gap-2 text-sm text-ink-2"><Loader2 className="h-4 w-4 animate-spin" /> Reading your data…</p>
            )}
            {error && <div className="mt-4"><ErrorBox error={error instanceof ApiError ? error : new Error(String(error))} /></div>}
          </Section>

          {det && (
            <Section title="Here's what we see in your data" help={`${det.rows.toLocaleString()} rows. Nothing has been saved yet.`}>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {([["Type of data", "data_type", dataType], ["Sector", "sector", sector], ["Size", "size", size]] as const).map(([label, k, chosen]) => {
                  const g = det[k];
                  return (
                    <div key={k} className="rounded-xl border border-line p-3">
                      <div className="text-xs text-muted">{label}</div>
                      {chosen ? (
                        <>
                          <div className="mt-0.5 font-semibold text-ink">{chosen.replace("_", " ").replace(/^\w/, (c) => c.toUpperCase())} <span className="text-xs font-normal text-muted">(your choice)</span></div>
                          {chosen !== g.value && g.confidence !== "low" && (
                            <p className="mt-1 text-xs text-ink-2">The data looks more like <b>{g.label}</b>.</p>
                          )}
                        </>
                      ) : (
                        <>
                          <div className="mt-0.5 font-semibold text-ink">{g.label} <span className="text-xs font-normal text-muted">({CONF[g.confidence]})</span></div>
                          <p className="mt-1 text-xs text-ink-2">Because {g.reasons[0]}</p>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
              {unclassified.length > 0 && (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--st-warning)] bg-[color-mix(in_srgb,var(--st-warning)_10%,transparent)] p-3 text-sm">
                  <span className="flex items-center gap-2 text-ink">
                    <HelpCircle className="h-5 w-5" style={{ color: "var(--st-warning)" }} aria-hidden />
                    Please classify your input for a better result. You haven't chosen the {unclassified.join(", ")}.
                  </span>
                  <span className="flex gap-2">
                    <button className="rounded-lg border border-line bg-surface px-3 py-1.5 font-medium text-ink hover:bg-surface-2" onClick={useGuesses}>Use these guesses</button>
                    <button className="rounded-lg border border-line bg-surface px-3 py-1.5 font-medium text-ink hover:bg-surface-2" onClick={() => setStep(1)}>Choose myself</button>
                  </span>
                </div>
              )}
              {det.preview.length > 0 && (
                <div className="mt-4 overflow-x-auto">
                  <p className="mb-1 text-xs text-muted">First rows. Columns we recognised are marked with what they mean.</p>
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-line text-left">
                        {Object.keys(det.preview[0]).map((c) => (
                          <th key={c} className="whitespace-nowrap px-2 py-1.5 font-medium text-ink">
                            {c}
                            {det.mapping[c] && <span className="ml-1 rounded bg-accent-wash px-1 py-0.5 text-[10px] font-normal text-accent">{det.mapping[c].replace("_", " ")}</span>}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {det.preview.map((r, i) => (
                        <tr key={i} className="border-b border-line last:border-0">
                          {Object.values(r).map((v, j) => <td key={j} className="max-w-[14rem] truncate px-2 py-1.5 text-ink-2">{v}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {det.data_type.value !== "full" && (
                <p className="mt-3 text-xs text-muted">
                  Tip: a full export (alerts + cases + escalations + assets + logs) unlocks every check, including closure speed, escalation and blind spots.
                </p>
              )}
            </Section>
          )}

          <div className="flex items-center justify-between gap-3">
            <button className="rounded-xl border border-line bg-surface px-4 py-2.5 font-medium text-ink hover:bg-surface-2" onClick={() => setStep(1)}>← Back</button>
            <button className="btn-primary inline-flex items-center gap-2 rounded-xl px-5 py-2.5 font-medium disabled:opacity-50"
              disabled={!!busy || ro || (!det && !(mode === "paste" && text.trim().split("\n").length >= 2))} onClick={analyse}>
              {busy === "analysing" ? <><Loader2 className="h-4 w-4 animate-spin" /> Analysing… (up to a minute)</> : "Analyse my data →"}
            </button>
          </div>
        </div>
      )}

      {step === 3 && result && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-ink-2">
              Report for <b className="text-ink">{org.trim() || result.entity_ids.join(", ")}</b> ·{" "}
              {(result.row_counts.alerts ?? 0).toLocaleString()} alerts
              {result.row_counts.cases ? `, ${result.row_counts.cases.toLocaleString()} cases` : ""} analysed
            </p>
            <ReportActions ids={result.entity_ids} onAnother={reset} saved={saved} />
          </div>
          <p className="print-only text-xs text-muted">SOCAssess report · {new Date().toLocaleString()} · analysis run {result.analysis_run_id}</p>
          <Report ids={result.entity_ids} snapshot={snapshot ?? undefined} checks={checks.length === ALL_CHECKS.length ? undefined : checks}
            note={<ClassifyNote classification={result.classification} auto={result.auto_classified} />} />
          <div className="no-print flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-surface p-4">
            <p className="text-sm text-ink-2">Done with this report?</p>
            <ReportActions ids={result.entity_ids} onAnother={reset} saved={saved} />
          </div>
          <details className="no-print rounded-xl border border-line bg-surface p-4 text-sm">
            <summary className="cursor-pointer font-medium text-ink">How your data was read</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-ink-2">
              {result.warnings.map((w) => <li key={w}>{w.replace(/^auto-mapping: /, "")}</li>)}
            </ul>
          </details>
        </div>
      )}
    </div>
  );
}
