import { useCallback, useEffect, useRef, useState } from "react";
import * as C from "../api/client";
import type { J } from "../lib/api";
import { hideRefs, keyLabel, keyValue, money, sentenceTags, symbols } from "../lib/format";
import { Header, Skeleton } from "../components/ui";

export default function Cost() {
  const [M, setM] = useState<J>(null), [r, setR] = useState<J>(null), [err, setErr] = useState(""), [rulesV, setRulesV] = useState("");
  const f = { users: useRef<HTMLInputElement>(null), qpud: useRef<HTMLInputElement>(null), rules: useRef<HTMLInputElement>(null), model: useRef<HTMLSelectElement>(null), tin: useRef<HTMLInputElement>(null), tout: useRef<HTMLInputElement>(null) };
  const run = useCallback(async () => {
    setRulesV(f.rules.current!.value + "%");
    const body = { users: +f.users.current!.value, queries_per_user_day: +f.qpud.current!.value, rules_share: +f.rules.current!.value / 100, model: f.model.current!.value, tokens_in: +f.tin.current!.value, tokens_out: +f.tout.current!.value };
    try { setR(await C.calcCost(body)); setErr(""); } catch (e) { setErr((e as Error).message); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { C.getCostMeta().then(setM); }, []);
  useEffect(() => { if (M) run(); }, [M, run]);
  if (!M) return <Skeleton rows={5} />;
  const d = M.defaults;
  const A = "tag ml-1";
  return (
    <>
      <Header title="Cost and scale calculator">Unit economics of the Adoption Insights Agent. Defaults are <b className="text-ink">assumptions</b>, prices are cited public list prices. Not NimbusPay figures.</Header>
      <div className="grid gap-3 lg:grid-cols-3">
        <div className="tile lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="field"><span>Users <span className={A}>assumption</span></span><input type="number" id="c-users" data-testid="c-users" min={0} defaultValue={d.users} ref={f.users} onInput={run} /></label>
            <label className="field"><span>Questions per user per day <span className={A}>assumption</span></span><input type="number" id="c-qpud" min={0} step={0.5} defaultValue={d.queries_per_user_day} ref={f.qpud} onInput={run} /></label>
            <label className="field"><span>Answered by rules engine: <b id="cv-rules">{rulesV || Math.round(d.rules_share * 100) + "%"}</b> <span className={A}>assumption</span></span><input type="range" id="c-rules" data-testid="c-rules" min={0} max={100} defaultValue={Math.round(d.rules_share * 100)} ref={f.rules} onInput={run} /></label>
            <label className="field sm:col-span-2"><span>Model for the LLM share</span><select id="c-model" data-testid="c-model" className="w-full" defaultValue={d.model} ref={f.model} onInput={run} onChange={() => {}}>{Object.entries(M.models).map(([k, v]) => <option key={k} value={k}>{v as string}</option>)}</select></label>
            <label className="field"><span>Avg tokens in <span className={A}>assumption</span></span><input type="number" id="c-tin" min={0} defaultValue={d.tokens_in} ref={f.tin} onInput={run} /></label>
            <label className="field"><span>Avg tokens out <span className={A}>assumption</span></span><input type="number" id="c-tout" min={0} defaultValue={d.tokens_out} ref={f.tout} onInput={run} /></label>
          </div>
        </div>
        <div className="outcard" id="c-out" data-testid="c-out">
          {err ? <span className="red">{err}</span> : r ? (
            <>
              <div className="eyebrow">Monthly cost (USD, list price)</div>
              <div className="out mt-1" data-testid="c-monthly">{money(r.monthly_cost_usd)}</div>
              <p className="mt-3 leading-7">Cost per question: <b>{r.cost_per_query_usd === null ? "n/a" : "$" + r.cost_per_query_usd}</b><br />Estimated p95 latency: <b>{r.p95_latency_s} s</b> <span className="tag">{sentenceTags(r.p95_basis)}</span><br />
                Model hosts needed: <b>{r.model_instances}</b> + app hosts: <b>{r.app_instances}</b></p>
              <p className="muted text-[12px] mt-2">{r.queries_per_day} questions/day, {r.llm_queries_per_day} to the LLM. App host {money(r.app_host_usd)} + model {money(r.model_cost_usd)}. {hideRefs(r.note)}</p>
            </>
          ) : null}
        </div>
      </div>
      <h2>Assumptions</h2>
      <div className="tile !p-0 overflow-auto"><table><tbody>{M.assumptions.map((a: J, i: number) => <tr key={i}><td className="whitespace-nowrap" title={a.key}>{keyLabel(a.key)}</td><td>{keyValue(a.key, a.value)}</td><td className="muted">{symbols(sentenceTags(hideRefs(a.note)))}</td></tr>)}</tbody></table></div>
      <h2>Sources (checked {M.sources.S13.checked})</h2>
      <div className="tile !p-0 overflow-auto"><table><tbody>{Object.entries(M.sources).map(([k, s]: [string, J]) => <tr key={k}><td>{k}</td><td>{hideRefs(s.label)}{/^https?:/.test(s.url) ? <div className="muted text-[12px] break-all">{s.url}</div> : null}</td></tr>)}</tbody></table></div>
    </>
  );
}
