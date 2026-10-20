/* Response shapes of the FastAPI backend (app/server.py). Only the fields the UI reads are named; the backend is the
   source of truth and every object may carry more keys (index signatures). Values are rendered as-is, never recomputed. */
/* eslint-disable @typescript-eslint/no-explicit-any */
type Open = { [k: string]: any };

export type Metric = Open & { label: string; value: number | null; unit: string; version: string; approximate: boolean; note: string };
export type Funnel = Open & { LF1: number; LF2: number; LF3: number; LF4: number; LF5: number; LF6: number };
export type Score = Open & { value: number | null; state: string; reason: string; interim_index: number | null; pillars: Record<string, number | null>; weights: Record<string, number> };
export type Alert = Open & { severity: string; metric: string; text: string };
export type State = Open & {
  dataset: string; dataset_label: string; label: string; data_as_of: string; period: string;
  metrics: Record<string, Metric>; score: Score; funnel: Funnel; paid_unused: number;
  renewal: Open & { outcome: string; why: string; evidence: Record<string, string> };
  users: Open & { vendor_mau_proxy: number; mau_overstatement: number };
  grouping: Open; quality: Open & { issues: string[] }; regions: Open[]; agents: Open[]; alerts: Alert[];
};
export type Scenario = Open & { key: string; label: string; note: string };
export type Personas = Record<string, string>;
export type Citation = Open & { metric: string; version: string; data_as_of?: string };
export type Answer = Open & {
  type: string; text: string; intent?: string; mode: string; brain?: string; persona?: string; citations: Citation[]; data_as_of: string;
  sql?: string; sql_executed?: boolean; row_count?: number; latency_ms?: number; confidence?: number; confidence_basis?: string;
  safe_alternative?: string; suggestions?: string[]; options?: { label: string; q: string }[]; followup?: Open & { interpreted_as: string };
  answered_by?: string; remote_fallback?: string; error?: boolean;
};
export type AskBody = { question: string; persona?: string | null; session_id?: string | null; previous?: string | null };
export type FeedbackBody = { question: string; answer?: string; rating: string; brain?: string; mode?: string; intent?: string; type?: string; persona?: string; comment?: string };
export type Lineage = Open & { metric: string; name: string; value: number | null; unit: string; version: string; formula: string; owner: string; sql?: string | null };
export type Brain = Open & { kind: string; label: string; ollama_host: string; ollama_model: string; ft_chain?: Open };
export type Health = Open & { ok: boolean; version: string; dataset: string };
export type ModelsOverview = Open & { brains: Open[]; uploaded: Open[]; metrics_help: Record<string, string> };
export type AuditRow = { ts: string; dataset: string; persona: string; question: string; type: string; intent: string; metrics: string; mode: string };
export type CompareRow = Open & { key: string; label: string; outcome: string };
export type Reclaim = Open & { rows: Open[]; purchased: number; reclaimable: number };
export type Reconcile = Open & { totals: Open; rows: Open[]; label: string };
export type WhatIfBody = { seats?: number | null; connector_fix?: boolean; id_coverage?: number | null };
export type WhatIfResult = Open & { before: Open; after: Open; label: string };
export type CostMeta = Open & { defaults: Open; models: Record<string, string>; assumptions: Open[]; sources: Record<string, Open> };
export type CostBody = { users?: number | null; queries_per_user_day?: number | null; rules_share?: number | null; model?: string | null; tokens_in?: number | null; tokens_out?: number | null };
export type CostResult = Open;
