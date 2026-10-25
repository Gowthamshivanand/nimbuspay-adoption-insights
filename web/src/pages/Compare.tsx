import { useEffect, useState } from "react";
import * as C from "../api/client";
import type { J } from "../lib/api";
import { fmt, oc } from "../lib/format";
import { Header, Skeleton } from "../components/ui";

const NUM = "!text-right tabular-nums whitespace-nowrap";

export default function Compare() {
  const [rows, setC] = useState<J[] | null>(null);
  useEffect(() => { C.getCompare().then(setC); }, []);
  return (
    <>
      <Header title="Scenario compare">All 8 synthetic scenarios through the same pipeline and renewal rules.</Header>
      {!rows ? <div id="cmp"><Skeleton /><p className="muted mt-2">Computing...</p></div> : (
        <div className="tile !p-0 overflow-auto">
          <table data-testid="compare">
            <tbody>
              <tr><th>Scenario</th><th>Outcome</th><th className="!text-right">M01</th><th className="!text-right">M02</th><th className="!text-right">Vendor MAU / Active</th><th className="!text-right">M11</th><th className="!text-right">Exact %</th><th className="!text-right">M17</th><th className="!text-right">M18</th><th className="!text-right">M19</th></tr>
              {rows.map((c) => (
                <tr key={c.key}>
                  <td>{c.label}</td><td className={`whitespace-nowrap ${oc(c.outcome)}`}><b>{c.outcome}</b></td><td className={NUM}>{fmt(c.M01, "%")}</td><td className={NUM}>{fmt(c.M02, "%")}</td><td className={NUM}>{c.vendor_mau} / {c.active}</td><td className={NUM}>{fmt(c.M11, "%")}</td><td className={NUM}>{c.exact_share}%</td>
                  <td className={`${NUM} ${c.M17 !== null ? "verified" : ""}`}>{fmt(c.M17)}</td><td className={NUM}>{fmt(c.M18)}</td>
                  <td className={`${NUM} ${c.score_state === "red" ? "red" : ""}`}>{c.M19 ?? "withheld (interim " + c.interim + ")"}{c.score_state === "red" ? <> · <span className="inline-block w-2 h-2 rounded-full bg-critical align-middle" aria-hidden="true"></span> Red</> : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
