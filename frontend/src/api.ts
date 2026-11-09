// Typed client for the SOCAssess API. In dev, Vite proxies /api; in production set VITE_API_BASE.
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

export type Severity = "low" | "medium" | "high" | "critical";

export interface BreakdownItem {
  finding_id: string;
  type: string;
  severity: Severity;
  title: string;
  weight: number;
  multiplier: number;
  points: number;
}

export interface EntityScore {
  entity_id: string;
  name: string;
  sector: string;
  size: string;
  source: string;
  risk_score: number;
  raw_points: number;
  band: Severity;
  rank: number;
  n_findings: number;
  has_case_data: boolean;
  anomaly_score: number | null;
  breakdown: BreakdownItem[];
}

export interface Finding {
  finding_id: string;
  entity_id: string;
  type: string;
  category: string;
  severity: Severity;
  title: string;
  rationale: string;
  evidence_kind: string;
  n_evidence: number;
  metric_values: Record<string, unknown>;
  detector: string;
  points: number;
}

export interface Benchmark {
  entity_id: string;
  metric: string;
  description: string;
  direction: number;
  value: number;
  peer_median_all: number | null;
  peer_median_size: number | null;
  size_peers: string[];
  percentile: number;
  z: number;
  n_peers: number;
}

export interface EntityDetail {
  run_id: string;
  entity: Record<string, string | null>;
  score: EntityScore;
  counts: Record<string, number | string | null>;
  findings: Finding[];
  benchmarks: Benchmark[];
  categories: { category: string; alerts: number }[];
  peer_values: Record<string, number[]>;
}

export type EvidenceRecord = Record<string, unknown> & { record_type: string; record_id: string };

export interface Evidence {
  total: number;
  offset: number;
  records: EvidenceRecord[];
}

export interface Cluster {
  cluster_id: number;
  label: string;
  patterns: number;
  alerts: number;
  n_entities: number;
  entities: string[];
  cross_entity: boolean;
  main_category: string;
  categories: Record<string, number>;
  top_rules: Record<string, number>;
  profile: Record<string, number>;
}

export interface Pattern {
  entity_id: string;
  rule_name: string;
  category: string;
  alerts: number;
  assets: number;
  active_days: number;
  after_hours_share: number;
  severity_mean: number;
  burstiness: number;
  asset_spread: number;
  first_seen: string;
  last_seen: string;
  cluster_id: number;
}

export interface Week {
  entity_id: string;
  week: string;
  alerts: number;
  high_critical: number;
  cases_closed: number | null;
  median_ttc_hours: number | null;
  fast_closures: number | null;
  sla_breaches: number | null;
  escalated: number | null;
}

export interface QueueItem {
  rank: number;
  entity_id: string;
  entity_name: string;
  finding_id: string | null;
  finding_title: string | null;
  finding_type: string;
  severity: Severity;
  record_type: string;
  record_id: string;
  reason: string;
  priority: number;
}

export interface Run {
  run_id: string;
  started_at: string;
  duration_s: number;
  input_hash: string;
  params_hash: string;
  code_version: string;
  entity_ids: string[];
  n_findings: number;
  detector_errors: Record<string, string>;
  trigger: string;
  params?: Record<string, unknown>;
}

export interface Health {
  status: string;
  version: string;
  read_only: boolean;
  public_demo?: boolean;
  max_upload_mb?: number;
  latest_run: string | null;
  entities: number;
}

export interface Summary {
  run: Run;
  entity_ids: string[];
  bands: { band: Severity; n: number }[];
  by_type: { type: string; category: string; n: number; points: number }[];
  by_severity: { severity: Severity; n: number }[];
  by_category: { category: string; n: number; points: number }[];
  alert_severity: { severity: Severity; n: number }[];
  alert_category: { category: string; n: number }[];
  totals: Record<string, number>;
}

export interface Guess {
  value: string;
  label: string;
  confidence: "high" | "medium" | "low" | "user";
  reasons: string[];
  source?: "user" | "auto";
}

