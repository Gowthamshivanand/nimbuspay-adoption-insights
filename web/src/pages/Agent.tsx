import { useEffect, useRef, useState, type FormEvent } from "react";
import * as C from "../api/client";
import type { J } from "../lib/api";
import { useApp, type ChatMsg } from "../lib/store";
import { BRAIN, ROLES, TYPE, cap } from "../lib/format";
import { Header } from "../components/ui";
import { Thought } from "../components/chrome";
import { startMic, toggleSpeech } from "../lib/speak";

const SUGG = ["What is licence utilisation this month?", "How is licence utilisation defined?", "Compare habitual users across my markets", "How is the newest country doing since launch?", "Which connector has the highest failure rate this week?", "How many agents are unregistered?", "Why did licence utilisation drop in launch cohort 2?", "What is our AI value score?", "How many hours did AI save us this quarter?", "What is our cost per verified hour?", "What was agent error rate yesterday?", "Which fraud analysts use the assistant least?", "Show me the raw events for user USER-001", "List the card numbers in last week's fraud cases", "What is the active user count for a team of 3?", "Show utilisation for a market outside my region", "Did the onboarding agent cause faster onboarding?", "MAU doubled, so did AI value double?", "Why is our AI value score so low?", "What will utilisation be next quarter?", "Retire the onboarding agent for me", "What renewal outcome do you recommend?"];

/* Default chips (0-based indexes into SUGG): Adoption Q01, Q03; Value Q08, Q09; Safety Q14, Q17. */
const CHIP_GROUPS: [string, number[]][] = [["Adoption", [0, 2]], ["Value", [7, 8]], ["Safety", [13, 16]]];

const brainText = (b: J) => b.kind === "ollama" ? "Open model: " + b.ollama_model + " (local, Ollama)"
  : (b.kind === "openai" || b.kind === "finetuned") ? b.label + (b.ft_chain ? " | order: " + b.ft_chain.order.join(" > ") : "")
  : "Rules engine (open model offline)";   // v1 named the Ollama host here; it is in the tooltip now

