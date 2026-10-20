import { useEffect, useState } from "react";
import { api, type J } from "../lib/api";
import { fmt, oc } from "../lib/format";
import { Header } from "../components/ui";

export default function Compare() {
  const [C, setC] = useState<J[] | null>(null);
  useEffect(() => { api("/api/compare").then(setC); }, []);
  return (
    <>
      <Header title="Scenario compare">All 8 synthetic scenarios through the same pipeline and renewal rules.</Header>
      {!C ? <div id="cmp" className="muted">Computing...</div> : (
        <div className="tile !p-0 overflow-auto">
          <table data-testid="compare">
            <tbody>
              <tr><th>Scenario</th><th>Outcome</th><th>M01</th><th>M02</th><th>Vendor MAU / Active</th><th>M11</th><th>Exact %</th><th>M17</th><th>M18</th><th>M19</th></tr>
              {C.map((c) => (
                <tr key={c.key}>
                  <td>{c.label}</td><td className={oc(c.outcome)}><b>{c.outcome}</b></td><td>{fmt(c.M01, "%")}</td><td>{fmt(c.M02, "%")}</td><td>{c.vendor_mau} / {c.active}</td><td>{fmt(c.M11, "%")}</td><td>{c.exact_share}%</td>
                  <td className={c.M17 !== null ? "verified" : ""}>{fmt(c.M17)}</td><td>{fmt(c.M18)}</td>
                  <td className={c.score_state === "red" ? "red" : ""}>{c.M19 ?? "withheld (interim " + c.interim + ")"}{c.score_state === "red" ? " RED" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
