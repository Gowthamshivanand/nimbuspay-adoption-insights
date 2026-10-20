/* Formatting rules copied 1:1 from the legacy UI so every number renders identically. */
export const fmt = (v: unknown, u?: string) => (v === null || v === undefined ? "withheld" : String(v) + (u === "%" ? "%" : ""));
export const oc = (o: unknown) => "o-" + String(o).split(" ")[0];
export const money = (v: unknown) => "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
export const BRAIN: Record<string, string> = { rules: "Rules engine", ollama: "Open model (Ollama)", finetuned: "Fine-tuned model", openai: "Hosted LLM" };
export const TYPE: Record<string, string> = { refuse: "Refused", caveat: "Answer with caveat", clarify: "Clarifying question", answer: "Answer" };
export const ROLES = ["manager", "analyst", "guest"] as const;
export const cap = (r: string) => r[0].toUpperCase() + r.slice(1);

/* ---- Display-only copy helpers. They never change a number or the data, only how backend prose is shown. ---- */
export const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/* "1 unregistered agent(s)" -> "1 unregistered agent", "5 team(s)" -> "5 teams", "2 mismatch(es)" -> "2 mismatches". */
export const fixPlurals = (s: string) =>
  s.replace(/(\d+)((?:\s+[A-Za-z-]+)*?)\s+([A-Za-z]+)\((e?s)\)/g, (_m, n, mid, w, suf) => `${n}${mid} ${w}${Number(n) === 1 ? "" : suf}`);

/* Hide internal host strings ("... at http://127.0.0.1:9") in prose; the full text stays in a tooltip. */
export const hideHosts = (s: string) => s.replace(/\s+at\s+https?:\/\/\S+/g, "").replace(/\s*\(?https?:\/\/(?:127\.0\.0\.1|localhost)\S*\)?/g, "");

/* Drop internal file and slide references from product copy (repo paths, "slide 12"). */
export const hideRefs = (s: string) =>
  s.replace(/,?\s*same as (?:[\w.-]+\/)*[\w.-]+\.(?:md|py)/g, "")
   .replace(/\s*\((?:[\w.-]+\/)*[\w.-]+\.(?:md|py)\)/g, "")
   .replace(/\s*\([^()]*\bslide \d+[^()]*\)/g, "");

export const dashes = (s: string) => s.replace(/\bLF(\d)-LF(\d)\b/g, "LF$1\u2013LF$2");

/* Sentence case for "a; b" action text: "Do not renew x. Enable or reassign y". */
export const sentences = (s: string) => s.split(/;\s+/).map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(". ");

export const tidy = (s: unknown) => (s === null || s === undefined ? "" : dashes(fixPlurals(String(s))));

/* Timestamps: ISO with a zone -> "YYYY-MM-DD HH:MM UTC". Without a zone it is the server's local clock, so it is shown
   as "YYYY-MM-DD HH:MM" and labelled server time by the caller (never mislabelled as UTC). */
export function fmtTs(s: unknown): string {
  if (typeof s !== "string") return s === null || s === undefined ? "" : String(s);
  const m = s.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/);
  if (!m) return s;
  if (!m[3]) return `${m[1]} ${m[2]}`;
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

/* Human labels for the cost model's assumption keys (display only). */
const KEY_LABELS: Record<string, string> = {
  users: "Users", queries_per_user_day: "Questions per user per day", rules_share: "Share answered by rules", tokens_in: "Avg tokens in",
  tokens_out: "Avg tokens out", days_per_month: "Days per month", hours_per_month: "Hours per month", peak_hour_share: "Peak-hour share",
  target_utilisation: "Target host utilisation", min_instances: "Minimum model hosts", app_host: "App host", llm_p95: "LLM p95 latency",
  rules_p95_ms: "Rules engine p95 latency (ms)", production_model: "Production model", concurrency: "Concurrency per host",
};
export const keyLabel = (k: string) => KEY_LABELS[k] || (k.charAt(0).toUpperCase() + k.slice(1)).replace(/_/g, " ");
const SHARE_KEYS = new Set(["rules_share", "peak_hour_share", "target_utilisation"]);
/* 0.3 -> "30%" for share keys only (the same number, shown as a percentage). */
export const keyValue = (k: string, v: unknown) =>
  SHARE_KEYS.has(k) && typeof v === "number" ? `${Math.round(v * 1000) / 10}%` : String(v);

/* Typographic tidy for metric definitions: "<=" -> "≤", ">=" -> "≥", LF ranges with an en dash. */
export const symbols = (s: unknown) => dashes(String(s ?? "")).replace(/<=/g, "\u2264").replace(/>=/g, "\u2265");
/* Keep "(< 70.0%)" together: no break after "<" or ">". */
export const keepTogether = (s: unknown) => String(s ?? "").replace(/([<>\u2264\u2265]) (?=\d)/g, "$1\u00a0");
export const capFirst = (s: unknown) => { const t = String(s ?? ""); return t.charAt(0).toUpperCase() + t.slice(1); };
/* Cost notes: "ASSUMPTION: x" -> "Assumption: x", "MEASURED on" -> "Measured on" (sentence case, same words). */
export const sentenceTags = (s: unknown) => String(s ?? "").replace(/\bASSUMPTION\b/g, "Assumption").replace(/\bMEASURED\b/g, "Measured");