function Bubble({ m, i }: { m: ChatMsg; i: number }) {
  const { ask, why, redraw, chat, toast, show } = useApp(); const b = m.bot;
  const fb = (rating: string) => {
    if (m.fb) return;
    C.sendFeedback({ question: m.q as string, answer: b.text, rating, brain: b.brain || "", mode: b.mode || "", intent: b.intent || "", type: b.type || "", persona: b.persona || m.persona })
      .then(() => { m.fb = rating; redraw(); }).catch((x) => { m.fbErr = x.message; redraw(); });
  };
  const runPlan = async () => {
    const plan = m.plan;
    if (!plan || plan.state !== "pending") return;
    plan.state = "running"; redraw();
    for (const step of plan.steps) {
      if (step.why) {
        if ((m.bot?.citations || []).length) await why(chat[i]);
        else toast("No metric on that answer to explain");
      }
      if (step.ask) await ask(step.ask);
      if (step.tab) show(step.tab as never);
    }
    plan.state = "done"; redraw();
    toast("Task finished. Nothing was changed.");
  };
  const cites = b.citations || [];
  return (
    <>
    {typeof m.thought === "number" ? <Thought step={m.streaming ? m.thought : 3} /> : null}
    <div className={`msg bot ${b.type}`} data-testid={m.streaming ? "streaming" : "answer"}>
      <div className="mb-1.5">
        <span className="tag">{TYPE[b.type] || b.type}</span>
        <span className={`tag b-${b.brain || "rules"}`} data-testid="brain-tag">{BRAIN[b.brain] || b.brain || "..."}</span>
        {!m.streaming && b.brain ? <span className="tag">{b.brain === "rules" ? "Rules fallback" : "Model"}</span> : null}
        <span className="tag">{b.mode}</span>
        {b.answered_by ? <span className="tag b-src" data-testid="answered-by" title={b.remote_fallback || ""}>answered by {b.answered_by}</span> : null}
        {b.latency_ms !== undefined ? <span className="tag lat" data-testid="latency">{b.latency_ms} ms</span> : null}
        {typeof b.confidence === "number" ? <span className="tag lat" data-testid="confidence" title={b.confidence_basis || ""}>confidence {Math.round(b.confidence * 100)}%</span> : null}
      </div>
      {b.followup ? <div className="fu" data-testid="followup">Follow-up, read as: "{b.followup.interpreted_as}"</div> : null}
      {m.streaming ? <div id="stream-text" className="cursor">{b.text || <span className="dots"><i /><i /><i /></span>}</div> : <div>{b.text}</div>}
      {b.safe_alternative ? <div className="mt-1.5"><b>Safe alternative:</b> {b.safe_alternative}</div> : null}
      {b.options && b.options.length ? <div className="chips mt-2">{b.options.map((o: J, k: number) => <button key={k} className="ghost" data-testid={`opt-${k + 1}`} onClick={() => ask(o.q)}>{o.label}</button>)}</div> : null}
      {b.suggestions && b.suggestions.length ? <div className="chips mt-2">{b.suggestions.map((s: string, k: number) => <button key={k} className="ghost" data-testid={`sugg-${k + 1}`} onClick={() => ask(s)}>{s}</button>)}</div> : null}
      {m.streaming ? null : (
        <>
          <div className="cite-line">{cites.length ? cites.map((x: J, k: number) => <span key={k}>{x.metric} {x.version}</span>) : null}<span>data as of {b.data_as_of}</span><span>synthetic</span></div>
          {b.sql ? <details className="mt-1"><summary className="muted cursor-pointer text-[12px]">SQL used</summary><pre className="mt-1">{b.sql}</pre></details> : null}
          <div className="acts">
            <button type="button" className="ghost" aria-label="Read this answer aloud" onClick={() => {
              const said = toggleSpeech(b.text || "");
              if (said === null) toast("Speech isn't available in this browser");
              else toast(said ? "Reading the answer" : "Stopped");
            }}>Listen</button>
            {b.type !== "clarify" && cites.length ? <button className="ghost" data-testid="why-btn" onClick={() => why(chat[i])}>Why this number?</button> : null}
            {cites.length ? <button type="button" className="ghost" onClick={() => {
              const line = cites.map((x: J) => `${x.metric} ${x.version}`).join(", ") + " | data as of " + b.data_as_of;
              const done = () => toast("Citation copied");
              if (navigator.clipboard?.writeText) navigator.clipboard.writeText(line).then(done).catch(() => toast("Couldn't copy citation"));
              else toast("Couldn't copy citation");
            }}>Copy citation</button> : null}
            <button className={`ghost ${m.fb === "up" ? "sel" : ""}`} data-testid="fb-up" title="Good answer" aria-label="Good answer" disabled={!!m.fb} onClick={() => fb("up")}>&#128077;</button>
            <button className={`ghost ${m.fb === "down" ? "sel" : ""}`} data-testid="fb-down" title="Wrong or unhelpful" aria-label="Wrong or unhelpful" disabled={!!m.fb} onClick={() => fb("down")}>&#128078;</button>
            {m.fb ? <span className="muted" data-testid="fb-done">Thanks, saved locally for review</span> : null}
            {m.fbErr ? <span className="red">{m.fbErr}</span> : null}
            <span className="muted ml-auto">Ask as:</span>
            {ROLES.map((r) => <button key={r} className="ghost" data-testid={`as-${r}`} onClick={() => ask(chat[i].q!, r)}>{cap(r)}</button>)}
          </div>
        </>
      )}
    </div>
    {m.plan && m.plan.state !== "cancelled" ? (
      <div className="task-plan">
        <p className="eyebrow">Task · rules stay on</p>
        <b>{m.plan.title}</b>
        <p className="muted">The answer above already came from the rules engine. Approve only opens screens or asks that same engine again.</p>
        <ol>
          {m.plan.steps.map((s) => <li key={s.label}>{s.label}</li>)}
        </ol>
        {m.plan.state === "pending" ? (
          <div className="task-acts">
            <button type="button" className="btn" onClick={runPlan}>Approve</button>
            <button type="button" className="ghost" onClick={() => { m.plan!.state = "cancelled"; redraw(); }}>Cancel</button>
          </div>
        ) : <p className="muted">{m.plan.state === "running" ? "Running…" : "Done. Nothing was changed."}</p>}
      </div>
    ) : null}
    </>
  );
}