export interface Detection {
  data_type: Guess;
  sector: Guess;
  size: Guess;
  rows: number;
  tables: Record<string, number>;
  columns: string[];
  mapping: Record<string, string>;
  missing_for_full: string[];
  preview: Record<string, string>[];
}

export interface Classification {
  data_type?: string;
  sector?: string;
  size?: string;
}

export interface UploadResult {
  run_id: string;
  entity_ids: string[];
  row_counts: Record<string, number>;
  warnings: string[];
  analysis_run_id?: string;
  classification: Record<"data_type" | "sector" | "size", Guess>;
  auto_classified: string[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public errors: string[] = []) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, init);
  } catch {
    throw new ApiError(0, "Cannot reach the SOCAssess API. Is the backend running?");
  }
  if (!res.ok) {
    let body: { message?: string; errors?: string[] } = {};
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, body.message ?? `Request failed (${res.status})`, body.errors ?? []);
  }
  return res.json() as Promise<T>;
}

const qs = (p: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const t = s.toString();
  return t ? `?${t}` : "";
};

export const api = {
  health: () => request<Health>("/api/health"),
  summary: (entityIds: string[] = []) =>
    request<Summary>(`/api/summary${qs({ entity_id: entityIds.join(",") })}`),
  entities: () => request<{ run_id: string; entities: EntityScore[] }>("/api/entities"),
  entity: (id: string) => request<EntityDetail>(`/api/entities/${encodeURIComponent(id)}`),
  heatmap: () =>
    request<{
      run_id: string;
      entities: { entity_id: string; name: string; risk_score: number; rank: number }[];
      types: string[];
      cells: { entity_id: string; type: string; points: number; findings: number; severity: Severity }[];
    }>("/api/heatmap"),
  findings: (p: { entity_id?: string; type?: string; severity?: string; category?: string; limit?: number } = {}) =>
    request<{ run_id: string; total: number; findings: Finding[] }>(`/api/findings${qs(p)}`),
  finding: (id: string, offset = 0, limit = 50) =>
    request<{ run_id: string; finding: Finding; evidence: Evidence }>(
      `/api/findings/${encodeURIComponent(id)}${qs({ offset, limit })}`,
    ),
  evidence: (id: string, offset = 0, limit = 50) =>
    request<Evidence>(`/api/findings/${encodeURIComponent(id)}/evidence${qs({ offset, limit })}`),
  record: (kind: string, id: string) =>
    request<Record<string, unknown>>(`/api/records/${kind}/${encodeURIComponent(id)}`),
  clusters: () =>
    request<{ run_id: string; clusters: Cluster[]; unclustered: { patterns: number; alerts: number } }>(
      "/api/clusters",
    ),
  cluster: (id: number) => request<Cluster & { patterns: Pattern[] }>(`/api/clusters/${id}`),
  trends: (entityIds: string[]) =>
    request<{ run_id: string; weeks: Week[] }>(`/api/trends${qs({ entity_id: entityIds.join(",") })}`),
  queue: (p: { entity_id?: string; include_spot_checks?: boolean; limit?: number; offset?: number } = {}) =>
    request<{ run_id: string; total: number; items: QueueItem[] }>(`/api/review-queue${qs(p)}`),
  runs: () => request<Run[]>("/api/runs"),
  run: (id: string) => request<Run>(`/api/runs/${id}`),
  ingestions: () => request<Record<string, unknown>[]>("/api/ingestions"),
  runAnalysis: (params: Record<string, unknown> = {}) =>
    request<{ run_id: string; duration_s: number; n_findings: number; detector_errors: Record<string, string> }>(
      "/api/analysis/run",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ params }) },
    ),
  upload: (files: File[], analyse = true, entityName?: string, cls: Classification = {}) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return request<UploadResult>(
      `/api/ingest${qs({ analyse, entity_name: entityName, sector: cls.sector, size: cls.size, data_type: cls.data_type })}`,
      { method: "POST", body: fd },
    );
  },
  detect: (files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return request<Detection>("/api/detect", { method: "POST", body: fd });
  },
  reportUrl: (path: string) => `${API_BASE}/api/reports/${path}`,
};
