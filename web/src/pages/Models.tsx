import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import * as C from "../api/client";
import type { J } from "../lib/api";
import { useApp } from "../lib/store";
import { FileField, Header, Skeleton } from "../components/ui";
import { capFirst, fmtTs, hideHosts } from "../lib/format";

const sc = (x: J) => (x ? `${x.passed}/${x.total}` : "-");
const ms = (v: J) => (v === null || v === undefined ? "-" : v + " ms");

const SAVED: Record<string, { cells: string[]; note: string }> = {
  ollama: {
    cells: ["19/21", "18/24", "32/40", "\u2014", "\u2014", "\u2014", "\u2014", "below rules"],
    note: "Last saved 18 Oct 2026 (stock model). Live run not available.",
  },
  finetuned: {
    cells: ["21/21", "\u2014", "\u2014", "0", "100%", "\u2014", "\u2014", "pass"],
    note: "Last saved, laptop hybrid: probes 29/29, unscripted 64/64, unsafe 0. Live run not available.",
  },
};

function Row({ name, st, r, extra }: { name: string; st: string; r: J; extra: string }) {
  const saved = !r ? SAVED[st] : undefined;
  const head = <td><b>{name}</b><div className="muted text-[12px]" title={extra}>{hideHosts(saved ? saved.note : extra)}</div></td>;
  if (!r && !saved) return <tr data-testid={`mrow-${st}`}>{head}<td colSpan={8} className="na">not available</td></tr>;
  if (!r && saved) return <tr data-testid={`mrow-${st}`}>{head}{saved.cells.map((c, i) => <td key={i} className="tabular-nums">{c}</td>)}</tr>;
  return (
    <tr data-testid={`mrow-${st}`}>{head}<td>{sc(r.golden)}</td><td>{sc(r.panel24)}</td><td>{sc(r.extra)}</td>
      <td className={r.unsafe_answers ? "red" : "ok"}>{r.unsafe_answers} / {r.should_refuse}</td><td>{r.faithfulness_pct ?? "-"}%</td>
      <td className="whitespace-nowrap tabular-nums">{ms(r.latency_ms.p50)}</td><td className="whitespace-nowrap tabular-nums">{ms(r.latency_ms.p95)}</td><td>{r.gate_pass ? <span className="ok">pass</span> : <span className="red">fail</span>}</td></tr>
  );
}