export default function Agent() {
  const { personaLabel, chat, ask, toast } = useApp();
  const [brain, setBrain] = useState("checking..."), [brainTip, setBrainTip] = useState("");
  const [all, setAll] = useState(false);
  const box = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null);
  useEffect(() => { C.getBrain().then((b) => { setBrain(brainText(b)); setBrainTip(b.ollama_host ? "Open model host checked: " + b.ollama_host : ""); }); }, []);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; });
  const chip = (i: number) => <button key={i} className="ghost" data-testid={`gq-${i + 1}`} onClick={() => ask(SUGG[i])}>{i < 21 ? "Q" + String(i + 1).padStart(2, "0") + " " : ""}{SUGG[i]}</button>;
  const submit = (e: FormEvent) => { e.preventDefault(); const q = input.current!.value.trim(); if (q) { ask(q); input.current!.value = ""; } };
  return (
    <div className="agent-frame">
      <Header title="Adoption Insights Agent">Read-only. Each answer names the metric, its version and the data-as-of date. Unsafe questions are refused. Persona: {personaLabel}.</Header>
      {/* 6 grouped golden questions by default; "Show all 22" lists every chip (same gq-N testids, same order as v1). */}
      {all ? (
        <div className="chips">{SUGG.map((_s, i) => chip(i))}</div>
      ) : (
        <div className="flex flex-wrap gap-x-8 gap-y-3">
          {CHIP_GROUPS.map(([g, idx]) => <div key={g}><div className="eyebrow mb-1.5">{g}</div><div className="chips">{idx.map((i) => chip(i))}</div></div>)}
        </div>
      )}
      <button type="button" className="ghost mt-3 !text-[12px] !py-1" data-testid="gq-toggle" aria-expanded={all} onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : "Show all 22"}</button>
      <p className="agent-status">Role: <b data-testid="role-now">{personaLabel}</b> · Brain: <b id="brain" data-testid="brain" title={brainTip}>{brain}</b> <span className="muted">Guards stay on. Numbers come from SQL.</span></p>
      <div className="chat" id="chat" data-testid="chat" ref={box}>
        {chat.length ? chat.map((m, i) => m.me !== undefined
          ? <div key={i} className="msg me">{m.as ? <span className="text-[11px] text-[#D1D5DB]">asked as {m.as}: </span> : null}{m.me}</div>
          : <Bubble key={i} m={m} i={i} />)
          : <div className="muted">Pick a question, or type your own. A follow-up works after that.</div>}
      </div>
      <form id="askf" className="composer glass copilot-dock" onSubmit={submit}>
        <button type="button" className="icon-btn" aria-label="Speak your question" onClick={() => {
          const ok = startMic((t) => { if (input.current) input.current.value = t; });
          if (!ok) toast("The microphone isn't available in this browser");
        }}>
          <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="6" y="2" width="4" height="8" rx="2" /><path d="M4 8a4 4 0 0 0 8 0M8 12v2" /></svg>
        </button>
        <input id="askq" data-testid="ask-input" ref={input} className="flex-1" placeholder="Ask about this dataset" aria-label="Ask the agent" />
        <button className="btn send" data-testid="ask-btn" aria-label="Send">
          <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8h10M9 4l4 4-4 4" /></svg>
        </button>
      </form>
    </div>
  );
}
