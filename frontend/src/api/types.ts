export type GraphNodeName =
  | "ingest"
  | "calculate"
  | "evidence"
  | "analyze"
  | "render"
  | "quality"
  | "rework"
  | "human_review"
  | "finalize";
export type RunStatus =
  | "pending"
  | "running"
  | "paused"
  | "awaiting_human"
  | "approved"
  | "completed"
  | "error"
  | "rejected";
export interface TraceEventOut {
  node: string;
  timestamp: string;
  summary: string;
}
export interface InterruptPayload {
  kind: string;
  version?: number;
}
export interface Metric {
  id: string;
  label: string;
  dimension: string;
  cents: number;
  change: number | null;
  margin: number | null;
  target_rate: number | null;
  delivery_share: number | null;
  anomaly: boolean;
}
export interface Evidence {
  source_id: string;
  quote: string;
}
export interface Draft {
  summary: string;
  anomalies: {
    metric_id: string;
    reason: string;
    uncertain: boolean;
    evidence: Evidence[];
  }[];
  conflicts: string[];
  data_notes: string[];
  actions: string[];
  review_response: string;
}
export interface StateSnapshot {
  task_id?: string;
  status?: RunStatus;
  spec?: { title: string; year: number; week: number; focus: string };
  inputs?: { sales?: string; minutes?: string; master?: string | null };
  version?: number;
  current_node?: GraphNodeName;
  resume_node?: GraphNodeName;
  reason?: string;
  error_kind?: string;
  worker_active?: boolean;
  model?: string;
  total_model_calls?: number;
  total_active_seconds?: number;
  model_calls?: number;
  active_seconds?: number;
  limits?: Record<string, number>;
  sales?: {
    sheet: string;
    rows: number;
    raw_rows: number;
    removed_duplicates: number;
    mapping: Record<string, string>;
    date_start: string;
    date_end: string;
  };
  metrics?: {
    total: Metric;
    groups: Metric[];
    top_products: { product: string; cents: number }[];
    tokens: Record<string, string>;
    period: string;
    category_margins?: {
      region: string;
      category: string;
      margin: number;
      previous_margin: number;
    }[];
    anomalies: Metric[];
  };
  minutes?: { year?: number; week?: number; sources: { id: string; text: string }[] };
  draft?: Draft;
  report_quality_notes?: string[];
  feedback?: { reviewer: string; feedback: string; version: number }[];
  quality?: {
    passed: boolean;
    checks: { name: string; passed: boolean; details: string }[];
    page_audit?: { pages?: number; details: string };
  };
  artifact?: { file: string; artifact_id: string; sha256: string };
  delivery?: string;
  config_version?: string;
  import_options?: { sheet?: string; fields?: Record<string, string> };
  rework_plan?: {
    route: GraphNodeName;
    categories: string[];
    sections: string[];
    reasons: string[];
    version: number;
  };
  revision_items?: {
    id: string;
    text: string;
    categories: string[];
    sections: string[];
    status: string;
    response?: string;
    verification?: string;
    before: Record<string, unknown>;
    before_tokens?: Record<string, string>;
    after_tokens?: Record<string, string>;
    after?: Record<string, unknown>;
    changed_sections?: string[];
    requested_version: number;
    verified_version?: number;
  }[];
  revision_ledger?: {
    open_issues: string[];
    resolved_issues: string[];
    new_issues: string[];
  };
  work_items?: { id: string; label: string; kind: string }[];
}
export interface RunSummary {
  id: string;
  created: string;
  title: string;
  status: RunStatus;
  week: number;
}

export interface TaskFile {
  id: string;
  name: string;
  bytes: number;
  kind: "input" | "artifact";
  url: string;
}

export interface TaskEvent {
  seq: number;
  time: string;
  kind: string;
  payload: Record<string, unknown>;
}