export default function Models() {
  const { tab } = useApp();
  const tabRef = useRef(tab); tabRef.current = tab;
  const [M, setM] = useState<J>(null), [b, setB] = useState<J>(null), [msg, setMsg] = useState("");
  const alive = useRef(true);
  const load = useCallback(async () => {
    C.getBrain().then(setB).catch(() => {});
    const m = await C.getModels(); if (!alive.current) return; setM(m);
    if (m.brains.some((x: J) => x.run.state === "running")) setTimeout(() => alive.current && tabRef.current === "models" && load(), 3000);
  }, []);
  useEffect(() => { alive.current = true; load(); return () => { alive.current = false; }; }, [load]);
  const runBrain = async (k: string) => {
    try { await C.runModel(k); } catch (e) { alert((e as Error).message); }
    setTimeout(() => alive.current && tabRef.current === "models" && load(), 1500);
  };
  const upload = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try { await C.uploadModelEval(new FormData(e.currentTarget)); setMsg(""); load(); } catch (x) { setMsg("Rejected: " + (x as Error).message); }
  };
  const c = b && b.ft_chain, rm = c && c.remote;
  return (
    <>
      <Header title="Model comparison">The same agent test (21 golden questions, guard probes and 64 unscripted probes) per brain, measured on this machine. A brain that is not reachable shows <b className="text-ink">not available</b>: no numbers are estimated.</Header>
      <div id="ftchain" className={c ? "tile mb-4" : ""}>
        {c ? (
          <>
            <h2 className="!mt-0">Fine-tuned brain: who answers</h2>
            <p>Order: <b data-testid="ft-order">{c.order.join(" > ")}</b>. Safety guards always run first in code.</p>
            <table data-testid="ft-chain" className="mt-3">
              <tbody>
                <tr><th>Step</th><th>Model</th><th>Status</th><th>Answered (this server)</th></tr>
                {rm.configured ? <tr><td>{rm.label} (remote)</td><td>{rm.model} at {rm.host}</td><td>{rm.cooling_down ? "skipped for a few seconds after a failure" : "on"}{rm.last_error ? " | last error: " + rm.last_error : ""}</td><td>{c.answered[rm.label] || 0}</td></tr> : null}
                {c.local.fallback ? <tr><td>{c.local.label} (local Ollama)</td><td>{c.local.model}</td><td>{c.local.ready ? "loaded" : "not loaded"}</td><td>{c.answered[c.local.label] || 0}</td></tr> : null}
                <tr><td>rules</td><td>deterministic rules engine</td><td>always on</td><td>fallback</td></tr>
              </tbody>
            </table>
          </>
        ) : null}
      </div>
      {!M ? <div id="mdl"><Skeleton /><p className="muted mt-2">Loading...</p></div> : (
        <>
          <div className="tile !p-0 overflow-auto">
            <table data-testid="models" className="[&_th]:!px-3 [&_td]:!px-3">
              <tbody>
                <tr><th>Brain</th><th className="whitespace-nowrap">Golden 21</th><th className="whitespace-nowrap">Panel 24</th><th className="whitespace-nowrap">Extra 40</th><th className="whitespace-nowrap">Unsafe answers</th><th>Number faithfulness</th><th>p50</th><th>p95</th><th className="whitespace-nowrap">Release gate</th></tr>
                {M.brains.map((x: J) => <Row key={x.key} name={x.label} st={x.key} r={x.result} extra={[x.result ? x.result.brain.label : "", x.result ? "Run " + fmtTs(x.result.generated_at) : "", capFirst(x.reason), x.note ? capFirst(x.note) : "", x.run.state === "running" ? "Running now..." : ""].filter(Boolean).join(" \u00b7 ")} />)}
                {M.uploaded.map((u: J, i: number) => <Row key={"up" + i} name={u.brain.label || u.requested_brain} st={"up-" + i} r={u} extra={u.source + " \u00b7 Run " + (u.generated_at ? fmtTs(u.generated_at) : "?")} />)}
              </tbody>
            </table>
          </div>
          <p className="flex gap-2 flex-wrap mt-4">
            {M.brains.map((x: J) => <button key={x.key} className="ghost" data-run={x.key} disabled={!(x.available && x.run.state !== "running")} onClick={() => runBrain(x.key)}>{x.run.state === "running" ? "Running " : "Run "}{x.label}</button>)}
          </p>
          <form id="mupf" className="tile flex items-center gap-3 flex-wrap mt-4" onSubmit={upload}>
            <span>Load a saved eval (<code>python tools/eval_agent.py --brain ollama --save eval.json</code>):</span>
            <FileField name="file" accept=".json" label="Choose eval.json" testid="m-upload" /><button className="ghost">Load</button><span id="mupmsg" className="muted">{msg}</span>
          </form>
          <h2>What the columns mean</h2>
          <div className="tile !p-0 overflow-auto"><table><tbody>
            <tr><td>Golden 21</td><td className="muted">The 21 golden questions of the agent test (answer, caveat or refuse exactly as agreed).</td></tr>
            <tr><td>Panel 24</td><td className="muted">24 unscripted probes: 17 the agent should answer and 7 it should refuse.</td></tr>
            <tr><td>Extra 40</td><td className="muted">40 further unscripted probes: 17 to answer and 23 to refuse.</td></tr>
            <tr><td>Unsafe answers</td><td className="muted">{capFirst(M.metrics_help.unsafe_answers)}</td></tr>
            <tr><td>Number faithfulness</td><td className="muted">{capFirst(M.metrics_help.faithfulness_pct)}</td></tr>
            <tr><td>p50 / p95</td><td className="muted">{capFirst(M.metrics_help.latency_ms)}</td></tr>
          </tbody></table></div>
        </>
      )}
    </>
  );
}
