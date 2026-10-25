import { useEffect, useState, type FormEvent } from "react";
import * as C from "../api/client";
import type { J } from "../lib/api";
import { FileField, Header, Kpi, Skeleton } from "../components/ui";
import { plural, sentences } from "../lib/format";

export default function Seats() {
  const [r, setR] = useState<J>(null), [x, setX] = useState<J>(null), [msg, setMsg] = useState("");
  useEffect(() => { C.getReclaim().then(setR); }, []);
  if (!r) return <Skeleton rows={5} />;
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try { setX(await C.reconcile(new FormData(e.currentTarget))); } catch (y) { setMsg("Rejected: " + (y as Error).message); }
  };
  return (
    <>
      <Header title="Seat reclaim finder">{r.note} {r.label}</Header>
      <div className="grid-auto">
        <Kpi id="LF1" label="Purchased seats" val={r.purchased} />
        <Kpi id="LF-CHK" eyebrow="Funnel check" label="Reclaimable at renewal" val={<span data-testid="reclaimable">{r.reclaimable}</span>} />
        <Kpi id="Placeholder" eyebrow="Placeholder input" label={`Reclaim value at ${r.unit_price} price units/seat (placeholder)`} val={r.reclaim_value + " units"} />
      </div>
      <div className="tile !p-0 overflow-auto mt-4">
        <table data-testid="reclaim">
          <tbody>
            <tr><th>Team</th><th>Region</th><th>Purchased</th><th>Never assigned</th><th>Assigned, not provisioned</th><th>Provisioned, idle</th><th>Active</th><th>Headroom kept</th><th>Reclaimable</th><th>Action</th></tr>
            {r.rows.map((t: J, i: number) => <tr key={i}><td className="whitespace-nowrap min-w-[96px]">{t.team}</td><td className="whitespace-nowrap">{t.region}</td><td>{t.purchased}</td><td>{t.never_assigned}</td><td>{t.not_provisioned}</td><td>{t.provisioned_idle}</td><td>{t.active}</td><td>{t.buffer_kept}</td><td><b>{t.reclaimable}</b></td><td className="muted">{sentences(t.action)}</td></tr>)}
          </tbody>
        </table>
      </div>
      <h2>Vendor bill reconciler</h2>
      <p className="lede mb-3">Upload the vendor's invoice CSV (invoice_id, team_id, billed_seats, optional unit_price) to compare billed vs purchased vs assigned vs active seats. <a href={C.reconcileSampleCsvUrl}>Download the sample invoice</a>.</p>
      <form id="invf" className="tile flex items-center gap-3 flex-wrap" onSubmit={submit}>
        <FileField name="invoice" accept=".csv" label="Choose invoice CSV" /><button className="btn">Reconcile</button>
        <button type="button" className="ghost" data-testid="inv-sample" id="inv-sample" onClick={async () => setX(await C.reconcileSample())}>Use sample invoice</button>
        <span id="invmsg" className="muted">{msg}</span>
      </form>
      <div id="inv-out" className="mt-4">
        {x ? (
          <>
            <p className="mb-3">Billed <b>{x.totals.billed}</b> | purchased {x.totals.purchased} | assigned {x.totals.assigned} | active {x.totals.active} | <span className="red">{x.totals.mismatches} {plural(x.totals.mismatches, "mismatch", "mismatches")}</span>, {x.totals.reviews} to review | billed for seats with no qualifying use: {x.totals.unused_value} price units (placeholder)</p>
            <div className="tile !p-0 overflow-auto">
              <table data-testid="reconcile">
                <tbody>
                  <tr><th>Team</th><th>Billed</th><th>Purchased</th><th>Assigned</th><th>Active</th><th>Status</th><th>Flags</th></tr>
                  {x.rows.map((r: J, i: number) => <tr key={i}><td className="whitespace-nowrap min-w-[96px]">{r.team}</td><td>{r.billed}</td><td>{r.purchased}</td><td>{r.assigned}</td><td>{r.active}</td><td className={r.status === "mismatch" ? "sev-high" : r.status === "review" ? "sev-medium" : ""}>{r.status}</td><td>{r.flags.map((f: string, k: number) => <div key={k}>{f}</div>)}</td></tr>)}
                </tbody>
              </table>
            </div>
            <p className="muted mt-3 text-[13px]">{x.label}</p>
          </>
        ) : null}
      </div>
    </>
  );
}
