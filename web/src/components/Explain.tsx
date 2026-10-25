/* "Explain this number" (metric lineage) and "Why this number?" (per-answer provenance). Content as in the legacy UI. */
import type { J } from "../lib/api";
import type { ChatMsg } from "../lib/store";
import { BRAIN, symbols } from "../lib/format";
import { Modal } from "./ui";

export function LineageModal({ L, onClose }: { L: J; onClose: () => void }) {
  return (
    <Modal id="lin" onClose={onClose} width={740} testid="lineage" placement="sheet">
      <div className="sheet-head">
        <h2 className="!mt-0 !text-[18px]">Explain this number: {L.metric} {symbols(L.name)} = {L.value ?? "withheld"}{L.unit === "%" ? "%" : ""}</h2>
        <button className="ghost" data-testid="lin-close" onClick={onClose}>Close</button>
      </div>
      <table>
        <tbody>
          <tr><th>Version</th><td>{L.version}{L.approximate ? " (approximate)" : ""}</td></tr>
          <tr><th>Formula</th><td>{symbols(L.formula)}</td></tr>
          <tr><th>Owner</th><td>{L.owner} (proposed role: {L.proposed_owner_role})</td></tr>
          <tr><th>Freshness</th><td>Data as of {L.freshness.data_as_of}; {L.freshness.late_events} late events; {L.freshness.after_close_rows} rows after close (restatement)</td></tr>
          <tr><th>Source tables</th><td>{L.sources.map((s: string, i: number) => <div key={i}>{symbols(s)}</div>)}</td></tr>
          <tr><th>Pipeline</th><td>{L.pipeline.map(symbols).join(" \u2192 ")}</td></tr>
          <tr><th>Missing-data rule</th><td>{symbols(L.missing_data_rule)}</td></tr>
          <tr><th>Tests</th><td>{symbols(L.tests)}</td></tr>
          <tr><th>Note</th><td>{symbols(L.note)}</td></tr>
        </tbody>
      </table>
      {L.sql ? (
        <><h2>SQL</h2><pre>{L.sql}</pre><div className="muted mt-2">Re-run now on the warehouse: <b className="text-ink">{JSON.stringify(L.sql_result)}</b></div></>
      ) : <p className="muted mt-3">No SQL: this metric comes from an agreed input or from other metrics (see sources).</p>}
    </Modal>
  );
}

export function WhyModal({ m, L, ST, onClose }: { m: ChatMsg; L: (J | null)[]; ST: J; onClose: () => void }) {
  const b = m.bot, ids = [...new Set<string>((b.citations || []).map((c: J) => c.metric))];
  return (
    <Modal id="why" onClose={onClose} width={820} testid="why-panel">
      <h2 className="!mt-0 !text-[18px]">Why this number?</h2>
      <p className="muted">{m.q}</p>
      <table className="mt-3">
        <tbody>
          <tr><th>Answered by</th><td>{b.answered_by ? <><b>{b.answered_by}</b>{b.remote_fallback ? " (" + b.remote_fallback + ")" : ""}, </> : null}{BRAIN[b.brain] || b.brain} ({b.mode}), {String(b.latency_ms)} ms{typeof b.confidence === "number" ? `, confidence ${Math.round(b.confidence * 100)}% (${b.confidence_basis})` : ""}</td></tr>
          <tr><th>Role</th><td>{b.persona} (scope enforced on the server)</td></tr>
          <tr><th>Data as of</th><td data-testid="why-asof">{b.data_as_of}</td></tr>
          <tr><th>Rows returned</th><td data-testid="why-rows">{b.sql_executed ? String(b.row_count) : b.sql ? "Figure from the governed pipeline; SQL below is the equivalent query, not re-run for this answer" : "No SQL: figure from the governed pipeline or an agreed input"}</td></tr>
        </tbody>
      </table>
      <h2>Metric definitions</h2>
      <table data-testid="why-defs">
        <tbody>
          <tr><th>ID and version</th><th>Metric</th><th>Definition</th><th>Owner</th></tr>
          {ids.map((id, k) => {
            const l = L[k], mm = ST.metrics[id];
            return (
              <tr key={id}>
                <td><b>{id}</b> {l ? l.version : (b.citations.find((c: J) => c.metric === id) || {}).version}</td>
                <td>{l ? l.name : mm ? mm.label : "Licence funnel stage"}</td>
                <td>{symbols(l ? l.formula : mm ? mm.note : "Seat funnel stage LF1–LF6 from the seats and events tables")}</td>
                <td className="muted">{l ? l.owner : ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {b.sql ? <><h2>SQL run</h2><pre data-testid="why-sql">{b.sql}</pre></> : null}
      <p className="mt-5"><button className="ghost" data-testid="why-close" onClick={onClose}>Close</button></p>
    </Modal>
  );
}
