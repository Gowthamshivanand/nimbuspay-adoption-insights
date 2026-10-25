/* App-wide state: the loaded dataset (ST), scenarios, current tab, persona and the agent chat. */
import { createContext, useContext } from "react";
import type { J } from "./api";
import type { TaskPlan } from "./tasks";

export type Tab = "data" | "exec" | "whatif" | "seats" | "region" | "eng" | "agent" | "alerts" | "compare" | "pack" | "audit" | "cost" | "models";

export const TABS: [Tab, string][] = [["data", "Data"], ["exec", "Executive"], ["whatif", "What-if"], ["seats", "Seats and bill"], ["region", "Regional"], ["eng", "Engineering"], ["agent", "Agent"], ["alerts", "Alerts"], ["compare", "Compare"], ["pack", "Board pack"], ["audit", "Audit log"], ["cost", "Cost and scale"], ["models", "Models"]];

/* Sidebar grouping is presentation only; order and labels are the legacy TABS. */
export const GROUPS: [string, Tab[]][] = [["Dataset", ["data"]], ["Insights", ["exec", "whatif", "seats", "region", "eng"]], ["Agent", ["agent", "alerts"]], ["Reporting", ["compare", "pack", "audit"]], ["Platform", ["cost", "models"]]];

export type ChatMsg = { me?: string; as?: string | null; bot?: J; streaming?: boolean; thought?: number; q?: string; persona?: string; fb?: string; fbErr?: string; plan?: TaskPlan };

export type Ctx = {
  ST: J; setST: (s: J) => void;
  SCEN: J[];
  tab: Tab; show: (t: Tab) => void;
  persona: string; personaLabel: string; personas: Record<string, string>; setPersona: (p: string) => void;
  chat: ChatMsg[]; redraw: () => void; clearChat: () => void;
  ask: (q: string, persona?: string) => void;
  explain: (mid: string) => void;
  why: (m: ChatMsg) => void;
  loadScenario: (k: string) => void;
  toast: (text: string) => void;
};

export const AppCtx = createContext<Ctx | null>(null);
export const useApp = () => useContext(AppCtx)!;
