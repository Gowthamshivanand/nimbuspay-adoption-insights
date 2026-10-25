import type { J } from "../lib/api";
import { useApp } from "../lib/store";
import { fmt } from "../lib/format";
import { Bars, Header, Kpi } from "../components/ui";
import PipelineSummary from "./Pipeline";

export default function Eng() {
  const { ST } = useApp(); const M = ST.metrics;
  return (
    <>
      <Header title="Engineering reliability" />
      <div className="grid-auto">
        <Kpi id="M10" label={M.M10.label} val={fmt(M.M10.value, "%")} sub={M.M10.note} />
        <Kpi id="M11" label={M.M11.label} val={fmt(M.M11.value, "%")} sub={M.M11.note} />
        <Kpi id="M12" label={M.M12.label} val={M.M12.value} sub={M.M12.note} />
        <Kpi id="M16" label={M.M16.label} val={M.M16.value} />
        <Kpi id="M20" label={M.M20.label} val={fmt(M.M20.value, "%")} sub={M.M20.note} />
      </div>
      <h2>Agents (registry + build type)</h2>
      <div className="tile mb-4">
        <Bars legend={[["M11 failure rate", "accent"], ["M10 error rate", "navy"]]} max={100}
          rows={ST.agents.flatMap((a: J) => [[a.agent + " M11", Number(a.M11) || 0, fmt(a.M11, "%"), "accent"] as [string, number, string, "accent"], [a.agent + " M10", Number(a.M10) || 0, fmt(a.M10, "%"), "navy"] as [string, number, string, "navy"]])} />
      </div>
      <div className="tile !p-0 overflow-auto">
        <table>
          <tbody>
            <tr><th>Agent</th><th>Build type</th><th>Source</th><th>Runs</th><th>M10</th><th>Calls</th><th>M11</th><th>Qualifying</th><th>M20</th></tr>
            {ST.agents.map((a: J, i: number) => (
              <tr key={i}>
                <td>{a.agent} {a.registered ? "" : <span className="tag red">unregistered</span>}<div className="muted">{a.name}</div></td>
                <td>{a.build_type}</td><td className="muted">{a.build_type_source}</td><td>{a.runs}</td><td>{fmt(a.M10, "%")}</td><td>{a.calls}</td><td>{fmt(a.M11, "%")}</td><td>{a.qualifying}</td><td>{fmt(a.M20, "%")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>Pipeline</h2>
      <div className="tile"><PipelineSummary /></div>
    </>
  );
}
