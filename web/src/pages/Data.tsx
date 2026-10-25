import { useState, type FormEvent } from "react";
import * as C from "../api/client";
import type { J } from "../lib/api";
import { useApp } from "../lib/store";
import { FileField, Header, Subnav } from "../components/ui";
import PipelineSummary from "./Pipeline";

export default function Data() {
  const { ST, setST, SCEN, show, loadScenario, toast } = useApp();
  const [msg, setMsg] = useState("");
  const upload = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try { const s = await C.uploadCsvs(new FormData(e.currentTarget)); setST(s); show("exec"); }
    catch (x) { const t = "Rejected: " + (x as Error).message; setMsg(t); toast(t); }
  };
  return (
    <>
      <Header title="Data">Pick a synthetic scenario (each one is real CSV data run through the full pipeline), or upload your own event, seat and registry CSVs.</Header>
      <Subnav items={[{ id: "data-presets", label: "Presets" }, { id: "data-upload", label: "Upload" }, { id: "data-pipe", label: "Pipeline" }]} />
      <div id="data-presets" className="sc grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(250px,1fr))" }}>
        {SCEN.map((s: J) => (
          <div key={s.key} className={`tile flex flex-col transition-colors duration-fast ${s.key === ST.dataset ? "on !border-accent shadow-[inset_0_0_0_1px_var(--np-accent)]" : ""}`}>
            <div className="flex items-center justify-between gap-2"><b className="font-semibold">{s.label}</b>{s.key === ST.dataset ? <span className="eyebrow !text-accent">Loaded</span> : null}</div>
            <p className="muted text-[13px] mt-1 mb-3 flex-1">{s.note}</p>
            <div className="flex items-center gap-3 flex-wrap">
              <button className="ghost" data-testid={`scen-${s.key}`} onClick={() => loadScenario(s.key)}>Load</button>
              <span className="muted text-[12px]">CSV: <a href={C.sampleCsvUrl(s.key, "events.csv")}>events</a> <a href={C.sampleCsvUrl(s.key, "seats.csv")}>seats</a> <a href={C.sampleCsvUrl(s.key, "registry.csv")}>registry</a></span>
            </div>
          </div>
        ))}
      </div>
      {SCEN.length === 0 ? <p className="muted">No scenarios to show.</p> : null}
      <h2 id="data-upload">Upload CSVs</h2>
      <form id="up" className="tile toolbar" onSubmit={upload}>
        <div className="grid-auto">
          <div className="field"><span>events.csv</span><FileField name="events" accept=".csv" label="Choose events.csv" /></div>
          <div className="field"><span>seats.csv</span><FileField name="seats" accept=".csv" label="Choose seats.csv" /></div>
          <div className="field"><span>registry.csv</span><FileField name="registry" accept=".csv" label="Choose registry.csv" /></div>
        </div>
        <div className="grid-auto mt-4">
          <label className="field">Verified hours / week (from study, optional) <input name="verified_hours_week" /></label>
          <label className="field">Cost index vs current process (placeholder, optional) <input name="cost_index" /></label>
          <label className="field">Critical risk (optional) <input name="critical_risk" /></label>
        </div>
        <p className="mt-4 flex items-center gap-3"><button className="btn">Run pipeline</button> <span id="upmsg" className="muted">{msg}</span></p>
      </form>
      <h2 id="data-pipe">Pipeline result for this dataset</h2>
      <div className="tile" id="q"><PipelineSummary /></div>
    </>
  );
}
