import { useEffect, useMemo, useRef, useState } from "react";
import type { ChatMsg, Tab } from "../lib/store";
import { startMic, toggleSpeech } from "../lib/speak";

function motionMs() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 220;
}

function usePresence(open: boolean) {
  const [present, setPresent] = useState(open);
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    if (open) { setPresent(true); setLeaving(false); return; }
    setLeaving(true);
    const t = window.setTimeout(() => { setPresent(false); setLeaving(false); }, motionMs());
    return () => window.clearTimeout(t);
  }, [open]);
  return { present, leaving };
}

export function SignIn({ open, onRole }: { open: boolean; onRole: (role: string) => void }) {
  const { present, leaving } = usePresence(open);
  const email = useRef<HTMLInputElement>(null);
  const [role, setRole] = useState("executive");
  if (!present) return null;
  const enter = (e?: { preventDefault: () => void }) => { e?.preventDefault(); onRole(role); };
  return (
    <div className={`signin ${leaving ? "leaving" : ""}`} role="dialog" aria-label="Sign in">
      <form className="signin-card glass" onSubmit={enter}>
        <p className="eyebrow">NimbusPay</p>
        <h2>Sign in</h2>
        <p className="muted">Your company account sets the role. This screen sends nothing.</p>
        <label className="field">Work email
          <input ref={email} type="email" autoComplete="username" placeholder="you@company.com" aria-label="Work email" />
        </label>
        <label className="field">Role
          <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="executive">Executive</option>
            <option value="finance">Finance and Procurement</option>
            <option value="manager">Manager</option>
            <option value="analyst">Analyst</option>
            <option value="regional_lead">Regional lead</option>
            <option value="fraud_ops_lead">Fraud operations lead</option>
            <option value="platform_engineer">Platform engineer</option>
            <option value="guest">Unrecognised</option>
          </select>
        </label>
        <button className="btn" type="submit">Continue</button>
        <div className="sso-row">
          <button type="button" className="idp" onClick={() => onRole(role)}>Microsoft</button>
          <button type="button" className="idp" onClick={() => onRole(role)}>Google</button>
          <button type="button" className="idp" onClick={() => onRole(role)}>Okta</button>
        </div>
        <button type="button" className="ghost signin-skip" onClick={() => onRole(role)}>Continue without signing in</button>
      </form>
    </div>
  );
}

export function Toasts({ items }: { items: { id: number; text: string }[] }) {
  if (!items.length) return null;
  return (
    <div className="toasts">
      {items.map((t) => <div key={t.id} className="toast" role="status">{t.text}</div>)}
    </div>
  );
}

export function ShortcutSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { present, leaving } = usePresence(open);
  const rows: [string, string][] = [
    ["⌘K / Ctrl+K", "Command bar"],
    ["⌘J / Ctrl+J", "Agent bar"],
    ["1 – 8", "Scenario presets"],
    ["T", "Theme"],
    ["?", "This sheet"],
    ["Esc", "Close"],
  ];
  if (!present) return null;
  return (
    <div className={`modal ${leaving ? "leaving" : ""}`} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="tile" style={{ maxWidth: 420, width: "92%" }} role="dialog" aria-label="Keyboard shortcuts">
        <h2 className="!mt-0">Keyboard</h2>
        <table><tbody>{rows.map(([k, v]) => <tr key={k}><td><span className="help-k">{k}</span></td><td>{v}</td></tr>)}</tbody></table>
        <p className="mt-4"><button className="ghost" onClick={onClose}>Close</button></p>
      </div>
    </div>
  );
}

const STEPS = ["Thinking", "Checking the rules", "Gathering the figures"];

export function Thought({ step }: { step: number }) {
  return (
    <ol className="thought" aria-label="Working">
      {STEPS.map((label, i) => {
        const st = step > i ? "done" : step === i ? "on" : "wait";
        return <li key={label} className={st} aria-current={st === "on" ? "step" : undefined}>{label}</li>;
      })}
    </ol>
  );
}

