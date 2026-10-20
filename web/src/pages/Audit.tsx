import { useEffect, useState } from "react";
import * as C from "../api/client";
import type { J } from "../lib/api";
import { Header } from "../components/ui";
import { fmtTs } from "../lib/format";

/* Every cell is rendered as text (React escapes), so a hostile persona string never runs. */
export default function Audit() {
  const [A, setA] = useState<J[] | null>(null);
  useEffect(() => { C.getAudit().then(setA); }, []);
  if (!A) return null;
  return (
    <>
      <Header title="Audit log">Every agent question is logged: time, dataset, persona, outcome, metrics cited, mode.</Header>
      <div className="tile !p-0 overflow-auto">
        <table data-testid="audit">
          <tbody>
            <tr><th>Time (server)</th><th>Dataset</th><th>Persona</th><th>Question</th><th>Result</th><th>Metrics</th><th>Mode</th></tr>
            {A.length ? A.map((a, i) => <tr key={i}><td className="whitespace-nowrap">{fmtTs(a.ts)}</td><td>{a.dataset}</td><td>{a.persona}</td><td>{a.question}</td><td>{a.type}</td><td className="whitespace-nowrap">{(a.metrics || "").split(",").filter(Boolean).join(", ")}</td><td>{a.mode}</td></tr>)
              : <tr><td colSpan={7}>No questions yet</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
