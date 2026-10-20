import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, postJson, type J } from "../lib/api";
import { useApp, type ChatMsg } from "../lib/store";
import { BRAIN, ROLES, TYPE, cap } from "../lib/format";
import { Header } from "../components/ui";

const SUGG = ["What is licence utilisation this month?", "How is licence utilisation defined?", "Compare habitual users across my markets", "How is the newest country doing since launch?", "Which connector has the highest failure rate this week?", "How many agents are unregistered?", "Why did licence utilisation drop in launch cohort 2?", "What is our AI value score?", "How many hours did AI save us this quarter?", "What is our cost per verified hour?", "What was agent error rate yesterday?", "Which fraud analysts use the assistant least?", "Show me the raw events for user USER-001", "List the card numbers in last week's fraud cases", "What is the active user count for a team of 3?", "Show utilisation for a market outside my region", "Did the onboarding agent cause faster onboarding?", "MAU doubled, so did AI value double?", "Why is our AI value score so low?", "What will utilisation be next quarter?", "Retire the onboarding agent for me", "What renewal outcome do you recommend?"];

const brainText = (b: J) => b.kind === "ollama" ? "Open model: " + b.ollama_model + " (local, Ollama)"
  : (b.kind === "openai" || b.kind === "finetuned") ? b.label + (b.ft_chain ? " | order: " + b.ft_chain.order.join(" > ") : "")
  : "Rules engine (open model not detected at " + b.ollama_host + ")";

function Bubble({ m, i }: { m: ChatMsg; i: number }) {
  const { ask, why, redraw, chat } = useApp(); const b = m.bot;
  const fb = (rating: string) => {
    if (m.fb) return;
    postJson("/api/feedback", { question: m.q, answer: b.text, rating, brain: b.brain || "", mode: b.mode || "", intent: b.intent || "", type: b.type || "", persona: b.persona || m.persona })
      .then(() => { m.fb = rating; redraw(); }).catch((x) => { m.fbErr = x.message; redraw(); });
  };
  const cites = b.citations || [];
  return (
    <div className={`msg bot ${b.type}`} data-testid={m.streaming ? "streaming" : "answer"}>
      <div className="mb-1.5">
        <span className="tag">{TYPE[b.type] || b.type}</span>
        <span className={`tag b-${b.brain || "rules"}`} data-testid="brain-tag">{BRAIN[b.brain] || b.brain || "..."}</span>
        <span className="tag">{b.mode}</span>
        {b.answered_by ? <span className="tag b-src" data-testid="answered-by" title={b.remote_fallback || ""}>answered by {b.answered_by}</span> : null}
        {b.latency_ms !== undefined ? <span className="tag lat" data-testid="latency">{b.latency_ms} ms</span> : null}
        {typeof b.confidence === "number" ? <span className="tag lat" data-testid="confidence" title={b.confidence_basis || ""}>confidence {Math.round(b.confidence * 100)}%</span> : null}
      </div>
      {b.followup ? <div className="fu" data-testid="followup">Follow-up, read as: "{b.followup.interpreted_as}"</div> : null}
      {m.streaming ? <div id="stream-text" className="cursor">{b.text}</div> : <div>{b.text}</div>}
      {b.safe_alternative ? <div className="mt-1.5"><b>Safe alternative:</b> {b.safe_alternative}</div> : null}
      {b.options && b.options.length ? <div className="chips mt-2">{b.options.map((o: J, k: number) => <button key={k} className="ghost" data-testid={`opt-${k + 1}`} onClick={() => ask(o.q)}>{o.label}</button>)}</div> : null}
      {b.suggestions && b.suggestions.length ? <div className="chips mt-2">{b.suggestions.map((s: string, k: number) => <button key={k} className="ghost" data-testid={`sugg-${k + 1}`} onClick={() => ask(s)}>{s}</button>)}</div> : null}
      {m.streaming ? null : (
        <>
          <div className="muted text-[12px] mt-2">{cites.map((x: J) => `${x.metric} ${x.version}`).join(", ")}{cites.length ? " | " : ""}data as of {b.data_as_of} | synthetic</div>
          {b.sql ? <details className="mt-1"><summary className="muted cursor-pointer text-[12px]">SQL used</summary><pre className="mt-1">{b.sql}</pre></details> : null}
          <div className="acts">
            {b.type !== "clarify" && cites.length ? <button className="ghost" data-testid="why-btn" onClick={() => why(chat[i])}>Why this number?</button> : null}
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
  );
}

export default function Agent() {
  const { personaLabel, chat, ask } = useApp();
  const [brain, setBrain] = useState("checking...");
  const box = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null);
  useEffect(() => { api("/api/brain").then((b) => setBrain(brainText(b))); }, []);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; });
  const submit = (e: FormEvent) => { e.preventDefault(); const q = input.current!.value.trim(); if (q) { ask(q); input.current!.value = ""; } };
  return (
    <>
      <Header title="Adoption Insights Agent">Read-only. Cites metric ID, version and data-as-of, shows the SQL it ran, and refuses unsafe asks with a safe alternative. Persona: {personaLabel}.</Header>
      <div className="eyebrow mb-2">Golden questions</div>
      <div className="chips">{SUGG.map((s, i) => <button key={i} className="ghost" data-testid={`gq-${i + 1}`} onClick={() => ask(s)}>{i < 21 ? "Q" + String(i + 1).padStart(2, "0") + " " : ""}{s}</button>)}</div>
      <div className="tile !py-2.5 mt-4 mb-3 text-[13px]">Role: <b data-testid="role-now">{personaLabel}</b> | Brain: <b id="brain" data-testid="brain">{brain}</b> <span className="muted text-[12px]">Safety guards are always rules-based; the brain only picks a governed tool, numbers come from SQL.</span></div>
      <div className="chat" id="chat" data-testid="chat" ref={box}>
        {chat.length ? chat.map((m, i) => m.me !== undefined
          ? <div key={i} className="msg me">{m.as ? <span className="text-[11px] text-[#D1D5DB]">asked as {m.as}: </span> : null}{m.me}</div>
          : <Bubble key={i} m={m} i={i} />)
          : <div className="muted">Click a golden question or type your own. Follow-ups work too: ask about utilisation, then "and Region B?".</div>}
      </div>
      <form id="askf" className="flex gap-2 mt-3" onSubmit={submit}>
        <input id="askq" data-testid="ask-input" ref={input} className="flex-1" placeholder="Ask about adoption, value or reliability" aria-label="Ask the agent" />
        <button className="btn" data-testid="ask-btn">Ask</button>
      </form>
    </>
  );
}