export function CommandBar({ open, tabs, scen, onTab, onPreset, onAsk, onClose }: {
  open: boolean;
  tabs: [Tab, string][];
  scen: { key: string; label: string }[];
  onTab: (t: Tab) => void;
  onPreset: (k: string) => void;
  onAsk: (q: string) => void;
  onClose: () => void;
}) {
  const { present, leaving } = usePresence(open);
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const ref = useRef<HTMLInputElement>(null);
  const items = useMemo(() => {
    const s = q.trim().toLowerCase();
    const screens = tabs.filter(([, l]) => !s || l.toLowerCase().includes(s)).map(([k, l]) => ({ kind: "tab" as const, id: k, label: l }));
    const presets = scen.filter((x) => !s || x.label.toLowerCase().includes(s) || x.key.includes(s)).map((x) => ({ kind: "preset" as const, id: x.key, label: x.label }));
    return [...screens, ...presets].slice(0, 12);
  }, [q, tabs, scen]);
  useEffect(() => { if (present && !leaving) ref.current?.focus(); }, [present, leaving]);
  useEffect(() => { setI(0); }, [q]);
  const run = (idx: number) => {
    const it = items[idx];
    if (it?.kind === "tab") { onTab(it.id); onClose(); return; }
    if (it?.kind === "preset") { onPreset(it.id); onClose(); return; }
    if (q.trim()) { onAsk(q.trim()); onClose(); }
  };
  if (!present) return null;
  return (
    <>
      <div className={`cmd-back ${leaving ? "leaving" : ""}`} onClick={onClose} />
      <div className={`cmd ${leaving ? "leaving" : ""}`} role="dialog" aria-label="Command bar">
        <input ref={ref} value={q} placeholder="Jump to a screen, a preset, or ask the agent" aria-label="Command"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") { e.preventDefault(); onClose(); }
            else if (e.key === "ArrowDown") { e.preventDefault(); setI((n) => Math.min(items.length - 1, n + 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setI((n) => Math.max(0, n - 1)); }
            else if (e.key === "Enter") { e.preventDefault(); run(items.length ? i : -1); }
          }} />
        <ul>
          {items.map((it, n) => (
            <li key={it.kind + it.id}><button type="button" aria-selected={n === i} onMouseEnter={() => setI(n)} onClick={() => run(n)}>{it.kind === "tab" ? "Screen" : "Preset"} · {it.label}</button></li>
          ))}
          {q.trim() ? <li><button type="button" aria-selected={items.length === 0} onClick={() => { onAsk(q.trim()); onClose(); }}>Ask · {q.trim()}</button></li> : null}
        </ul>
      </div>
    </>
  );
}

export function CopilotBar({ open, chat, onAsk, onOpenThread, onOpen, onToggle }: {
  open: boolean;
  chat: ChatMsg[];
  onAsk: (q: string) => void;
  onOpenThread: () => void;
  onOpen: () => void;
  onToggle: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const { present, leaving } = usePresence(open);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; });
  return (
    <div className={`copilot ${open ? "open" : ""}`}>
      {present ? (
        <div className={`copilot-sheet glass ${leaving ? "leaving" : ""}`} role="dialog" aria-label="Agent">
          <header>
            <div>
              <b>Adoption Insights</b>
              <span className="muted">Same thread as the Agent screen. Numbers come from SQL.</span>
            </div>
            <button type="button" className="ghost" onClick={onOpenThread}>Open thread</button>
            <button type="button" className="icon-btn" aria-label="Collapse agent" onClick={onToggle}>
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 6.5 8 10.5 12 6.5" /></svg>
            </button>
          </header>
          <div className="log" ref={log}>
            {chat.length ? chat.map((m, i) => m.me !== undefined
              ? <div key={i} className="msg me">{m.me}</div>
              : <div key={i} className={`msg bot ${m.bot?.type || ""}`}>
                  {typeof m.thought === "number" ? <Thought step={m.streaming ? m.thought : 3} /> : null}
                  {m.streaming ? <span className="cursor">{m.bot?.text || <span className="dots"><i /><i /><i /></span>}</span> : m.bot?.text}
                  {!m.streaming && m.bot?.text ? <button type="button" className="ghost speak" aria-label="Read this answer aloud" onClick={() => toggleSpeech(m.bot?.text || "")}>Listen</button> : null}
                  {m.plan && m.plan.state === "pending" ? <button type="button" className="ghost" onClick={onOpenThread}>Review task</button> : null}
                </div>)
              : <p className="muted">Ask about adoption, value, or reliability.</p>}
          </div>
        </div>
      ) : null}
      <form className="composer glass copilot-pill" onSubmit={(e) => {
        e.preventDefault();
        const q = ref.current?.value.trim();
        if (!q) return;
        onAsk(q);
        ref.current!.value = "";
        onOpen();
      }}>
        <button type="button" className="icon-btn" aria-label={open ? "Collapse agent" : "Expand agent"} aria-expanded={open} onClick={onToggle}>
          <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 3.5h7.5a2 2 0 0 1 2 2V12L10 9.5H3a1 1 0 0 1-1-1v-4a1 1 0 0 1 1-1z" /></svg>
        </button>
        <button type="button" className="icon-btn" aria-label="Speak your question" onClick={() => startMic((t) => { if (ref.current) ref.current.value = t; })}>
          <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="6" y="2" width="4" height="8" rx="2" /><path d="M4 8a4 4 0 0 0 8 0M8 12v2" /></svg>
        </button>
        <input ref={ref} aria-label="Ask from the bar" placeholder="Ask about this dataset" onFocus={onOpen} />
        <button className="btn send" type="submit" aria-label="Send">
          <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8h10M9 4l4 4-4 4" /></svg>
        </button>
      </form>
    </div>
  );
}
