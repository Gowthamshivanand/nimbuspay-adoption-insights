import { useRef, useState } from "react";
import * as C from "../api/client";
import type { J } from "../lib/api";
import { useApp } from "../lib/store";
import { fmt, keepTogether, oc } from "../lib/format";
import { Bars, Header } from "../components/ui";

/* Inputs are uncontrolled (read at Simulate time) exactly like the legacy DOM version. */
export default function WhatIf() {
  const { ST, show } = useApp(); const f = ST.funnel;
  const seats = useRef<HTMLInputElement>(null), ids = useRef<HTMLInputElement>(null), conn = useRef<HTMLInputElement>(null);
  const [seatsV, setSeatsV] = useState(String(f.LF1)), [idsV, setIdsV] = useState<string | null>(null);
  const [w, setW] = useState<J>(null), [liveMsg, setLiveMsg] = useState("");
  const run = async () => {
    const body = { seats: +seats.current!.value, connector_fix: conn.current!.checked, id_coverage: idsV !== null ? +ids.current!.value : null };
    if (!C.STATIC) { setW(await C.whatIf(body)); return; }
    /* Static demo only: a combination that was not recorded shows the "live in the full app" note instead of an error. */
    try { setW(await C.whatIf(body)); setLiveMsg(""); } catch (e) { setW(null); setLiveMsg((e as Error).message); }
  };
  const col = (t: string, x: J) => (
    <div className="tile">
      <div className="eyebrow">{t}</div>
      <div className={`out mt-1 ${oc(x.outcome)}`}>{x.outcome}</div>
      <div className="muted text-[13px] mt-1">{keepTogether(x.why)}</div>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-[13px] max-w-[320px]">
        <dt className="muted">M01</dt><dd className="tabular-nums">{fmt(x.M01, "%")}</dd>
        <dt className="muted">M11</dt><dd className="tabular-nums">{fmt(x.M11, "%")}</dd>
        <dt className="muted">Exact share</dt><dd className="tabular-nums">{x.exact_share}%</dd>
        <dt className="muted">Paid seats unused</dt><dd className="tabular-nums">{x.paid_unused}</dd>
        <dt className="muted">M19</dt><dd><b className={x.score_state === "red" ? "red" : ""}>{x.score ?? "withheld (interim " + x.interim + ")"}</b></dd>
      </dl>
      <div className="mt-4"><Bars rows={["LF1", "LF2", "LF3", "LF4", "LF5", "LF6"].map((k) => [k, x.funnel[k]])} max={Math.max(w.before.funnel.LF1, w.after.funnel.LF1)} /></div>
      <div className="mt-4"><Bars rows={Object.entries(x.pillars).map(([k, v]: [string, J]) => [k, v ?? 0, v ?? "no data"])} max={100} /></div>
    </div>
  );
  return (
    <>
      <Header title="Renewal what-if simulator">Re-runs the same pipeline and renewal rules on a modified copy of {ST.dataset_label}. Not a forecast. Synthetic.</Header>
      <div className="tile">
        <div className="grid-auto items-end">
          <label className="field">Seats at renewal: <b id="wv-seats">{seatsV}</b>
            <input type="range" id="w-seats" data-testid="w-seats" min={0} max={Math.max(f.LF1, f.LF2) + 10} defaultValue={f.LF1} ref={seats} onInput={(e) => setSeatsV(e.currentTarget.value)} /></label>
          <label className="field">Interaction ID coverage: <b id="wv-ids">{idsV === null ? `current (${ST.grouping.exact_share}%)` : idsV + "%"}</b>
            <input type="range" id="w-ids" data-testid="w-ids" min={0} max={100} defaultValue={Math.round(ST.grouping.exact_share)} ref={ids} onInput={(e) => setIdsV(e.currentTarget.value)} /></label>
          <label className="flex items-center text-[13px]"><input type="checkbox" id="w-conn" data-testid="w-conn" ref={conn} /> Connector failures fixed</label>
        </div>
        <p className="mt-4 flex gap-2"><button className="btn" data-testid="w-run" id="w-run" onClick={run}>Simulate</button> <button className="ghost" id="w-reset" onClick={() => show("whatif")}>Reset</button></p>
      </div>
      <div id="w-out" className="mt-4">
        {liveMsg ? <p className="muted mt-4 text-[13px]" data-testid="w-live">{liveMsg} Recorded combinations: 20 seats with nothing else changed, or 25 seats with connector failures fixed and ID coverage at 60%.</p> : null}
        {w ? <><div className="grid gap-3" data-testid="w-result" style={{ gridTemplateColumns: "1fr 1fr" }}>{col("Today", w.before)}{col("What-if", w.after)}</div><p className="muted mt-3 text-[13px]">{w.label}</p></> : null}
      </div>
    </>
  );
}
