import type { J } from "../lib/api";
import { useApp } from "../lib/store";
import { fmt, keepTogether, oc } from "../lib/format";
import { Bars, Header, Kpi } from "../components/ui";

const EV: Record<string, string> = { e1: "Utilisation", e2: "Verified impact", e3: "Unit economics", e4: "Reliability and governance" };

export default function Exec() {
  const { ST } = useApp(); const M = ST.metrics, s = ST.score, rn = ST.renewal, f = ST.funnel;
  const sc = s.value !== null
    ? <span className={s.state === "red" ? "red" : ""} data-testid="score">{s.value}/100{s.state === "red" ? " RED" : ""}</span>
    : <span data-testid="score">Withheld</span>;
  return (
    <>
      <Header title="Executive view">{ST.label} Dataset: {ST.dataset_label}.</Header>
      <div className="outcard">
        <div className="eyebrow">Renewal recommendation</div>
        <div className={`out mt-1 ${oc(rn.outcome)}`} data-testid="outcome">{rn.outcome}</div>
        <div className="mt-1 max-w-[820px]">{keepTogether(rn.why)}</div>
        <div className="grid-auto mt-4">
          {Object.entries(EV).map(([k, l]) => {
            const v = rn.evidence[k] === "met" && k === "e2";
            return <div key={k} className="text-[13px]"><span className={`tag ${v ? "met" : ""}`}>{v ? "verified" : rn.evidence[k]}</span>{l}</div>;
          })}
        </div>
      </div>
      <h2>AI value score (M19), shown beside its pillars, never a team target</h2>
      <div className="grid-auto">
        <div className="kpi">
          <div className="id">M19 {M.M19.version}</div><div className="v">{sc}</div><div className="l">{s.reason}</div>
          {s.interim_index !== null ? <div className="mt-2 text-[13px]">Interim adoption and health index: <b>{s.interim_index}/100</b> (33/25/25/17)</div> : null}
        </div>
        <div className="tile" style={{ gridColumn: "span 2" }}>
          <Bars rows={Object.entries(s.pillars).map(([k, v]: [string, J]) => [`${k} (w ${s.weights[k]})`, v ?? 0, v ?? "no data"])} max={100} />
        </div>
      </div>
      <h2>Headline governed metrics</h2>
      <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        {["M01", "M02", "M04", "M07", "M10", "M17", "M18"].map((id) => <Kpi key={id} id={id} label={M[id].label + (M[id].approximate ? " (approx.)" : "")} val={fmt(M[id].value, M[id].unit)} sub={M[id].note} />)}
      </div>
      <h2>Licence funnel LF1–LF6</h2>
      <div className="tile" data-testid="funnel">
        <Bars rows={[["LF1 Purchased", f.LF1], ["LF2 Assigned", f.LF2], ["LF3 Provisioned", f.LF3], ["LF4 Active", f.LF4], ["LF5 Engaged", f.LF5], ["LF6 Habitual", f.LF6]]} max={f.LF1} />
        <p className="muted mt-3 text-[13px]">Vendor-style MAU proxy {ST.users.vendor_mau_proxy} vs truly active {f.LF4}. {ST.paid_unused} paid seats have no qualifying use.</p>
      </div>
    </>
  );
}
