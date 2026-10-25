import { useState } from "react";
import type { J } from "../lib/api";
import { useApp } from "../lib/store";
import { fmt, keepTogether, oc } from "../lib/format";
import { Header, Kpi, Subnav } from "../components/ui";

const EV: Record<string, string> = { e1: "Utilisation", e2: "Verified impact", e3: "Unit economics", e4: "Reliability and governance" };
const STAGES: [string, string][] = [["LF1", "Purchased"], ["LF2", "Assigned"], ["LF3", "Provisioned"], ["LF4", "Active"], ["LF5", "Engaged"], ["LF6", "Habitual"]];

export default function Exec() {
  const { ST, explain } = useApp(); const M = ST.metrics, s = ST.score, rn = ST.renewal, f = ST.funnel;
  const [more, setMore] = useState(false);
  const mau = Number(ST.users.vendor_mau_proxy) || 0;
  const habitual = Number(f.LF6) || 0;
  const paid = Number(f.LF1) || 0;
  const sc = s.value !== null
    ? <span className={s.state === "red" ? "red" : ""} data-testid="score">{s.value}/100{s.state === "red" ? " RED" : ""}</span>
    : <span data-testid="score">Withheld</span>;
  const ids = Object.keys(M).filter((id) => /^M\d\d$/.test(id)).sort();
  const peak = Math.max(paid, 1);
  return (
    <>
      <Header title="Executive view">{ST.label} Dataset: {ST.dataset_label}.</Header>
      <Subnav items={[{ id: "exec-hero", label: "Decision" }, { id: "exec-funnel", label: "Licence funnel" }, { id: "exec-score", label: "M19" }, { id: "exec-metrics", label: "Headlines" }, { id: "exec-catalogue", label: "Metric catalogue" }]} />
      <section id="exec-hero" className="hero-stage">
        <div className="hero-copy">
          <p className="hero-kicker">Vendor MAU against people who actually came back</p>
          <div className="hero-pair">
            <div className="hero-stat"><b>{mau}</b><span>Vendor MAU</span></div>
            <div className="hero-vs">vs</div>
            <div className="hero-stat"><b>{habitual}</b><span>habitual users</span></div>
          </div>
          <p className="hero-foot">of <b>{paid}</b> paid seats</p>
        </div>
        <div className="outcard">
          <div className="eyebrow">Renewal recommendation</div>
          <div className={`out mt-3 ${oc(rn.outcome)}`} data-testid="outcome">{rn.outcome}</div>
          <p className="mt-3 text-[15px] leading-6">{keepTogether(rn.why)}</p>
          <ul className="mt-6 flex flex-col gap-3">
            {Object.entries(EV).map(([k, l]) => {
              const v = rn.evidence[k] === "met" && k === "e2";
              return <li key={k} className="flex items-center justify-between gap-3 text-[14px]"><span>{l}</span><span className={`tag ${v ? "met" : ""}`}>{v ? "verified" : rn.evidence[k]}</span></li>;
            })}
          </ul>
        </div>
      </section>
      <h2 id="exec-funnel">Licence funnel LF1–LF6</h2>
      <div data-testid="funnel">
        <div className="funnel-steps" aria-hidden="true">
          {STAGES.map(([id, name]) => (
            <div key={id} className="funnel-step">
              <strong>{f[id]}</strong>
              <div className="col" style={{ height: Math.max(18, Math.round(92 * Number(f[id]) / peak)), ["--w" as string]: `${Math.round((100 * Number(f[id])) / peak)}%` }} />
              <em>{id} {name}</em>
            </div>
          ))}
        </div>
        <p className="muted text-[14px]">Vendor-style MAU proxy {ST.users.vendor_mau_proxy} vs truly active {f.LF4}. {ST.paid_unused} paid seats have no qualifying use.</p>
      </div>
      <h2 id="exec-score">AI value score (M19), shown beside its pillars, never a team target</h2>
      <div className="grid gap-8 lg:grid-cols-[240px_1fr] items-start">
        <div>
          <div className="text-[13px] text-muted">M19</div>
          <div className="text-[56px] font-semibold leading-none tracking-[-0.04em] mt-2">{sc}</div>
          <p className="mt-3 text-[14px] text-muted">{s.reason}</p>
          {s.interim_index !== null ? <p className="mt-3 text-[14px]">Interim adoption and health index: <b>{s.interim_index}/100</b> (33/25/25/17)</p> : null}
        </div>
        <div className="flex flex-col gap-4">
          {Object.entries(s.pillars).map(([k, v]: [string, J]) => (
            <div key={k} className="pillar">
              <span className="text-[14px]">{k} <span className="text-muted">w {s.weights[k]}</span></span>
              <div className="bar"><i className="navy" style={{ width: `${v ?? 0}%` }} /></div>
              <span className="text-right font-semibold tabular-nums">{v ?? "no data"}</span>
            </div>
          ))}
        </div>
      </div>
      <h2 id="exec-metrics">Headline governed metrics</h2>
      <div className="metric-grid">
        {["M01", "M02", "M04", "M07", "M10", "M17", "M18"].map((id) => (
          <div key={id} className="metric-card">
            <Kpi id={id} label={M[id].label + (M[id].approximate ? " (approx.)" : "")} val={fmt(M[id].value, M[id].unit)} sub={M[id].note} />
            <button type="button" className="text-btn" onClick={() => explain(id)}>View more</button>
          </div>
        ))}
      </div>
      <h2 id="exec-catalogue">Metric catalogue</h2>
      <div className="metric-list">
        <table>
          <tbody>
            <tr><th>ID</th><th>Metric</th><th className="!text-right">Value</th><th></th></tr>
            {(more ? ids : ids.slice(0, 8)).flatMap((id) => [
              <tr key={id} data-metric={id} title="Click: explain this number" className="cursor-pointer">
                <td className="whitespace-nowrap"><b>{id}</b></td>
                <td>{M[id].label}</td>
                <td className="!text-right tabular-nums font-semibold">{fmt(M[id].value, M[id].unit)}</td>
                <td className="!text-right"><button type="button" className="text-btn" onClick={(e) => { e.stopPropagation(); explain(id); }}>View more</button></td>
              </tr>,
            ])}
          </tbody>
        </table>
      </div>
      {ids.length > 8 ? <button type="button" className="ghost mt-3" onClick={() => setMore((v) => !v)}>{more ? "Show fewer" : "Show all"}</button> : null}
    </>
  );
}
