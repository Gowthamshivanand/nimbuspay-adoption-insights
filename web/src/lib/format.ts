/* Formatting rules copied 1:1 from the legacy UI so every number renders identically. */
export const fmt = (v: unknown, u?: string) => (v === null || v === undefined ? "withheld" : String(v) + (u === "%" ? "%" : ""));
export const oc = (o: unknown) => "o-" + String(o).split(" ")[0];
export const money = (v: unknown) => "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
export const BRAIN: Record<string, string> = { rules: "Rules engine", ollama: "Open model (Ollama)", finetuned: "Fine-tuned model", openai: "Hosted LLM" };
export const TYPE: Record<string, string> = { refuse: "Refused", caveat: "Answer with caveat", clarify: "Clarifying question", answer: "Answer" };
export const ROLES = ["manager", "analyst", "guest"] as const;
export const cap = (r: string) => r[0].toUpperCase() + r.slice(1);
