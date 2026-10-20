import { useRef, useState } from "react";
import { postJson, type J } from "../lib/api";
import { useApp } from "../lib/store";
import { fmt, oc } from "../lib/format";
import { Bars, Header } from "../components/ui";

/* Inputs are uncontrolled (read at Simulate time) exactly like the legacy DOM version. */
export default function WhatIf() {
  const { ST, show } = useApp(); const f = ST.funnel;
  const seats = useRef<HTMLInputElement>(null), ids = useRef<HTMLInputElement>(null), conn = useRef<HTMLInputElement>(null);
  const [seatsV, setSeatsV] = useState(String(f.LF1)), [idsV, setIdsV] = useState<string | null>(null);
  const [w, setW] = useState<J>(null);
  const run = async () => {
    const body = { seats: +seats.current!.value, connector_fix: conn.current!.checked, id_coverage: idsV !== null ? +ids.current!.value : null };
    setW(await postJson("/api/whatif", body));
  };
  const col = (t: string, x: J) => (
    <div className="tile">
      <div className="eyebrow">{t}</div>
      <div className={`out mt-1 ${oc(x.outcome)}`}>{x.outcome}</div>
      <div className="muted text-[13px] mt-1">{x.why}</div>
      <p className="mt-3 text-[13px]">M01 {fmt(x.M01, "%")} | M11 {fmt(x.M11, "%")} | exact {x.exact_share}% | paid seats unused {x.paid_unused}</p>
      <p className="mt-1 text-[13px]">M19: <b className={x.score_state === "red" ? "red" : ""}>{x.score ?? "withheld (interim " + x.interim + ")"}</b></p>
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
        {w ? <><div className="grid gap-3" data-testid="w-result" style={{ gridTemplateColumns: "1fr 1fr" }}>{col("Today", w.before)}{col("What-if", w.after)}</div><p className="muted mt-3 text-[13px]">{w.label}</p></> : null}
      </div>
    </>
  );
}
