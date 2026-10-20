import { useState, type FormEvent } from "react";
import { api, type J } from "../lib/api";
import { useApp } from "../lib/store";
import { Header } from "../components/ui";
import PipelineSummary from "./Pipeline";

export default function Data() {
  const { ST, setST, SCEN, show, tab, clearChat } = useApp();
  const [msg, setMsg] = useState("");
  const load = async (k: string) => {
    try { const s = await api("/api/load/" + k, { method: "POST" }); setST(s); clearChat(); show(tab === "data" ? "exec" : tab); }
    catch (e) { console.error(e); }                 // legacy: no UI message (e.g. 403 on the read-only public Space)
  };
  const upload = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try { const s = await api("/api/upload", { method: "POST", body: new FormData(e.currentTarget) }); setST(s); show("exec"); }
    catch (x) { setMsg("Rejected: " + (x as Error).message); }
  };
  return (
    <>
      <Header title="Data">Pick a synthetic scenario (each one is real CSV data run through the full pipeline), or upload your own event, seat and registry CSVs.</Header>
      <div className="sc grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(250px,1fr))" }}>
        {SCEN.map((s: J) => (
          <div key={s.key} className={`tile flex flex-col transition-colors duration-fast ${s.key === ST.dataset ? "on !border-accent shadow-[inset_0_0_0_1px_theme(colors.accent)]" : ""}`}>
            <div className="flex items-center justify-between gap-2"><b className="font-semibold">{s.label}</b>{s.key === ST.dataset ? <span className="eyebrow !text-accent">Loaded</span> : null}</div>
            <p className="muted text-[13px] mt-1 mb-3 flex-1">{s.note}</p>
            <div className="flex items-center gap-3 flex-wrap">
              <button className="btn" data-testid={`scen-${s.key}`} onClick={() => load(s.key)}>Load</button>
              <span className="muted text-[12px]">CSV: <a href={`/api/sample/${s.key}/events.csv`}>events</a> <a href={`/api/sample/${s.key}/seats.csv`}>seats</a> <a href={`/api/sample/${s.key}/registry.csv`}>registry</a></span>
            </div>
          </div>
        ))}
      </div>
      <h2>Upload CSVs</h2>
      <form id="up" className="tile" onSubmit={upload}>
        <div className="grid-auto">
          <label className="field">events.csv <input type="file" name="events" accept=".csv" required /></label>
          <label className="field">seats.csv <input type="file" name="seats" accept=".csv" required /></label>
          <label className="field">registry.csv <input type="file" name="registry" accept=".csv" required /></label>
        </div>
        <div className="grid-auto mt-4">
          <label className="field">Verified hours / week (from study, optional) <input name="verified_hours_week" /></label>
          <label className="field">Cost index vs current process (placeholder, optional) <input name="cost_index" /></label>
          <label className="field">Critical risk (optional) <input name="critical_risk" /></label>
        </div>
        <p className="mt-4 flex items-center gap-3"><button className="btn">Run pipeline</button> <span id="upmsg" className="muted">{msg}</span></p>
      </form>
      <h2>Pipeline result for this dataset</h2>
      <div className="tile" id="q"><PipelineSummary /></div>
    </>
  );
}
