/* NimbusPay Adoption Insights UI (v2). Talks to the same FastAPI backend as the legacy UI; all data synthetic.
   Behaviour is a 1:1 port of app/static/app.js: same tabs, controls, requests, numbers and data-testids. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import * as C from "./api/client";
import type { J } from "./lib/api";
import { AppCtx, GROUPS, TABS, type ChatMsg, type Ctx, type Tab } from "./lib/store";
import { LineageModal, WhyModal } from "./components/Explain";
import { cap } from "./lib/format";
import Data from "./pages/Data";
import Exec from "./pages/Exec";
import WhatIf from "./pages/WhatIf";
import Seats from "./pages/Seats";
import Region from "./pages/Region";
import Eng from "./pages/Eng";
import Agent from "./pages/Agent";
import Alerts from "./pages/Alerts";
import Compare from "./pages/Compare";
import Pack from "./pages/Pack";
import Audit from "./pages/Audit";
import Cost from "./pages/Cost";
import Models from "./pages/Models";

const SCREENS: Record<Tab, () => JSX.Element | null> = { data: Data, exec: Exec, whatif: WhatIf, seats: Seats, region: Region, eng: Eng, agent: Agent, alerts: Alerts, compare: Compare, pack: Pack, audit: Audit, cost: Cost, models: Models };
const LABEL = Object.fromEntries(TABS) as Record<Tab, string>;
const SEGMENTS = ["executive", "manager", "analyst", "guest"];
const SID = "s-" + ((window.crypto && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));

export default function App() {
  const [personas, setPersonas] = useState<Record<string, string> | null>(null);
  const [persona, setPersonaRaw] = useState("");
  const [SCEN, setSCEN] = useState<J[]>([]);
  const [ST, setST] = useState<J>(null);
  const nav = useNavigate(), loc = useLocation();
  const tab = ((loc.pathname.slice(1) || "data") in SCREENS ? (loc.pathname.slice(1) || "data") : "data") as Tab;
  const [, setV] = useState(0);
  const chatRef = useRef<ChatMsg[]>([]);
  const tabRef = useRef<Tab>("data"), personaRef = useRef(""), stRef = useRef<J>(null);
  const [lin, setLin] = useState<J>(null);
  const [whyM, setWhyM] = useState<{ m: ChatMsg; L: (J | null)[] } | null>(null);

  const redraw = useCallback(() => setV((v) => v + 1), []);
  /* Every show() is a new navigation (new location.key), so the page re-mounts and re-fetches, exactly as v1 re-ran R[t](). */
  const navRef = useRef(nav); navRef.current = nav;     // useNavigate changes identity per location; keep show() stable
  const show = useCallback((t: Tab) => { tabRef.current = t; navRef.current("/" + t); }, []);
  const setPersona = useCallback((p: string) => { personaRef.current = p; setPersonaRaw(p); }, []);
  const setSTx = useCallback((s: J) => { stRef.current = s; setST(s); }, []);

  useEffect(() => {
    (async () => {
      const ps = await C.getPersonas();
      setPersonas(ps); setPersona(Object.keys(ps)[0] || "");
      setSCEN(await C.getScenarios()); setSTx(await C.getState()); show("data");
    })();
  }, [setPersona, setSTx, show]);

  /* Explain this number: any [data-metric=M\d\d] click, anywhere (KPI tiles). */
  const explain = useCallback(async (mid: string) => {
    let L; try { L = await C.getLineage(mid); } catch { return; }
    setLin(L);
  }, []);
  useEffect(() => {
    const h = (e: MouseEvent) => { const k = (e.target as HTMLElement).closest?.("[data-metric]") as HTMLElement | null; if (k && /^M\d\d$/.test(k.dataset.metric || "")) explain(k.dataset.metric!); };
    document.addEventListener("click", h); return () => document.removeEventListener("click", h);
  }, [explain]);

  const why = useCallback(async (m: ChatMsg) => {
    const b = m.bot, ids = [...new Set<string>((b.citations || []).map((c: J) => c.metric))];
    const L = await Promise.all(ids.map((id) => (/^M\d\d$/.test(id) ? C.getLineage(id).catch(() => null) : Promise.resolve(null))));
    setWhyM({ m, L });
  }, []);

  /* Ask: stream (SSE over fetch) with a graceful fallback to /api/ask; never leaves a frozen bubble. */
  const ask = useCallback(async (q: string, as?: string) => {
    if (tabRef.current !== "agent") show("agent");
    const persona = as || personaRef.current, CHAT = chatRef.current, ST = stRef.current;
    CHAT.push({ me: q, as: persona !== personaRef.current ? persona : null });
    const m: ChatMsg = { bot: { type: "answer", text: "", citations: [], mode: "...", data_as_of: ST.data_as_of }, streaming: true, q, persona };
    CHAT.push(m); redraw();
    const body = { question: q, persona, session_id: SID };
    try {
      const res = await C.askStream(body);
      if (!res.ok || !res.body) throw new Error("no stream");
      const rd = res.body.getReader(), dec = new TextDecoder(); let buf = "", done: J = null;
      for (;;) {
        const { value, done: end } = await rd.read(); if (end) break;
        buf += dec.decode(value, { stream: true }); let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const blk = buf.slice(0, i); buf = buf.slice(i + 2);
          const ev = (blk.match(/^event: (.*)$/m) || [])[1], data = JSON.parse((blk.match(/^data: (.*)$/m) || [, "null"])[1]!);
          if (ev === "meta") { Object.assign(m.bot, data); redraw(); }
          else if (ev === "token") { m.bot.text += data; redraw(); }
          else if (ev === "done") done = data;
        }
      }
      if (!done) throw new Error("stream ended early");
      m.bot = done;
    } catch {
      try { m.bot = await C.ask(body); }
      catch (e2) {
        m.bot = { type: "caveat", intent: "error", error: true, mode: "error", brain: "rules", citations: [], data_as_of: ST.data_as_of,
          text: "The service didn't answer (" + ((e2 as Error).message || "network error") + "), so there is no answer and no number to show. Please ask again; if it repeats, restart the app." };
      }
    }
    m.streaming = false; redraw();
  }, [redraw, show]);

  const personaLabel = personas ? personas[persona] ?? "" : "";
  const ctx: Ctx = useMemo(() => ({
    ST, setST: setSTx, SCEN, tab, show, persona, personaLabel, personas: personas || {}, setPersona,
    chat: chatRef.current, redraw, clearChat: () => { chatRef.current.length = 0; }, ask, explain, why,
  }), [ST, setSTx, SCEN, tab, show, persona, personaLabel, personas, setPersona, redraw, ask, explain, why]);

  return (
    <AppCtx.Provider value={ctx}>
      <div className="min-h-screen flex flex-col">
        <header className="flex justify-between items-center gap-3 flex-wrap px-6 py-3 border-b border-line bg-canvas z-40">
          <div className="flex items-center gap-3 text-[15px]">
            <span className="w-2 h-2 rounded-full bg-accentFill" aria-hidden="true"></span>
            <span><b className="font-semibold text-navy">NimbusPay</b> Adoption Insights</span>
            <span className="tag !mr-0 border border-line bg-canvas max-[479px]:hidden">live product</span>
            <span className="tag !mr-0 border border-accent bg-canvas text-accent font-semibold">SYNTHETIC DATA</span>
          </div>
          <div className="flex items-center gap-x-4 gap-y-2 flex-wrap min-w-0 max-w-full">
            {/* One role control: four segments plus "More roles" for the other personas. Same testids and behaviour as v1. */}
            <div className="roles flex items-center gap-2 min-w-0 max-w-full" data-testid="role-switch" title="Role switch: scope is enforced on the server, the UI only sends the role name">
              <span className="eyebrow max-sm:hidden">Role</span>
              <div className="inline-flex items-center gap-0.5 rounded-control border border-lineStrong p-0.5 bg-surface max-w-full overflow-x-auto">
                {SEGMENTS.map((r) => (
                  <button key={r} type="button" data-role={r} data-testid={`role-${r}`} onClick={() => setPersona(r)} aria-pressed={persona === r}
                    className={`role px-2 sm:px-3 py-1 min-h-[44px] sm:min-h-0 rounded-[6px] text-[12px] sm:text-[13px] whitespace-nowrap transition-colors duration-fast ${persona === r ? (r === "guest" ? "on bg-critical text-white font-semibold" : "on bg-navy text-white font-semibold") : "text-ink hover:bg-canvas"}`}>{cap(r)}</button>
                ))}
                <select id="persona" data-testid="persona" aria-label="More roles" value={SEGMENTS.includes(persona) ? "" : persona} onChange={(e) => e.target.value && setPersona(e.target.value)}
                  className={`min-h-[44px] sm:min-h-0 !border-0 !rounded-[6px] !py-1 !pl-3 !pr-7 text-[12px] sm:text-[13px] max-w-[124px] sm:max-w-[190px] ${SEGMENTS.includes(persona) ? "!bg-transparent text-ink" : "on !bg-navy !text-white font-semibold"}`}>
                  <option value="" disabled>More roles</option>
                  {personas && Object.entries(personas).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
            </div>
            <span id="ds" className="muted text-[12px]">{ST ? <><span className="whitespace-nowrap max-sm:block">Dataset: {ST.dataset_label}</span><span className="max-sm:hidden"> | </span><span className="whitespace-nowrap max-sm:block">data as of {ST.data_as_of}</span></> : ""}</span>
          </div>
        </header>
        <div className="flex flex-1 flex-col lg:flex-row">
          {/* Full-height sidebar column; the nav inside it is sticky. Below lg: one horizontally scrolling row of tabs. */}
          <div className="lg:w-[200px] shrink-0 bg-surface border-b lg:border-b-0 lg:border-r border-line">
            <nav id="tabs" aria-label="Screens" className="px-3 py-2 lg:py-6 flex lg:flex-col gap-1 lg:gap-5 flex-nowrap overflow-x-auto lg:overflow-visible lg:sticky lg:top-0">
              {GROUPS.map(([g, ts]) => (
                <div key={g} className="flex lg:flex-col gap-0.5 flex-nowrap shrink-0">
                  <div className="eyebrow px-3 mb-1 hidden lg:block">{g}</div>
                  {ts.map((k) => (
                    <button key={k} data-tab={k} id={`tab-${k}`} onClick={() => show(k)} aria-current={tab === k ? "page" : undefined}
                      className={`text-left px-3 py-1.5 min-h-[44px] lg:min-h-0 whitespace-nowrap rounded-control text-[13px] transition-colors duration-fast ${tab === k ? "on bg-canvas text-ink font-semibold shadow-[inset_2px_0_0_theme(colors.accentFill)] border border-line" : "text-muted border border-transparent hover:text-ink"}`}>{LABEL[k]}</button>
                  ))}
                </div>
              ))}
            </nav>
          </div>
          <main id="view" className="flex-1 min-w-0 px-6 lg:px-10 py-8 max-w-[1200px]">
            {ST && personas ? (
              <Routes>
                {TABS.map(([k]) => { const Page = SCREENS[k]; return <Route key={k} path={"/" + k} element={<div className="screen" key={loc.key + (k === "agent" ? ":" + persona : "")}><Page /></div>} />; })}
                <Route path="*" element={<Navigate to="/data" replace />} />
              </Routes>
            ) : null}
          </main>
        </div>
        <footer className="muted px-6 py-5 text-[12px] text-center border-t border-line">Read-only. Every number is synthetic and labelled; thresholds and weights are placeholders to agree. Metric version <span id="ver">v1.0</span>. Built by Gowtham S.</footer>
      </div>
      {lin ? <LineageModal L={lin} onClose={() => setLin(null)} /> : null}
      {whyM ? <WhyModal m={whyM.m} L={whyM.L} ST={ST} onClose={() => setWhyM(null)} /> : null}
    </AppCtx.Provider>
  );
}
