/* NimbusPay Adoption Insights UI (v2). Talks to the same FastAPI backend as the legacy UI; all data synthetic.
   Behaviour is a 1:1 port of app/static/app.js: same tabs, controls, requests, numbers and data-testids. */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import * as C from "./api/client";
import type { J } from "./lib/api";
import { AppCtx, GROUPS, TABS, type ChatMsg, type Ctx, type Tab } from "./lib/store";
import { LineageModal, WhyModal } from "./components/Explain";
import { CommandBar, CopilotBar, ShortcutSheet, SignIn, Toasts } from "./components/chrome";
import { planFor } from "./lib/tasks";
import { cap } from "./lib/format";

function Glyph({ children }: { children: ReactNode }) {
  return (
    <svg className="nav-glyph" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

function DatasetIcon({ id }: { id: string }) {
  if (id === "healthy") return <Glyph><circle cx="8" cy="8" r="5.2" /><path d="M5.4 8.1 7.1 9.8 10.7 6.2" /></Glyph>;
  if (id === "overstated") return <Glyph><path d="M3 11.5 6.2 7l2.2 2.2L13 4.5" /><path d="M10 4.5h3V7.5" /></Glyph>;
  if (id === "shelfware") return <Glyph><rect x="3" y="4" width="10" height="8" rx="1.4" /><path d="M3 7h10" /></Glyph>;
  if (id === "newcountry") return <Glyph><circle cx="8" cy="8" r="5.2" /><path d="M3 8h10M8 2.8c1.4 1.5 1.4 7.4 0 10.4M8 2.8c-1.4 1.5-1.4 7.4 0 10.4" /></Glyph>;
  if (id === "incident") return <Glyph><path d="M8 3v5" /><path d="M8 11.2v.3" /></Glyph>;
  if (id === "noids") return <Glyph><circle cx="8" cy="8" r="5.2" /><path d="M4.6 4.6 11.4 11.4" /></Glyph>;
  if (id === "breach") return <Glyph><path d="M8 2.6 13 4.4v3.6c0 2.8-2 4.4-5 5.4-3-1-5-2.6-5-5.4V4.4z" /></Glyph>;
  return <Glyph><path d="M3 12V8M8 12V4.5M13 12V7" /></Glyph>;
}

function NavIcon({ id }: { id: string }) {
  if (id === "data") return <Glyph><rect x="3" y="3" width="10" height="10" rx="1.5" /><path d="M3 6.5h10M6.5 6.5V13" /></Glyph>;
  if (id === "exec") return <Glyph><path d="M3 12.2 6.2 8l2.2 2.1L13 4.6" /></Glyph>;
  if (id === "whatif") return <Glyph><circle cx="8" cy="8" r="2" /><path d="M8 2.8v1.6M8 11.6v1.6M2.8 8h1.6M11.6 8h1.6" /></Glyph>;
  if (id === "seats") return <Glyph><path d="M3.5 7.2h9v4.2h-9z" /><path d="M5.4 7.2V5.6a2.6 2.6 0 0 1 5.2 0v1.6" /></Glyph>;
  if (id === "region") return <Glyph><path d="M8 2.8a4.2 4.2 0 0 1 4.2 4.2c0 2.6-4.2 6.2-4.2 6.2S3.8 9.6 3.8 7A4.2 4.2 0 0 1 8 2.8z" /><circle cx="8" cy="7" r="1.1" /></Glyph>;
  if (id === "eng") return <Glyph><path d="M6.2 3.2 3.2 8h3.4L5.4 12.8 12.8 7.2H9.2z" /></Glyph>;
  if (id === "agent") return <Glyph><path d="M3 3.6h7.4a1.6 1.6 0 0 1 1.6 1.6v4.2L9.6 7.4H4.2A1.2 1.2 0 0 1 3 6.2V3.6z" /></Glyph>;
  if (id === "alerts") return <Glyph><path d="M8 2.8a3 3 0 0 1 3 3v2.1l.8 1.4H4.2L5 7.9V5.8a3 3 0 0 1 3-3z" /><path d="M6.7 11.4a1.3 1.3 0 0 0 2.6 0" /></Glyph>;
  if (id === "compare") return <Glyph><path d="M3.2 12.2V8.2M8 12.2V4.2M12.8 12.2V6.4" /></Glyph>;
  if (id === "pack") return <Glyph><path d="M3.2 4.4h9.6v8.2H3.2z" /><path d="M3.2 7.2h9.6" /></Glyph>;
  if (id === "audit") return <Glyph><path d="M4 3.2h5.2L12 6v6.8H4z" /><path d="M6 8.2h4M6 10.4h2.6" /></Glyph>;
  if (id === "cost") return <Glyph><path d="M4 11.4V8.4M8 11.4V5M12 11.4V7" /></Glyph>;
  return <Glyph><rect x="3" y="3" width="4" height="4" rx=".6" /><rect x="9" y="3" width="4" height="4" rx=".6" /><rect x="3" y="9" width="4" height="4" rx=".6" /><rect x="9" y="9" width="4" height="4" rx=".6" /></Glyph>;
}
import { Skeleton } from "./components/ui";
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
const SHORT: Record<string, string> = { baseline: "Baseline", breach: "Breach", healthy: "Healthy", incident: "Incident", newcountry: "New country", noids: "No IDs", overstated: "Overstated", shelfware: "Shelfware" };
const QA = typeof navigator !== "undefined" && navigator.webdriver;

function RoleSwitch({ persona, personas, onPick }: { persona: string; personas: Record<string, string> | null; onPick: (role: string) => void }) {
  return (
    <div className="role-switch" data-testid="role-switch" title="Role switch: scope is enforced on the server, the UI only sends the role name">
      {SEGMENTS.map((r) => (
        <button key={r} type="button" data-role={r} data-testid={`role-${r}`} aria-pressed={persona === r} onClick={() => onPick(r)} className={`role ${persona === r ? "on" : ""}`}>{cap(r)}</button>
      ))}
      <select id="persona" data-testid="persona" aria-label="More roles" value={SEGMENTS.includes(persona) ? "" : persona} onChange={(e) => { if (e.target.value) onPick(e.target.value); }} className={SEGMENTS.includes(persona) ? "" : "on"}>
        <option value="" disabled>More roles</option>
        {personas && Object.entries(personas).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
    </div>
  );
}

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
  const [drawer, setDrawer] = useState(false);
  const [railLock, setRailLock] = useState(false);
  const leftRail = useRef(true);
  const [theme, setTheme] = useState<"light" | "dark" | "system">(() => {
    const t = localStorage.getItem("np-theme");
    return t === "light" || t === "dark" ? t : "system";
  });
  const [cmd, setCmd] = useState(false);
  const [panel, setPanel] = useState(false);
  const [gate, setGate] = useState(() => {
    if (typeof navigator !== "undefined" && navigator.webdriver) return false;
    try { return sessionStorage.getItem("np-gate") !== "1"; } catch { return true; }
  });
  const [acct, setAcct] = useState(false);
  const [profile, setProfile] = useState(false);
  const enter = useCallback(() => {
    try { sessionStorage.setItem("np-gate", "1"); } catch { /* private mode */ }
    setGate(false);
  }, []);
  const [help, setHelp] = useState(false);
  const [toasts, setToasts] = useState<{ id: number; text: string }[]>([]);

  const redraw = useCallback(() => setV((v) => v + 1), []);
  const navRef = useRef(nav); navRef.current = nav;
  const show = useCallback((t: Tab) => { tabRef.current = t; navRef.current("/" + t); setDrawer(false); }, []);
  const setPersona = useCallback((p: string) => { personaRef.current = p; setPersonaRaw(p); }, []);
  const setSTx = useCallback((s: J) => { stRef.current = s; setST(s); }, []);
  const toast = useCallback((text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, text }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 2800);
  }, []);
  const signOut = useCallback(() => {
    try { sessionStorage.removeItem("np-gate"); } catch { /* private mode */ }
    setAcct(false);
    setGate(true);
    toast("Signed out");
  }, [toast]);

  const toggleTheme = useCallback(() => {
    const dark = document.documentElement.classList.contains("dark");
    const next = dark ? "light" : "dark";
    localStorage.setItem("np-theme", next);
    setTheme(next);
  }, []);

  useEffect(() => {
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
      document.documentElement.classList.toggle("dark", dark);
      document.documentElement.dataset.theme = dark ? "dark" : "light";
    };
    apply();
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  const loadScenario = useCallback(async (k: string) => {
    try {
      const s = await C.loadScenario(k);
      setSTx(s);
      chatRef.current.length = 0;
      show(tabRef.current === "data" ? "exec" : tabRef.current);
      toast(SHORT[k] || k);
    } catch (e) {
      console.error(e);
      toast("Couldn't load that preset");
    }
  }, [setSTx, show, toast]);

  useEffect(() => {
    (async () => {
      const ps = await C.getPersonas();
      setPersonas(ps); setPersona(Object.keys(ps)[0] || "");
      setSCEN(await C.getScenarios()); setSTx(await C.getState()); show("data");
    })();
  }, [setPersona, setSTx, show]);

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

  const ask = useCallback(async (q: string, as?: string, stay?: boolean) => {
    if (!stay && tabRef.current !== "agent") show("agent");
    const persona = as || personaRef.current, CHAT = chatRef.current, ST = stRef.current;
    CHAT.push({ me: q, as: persona !== personaRef.current ? persona : null });
    const m: ChatMsg = { bot: { type: "answer", text: "", citations: [], mode: "...", data_as_of: ST.data_as_of }, streaming: true, thought: 0, q, persona };
    CHAT.push(m); redraw();
    const showThought = typeof navigator === "undefined" || !navigator.webdriver;
    const pace = showThought
      ? (async () => {
          await new Promise((r) => setTimeout(r, 420));
          if (m.streaming && (m.thought ?? 0) < 1) { m.thought = 1; redraw(); }
          await new Promise((r) => setTimeout(r, 460));
          if (m.streaming && (m.thought ?? 0) < 2) { m.thought = 2; redraw(); }
        })()
      : Promise.resolve();
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
        toast("The agent didn't answer");
      }
    }
    if (showThought) await pace;
    m.thought = 3;
    m.streaming = false;
    if (m.bot && !m.bot.error) {
      const plan = planFor(q, m.bot.type, m.bot.text);
      if (plan) m.plan = plan;
    }
    redraw();
  }, [redraw, show, toast]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === "k") { e.preventDefault(); setCmd(true); return; }
      if (meta && e.key.toLowerCase() === "j") { e.preventDefault(); setPanel((v) => !v); return; }
      if (e.key === "Escape") { setCmd(false); setPanel(false); setHelp(false); setAcct(false); setProfile(false); setDrawer(false); return; }
      if (typing) return;
      if (e.key === "?") { e.preventDefault(); setHelp(true); return; }
      if (e.key.toLowerCase() === "t" && !meta) { e.preventDefault(); toggleTheme(); return; }
      if (e.key >= "1" && e.key <= "8") {
        const s = SCEN[Number(e.key) - 1];
        if (s) { e.preventDefault(); loadScenario(s.key); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [SCEN, loadScenario, toggleTheme]);

  const personaLabel = personas ? personas[persona] ?? "" : "";
  const ctx: Ctx = useMemo(() => ({
    ST, setST: setSTx, SCEN, tab, show, persona, personaLabel, personas: personas || {}, setPersona,
    chat: chatRef.current, redraw, clearChat: () => { chatRef.current.length = 0; }, ask, explain, why, loadScenario, toast,
  }), [ST, setSTx, SCEN, tab, show, persona, personaLabel, personas, setPersona, redraw, ask, explain, why, loadScenario, toast]);

  useEffect(() => { if (QA) document.documentElement.dataset.qa = "1"; }, []);

  const darkOn = theme === "dark" || (theme === "system" && typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const themeIcon = () => darkOn ? (
    <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="8" cy="8" r="3" /><path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.2 3.2l1.1 1.1M11.7 11.7l1.1 1.1M3.2 12.8l1.1-1.1M11.7 4.3l1.1-1.1" /></svg>
  ) : (
    <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M13.5 10.2A5.5 5.5 0 0 1 5.8 2.5 5.5 5.5 0 1 0 13.5 10.2z" /></svg>
  );
  const account = (place: "rail" | "bar") => (
    <div className={`cluster cluster-${place}`}>
      <span className="pill rail-pill">Synthetic</span>
      <button type="button" className="icon-btn" aria-label={darkOn ? "Switch to light theme" : "Switch to dark theme"} title="Theme (T)" onClick={toggleTheme}>{themeIcon()}</button>
      <button type="button" className="icon-btn" aria-label="Open command bar" title="Command (⌘K)" onClick={() => setCmd(true)}>
        <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="7" cy="7" r="4.2" /><path d="M10.2 10.2 13.5 13.5" /></svg>
      </button>
      <div className="acct">
        <button type="button" className="acct-btn" aria-label="Account" aria-expanded={acct} onClick={() => { setRailLock(false); setAcct((v) => !v); }}>
          <span className="acct-mark" aria-hidden="true">{(personaLabel || "E").slice(0, 1)}</span>
          <span className="acct-name">{personaLabel || "Account"}</span>
        </button>
        {acct ? (
          <div className="acct-menu glass" role="menu">
            <div className="acct-who">
              <b>{personaLabel || "Executive"}</b>
              <span>demo@nimbuspay.example</span>
            </div>
            <button type="button" role="menuitem" onClick={() => { setAcct(false); setProfile(true); }}>Profile</button>
            <button type="button" role="menuitem" onClick={() => { setAcct(false); setHelp(true); }}>Keyboard shortcuts</button>
            <button type="button" role="menuitem" onClick={() => { setAcct(false); toggleTheme(); }}>{darkOn ? "Light theme" : "Dark theme"}</button>
            <button type="button" role="menuitem" className="danger" onClick={signOut}>Sign out</button>
          </div>
        ) : null}
      </div>
    </div>
  );

  return (
    <AppCtx.Provider value={ctx}>
      <div className="app-frame min-h-screen">
        {drawer ? <button type="button" className="drawer-scrim" aria-label="Close menu" onClick={() => setDrawer(false)} /> : null}
        <aside
          className={`shell-side ${drawer ? "drawer-open" : ""} ${railLock && !acct ? "rail-locked" : ""}`}
          onMouseEnter={() => { if (leftRail.current) { leftRail.current = false; setRailLock(false); } }}
          onMouseLeave={() => { leftRail.current = true; }}
        >
          <div className="rail-surface">
            <div className="side-head">
              <div className="side-brand">
                <span className="brand-badge" aria-hidden="true">N</span>
                <span className="brand-copy">
                  <b>NimbusPay</b>
                  <span>Adoption Insights</span>
                </span>
              </div>
              <button type="button" className="icon-btn drawer-close" aria-label="Close menu" onClick={() => setDrawer(false)}>
                <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 4l8 8M12 4l-8 8" /></svg>
              </button>
            </div>
            <div className="side-scroll">
              <div className="side-datasets" role="group" aria-label="Scenario presets">
                <div className="nav-group">Presets</div>
                {SCEN.map((s: J) => (
                  <button key={s.key} type="button" className="nav-item" data-preset={s.key} aria-pressed={ST?.dataset === s.key} aria-label={s.label} onClick={(e) => { e.currentTarget.blur(); setRailLock(true); setAcct(false); loadScenario(s.key); }}>
                    <DatasetIcon id={s.key} />
                    <span className="nav-label">{SHORT[s.key] || s.label}</span>
                  </button>
                ))}
                <p id="ds" className="side-ds">{ST ? <>{ST.dataset_label} · {ST.data_as_of}</> : ""}</p>
              </div>
              <nav id="tabs" aria-label="Screens">
                {GROUPS.map(([g, ts]) => (
                  <div key={g} className="side-group">
                    <div className="nav-group">{g}</div>
                    {ts.map((k) => (
                      <button key={k} data-tab={k} id={`tab-${k}`} onClick={(e) => { e.currentTarget.blur(); setRailLock(true); setAcct(false); show(k); }} aria-current={tab === k ? "page" : undefined} className={`nav-item ${tab === k ? "on" : ""}`} aria-label={LABEL[k]}>
                        <NavIcon id={k} />
                        <span className="nav-label">{LABEL[k]}</span>
                      </button>
                    ))}
                  </div>
                ))}
              </nav>
            </div>
            {account("rail")}
          </div>
        </aside>
        <div className="app-main">
          <header className="topbar">
            <button type="button" className="icon-btn menu-btn" aria-label={drawer ? "Close menu" : "Open menu"} aria-expanded={drawer} onClick={() => setDrawer((v) => !v)}>
              <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 4h10M3 8h10M3 12h10" /></svg>
            </button>
            <div className="top-brand"><b>NimbusPay</b></div>
            {account("bar")}
          </header>
          <main id="view">
            {ST && personas ? (
              <Routes>
                {TABS.map(([k]) => { const Page = SCREENS[k]; return <Route key={k} path={"/" + k} element={<div className="screen" key={loc.key + (k === "agent" ? ":" + persona : "")}><Page /></div>} />; })}
                <Route path="*" element={<Navigate to="/data" replace />} />
              </Routes>
            ) : <Skeleton rows={6} />}
          </main>
          <footer className="app-foot">Read-only. Every number is synthetic and labelled. Thresholds and weights are placeholders to agree. Built by Gowtham S.</footer>
        </div>
      </div>
      <CommandBar open={cmd} tabs={TABS} scen={SCEN} onTab={show} onPreset={loadScenario} onAsk={ask} onClose={() => setCmd(false)} />
      {tab !== "agent" ? <CopilotBar open={panel} chat={chatRef.current} onAsk={(q) => ask(q, undefined, true)} onOpenThread={() => { setPanel(false); show("agent"); }} onOpen={() => setPanel(true)} onToggle={() => setPanel((v) => !v)} /> : null}
      <ShortcutSheet open={help} onClose={() => setHelp(false)} />
      <SignIn open={gate} onRole={(r) => { setPersona(r); enter(); }} />
      {QA ? <div className="qa-roles"><RoleSwitch persona={persona} personas={personas} onPick={(r) => { if (r === persona) return; setPersona(r); toast(personas?.[r] || cap(r)); }} /></div> : null}
      {profile ? (
        <div className="modal" role="presentation" onClick={() => setProfile(false)}>
          <div className="profile-card" role="dialog" aria-label="Profile" onClick={(e) => e.stopPropagation()}>
            <p className="eyebrow">Profile</p>
            <h2>{personaLabel || "Executive"}</h2>
            <p className="muted">demo@nimbuspay.example</p>
            <p>This role is the demo switch. A company sign-in would replace it. Nothing is stored.</p>
            <button type="button" className="btn" onClick={() => setProfile(false)}>Close</button>
          </div>
        </div>
      ) : null}
      <Toasts items={toasts} />
      {lin ? <LineageModal L={lin} onClose={() => setLin(null)} /> : null}
      {whyM ? <WhyModal m={whyM.m} L={whyM.L} ST={ST} onClose={() => setWhyM(null)} /> : null}
    </AppCtx.Provider>
  );
}
