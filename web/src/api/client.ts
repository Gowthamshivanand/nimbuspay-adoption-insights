/* Typed client: one function per backend endpoint (app/server.py). Every screen gets its data only through here.
   Same requests as the v1 UI (method, path, body). Errors throw Error(detail) exactly like v1's api() helper.
   Figma Make components can import these functions directly (drop-in for a Make `src/api/client.ts`). */
import type * as T from "./types";
export type * from "./types";

export async function request<R = unknown>(path: string, opts?: RequestInit): Promise<R> {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
const post = <R>(path: string, body?: unknown) =>
  request<R>(path, body === undefined ? { method: "POST" } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const postForm = <R>(path: string, form: FormData) => request<R>(path, { method: "POST", body: form });

// Status
export const getHealth = () => request<T.Health>("/api/health");
export const getBrain = (refresh = false) => request<T.Brain>(refresh ? "/api/brain?refresh=true" : "/api/brain");
export const getPersonas = () => request<T.Personas>("/api/personas");
// Data sets
export const getScenarios = () => request<T.Scenario[]>("/api/scenarios");
export const getState = () => request<T.State>("/api/state");
export const loadScenario = (key: string) => post<T.State>("/api/load/" + key);
export const uploadCsvs = (form: FormData) => postForm<T.State>("/api/upload", form);   // events, seats, registry + optional outcome fields
export const sampleCsvUrl = (key: string, name: "events.csv" | "seats.csv" | "registry.csv" | "outcomes.json") => `/api/sample/${key}/${name}`;
export const getCompare = () => request<T.CompareRow[]>("/api/compare");
// Agent
export const ask = (body: T.AskBody) => post<T.Answer>("/api/ask", body);
export const askStream = (body: T.AskBody) =>        // server-sent events: meta, token..., done (parsed by the caller)
  fetch("/api/ask/stream", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const endSession = (sid: string) => request<{ ok: boolean }>("/api/session/" + sid, { method: "DELETE" });
export const sendFeedback = (body: T.FeedbackBody) => post<{ ok: boolean; id: string }>("/api/feedback", body);
export const getFeedback = () => request<unknown>("/api/feedback");
export const getLineage = (mid: string) => request<T.Lineage>("/api/lineage/" + mid);
export const getAudit = (limit?: number) => request<T.AuditRow[]>(limit === undefined ? "/api/audit" : "/api/audit?limit=" + limit);
// Seats, bill, what-if
export const getReclaim = () => request<T.Reclaim>("/api/reclaim");
export const reconcile = (form: FormData) => postForm<T.Reconcile>("/api/reconcile", form);   // field: invoice
export const reconcileSample = () => request<T.Reconcile>("/api/reconcile/sample");
export const reconcileSampleCsvUrl = "/api/reconcile/sample.csv";
export const whatIf = (body: T.WhatIfBody) => post<T.WhatIfResult>("/api/whatif", body);
// Reporting
export const boardpackUrl = (format: "html" | "md") => "/api/boardpack?format=" + format;
// Cost and models
export const getCostMeta = () => request<T.CostMeta>("/api/cost");
export const calcCost = (body: T.CostBody) => post<T.CostResult>("/api/cost", body);
export const getModels = () => request<T.ModelsOverview>("/api/models");
export const runModel = (key: string) => post<unknown>("/api/models/run/" + key);
export const uploadModelEval = (form: FormData) => postForm<unknown>("/api/models/upload", form);   // field: file
