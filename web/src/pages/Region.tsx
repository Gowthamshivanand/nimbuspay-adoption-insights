import type { J } from "../lib/api";
import { useApp } from "../lib/store";
import { fmt } from "../lib/format";
import { Bars, Header, Kpi, Subnav } from "../components/ui";

export default function Region() {
  const { ST } = useApp();
  return (
    <>
      <Header title="Regional adoption and intervention">Teams under {5} assigned seats are suppressed (small-group rule); region totals shown.</Header>
      <Subnav items={ST.regions.map((g: J) => ({ id: "reg-" + g.region, label: g.region }))} />
      <div className="flex flex-col gap-4">
        {ST.regions.map((g: J) => (
          <section key={g.region} id={"reg-" + g.region} className="tile">
            <div className="flex items-center gap-2"><b className="font-semibold text-[15px]">{g.region}</b> {g.launch_cohort ? <span className="tag">launch cohort</span> : null}</div>
            <div className="grid-auto mt-3">
              <Kpi id="M01" label="Utilisation" val={fmt(g.M01, "%")} sub={`${g.active}/${g.assigned}`} />
              <Kpi id="M02" label="Habitual" val={fmt(g.M02, "%")} sub={`${g.habitual}/${g.assigned}`} />
              <Kpi id="M11" label="Connector failures" val={fmt(g.M11, "%")} />
            </div>
            <div className="mt-4 overflow-auto">
              <Bars max={100} legend={[["M01 utilisation", "accent"]]} rows={[[g.region + " M01", Number(g.M01) || 0, fmt(g.M01, "%"), "accent"]]} />
              <table className="mt-3">
              <tbody>
                <tr><th>Team</th><th>Purchased</th><th>Assigned</th><th>Active</th><th>Habitual</th></tr>
                {g.teams.map((t: J, i: number) => t.suppressed
                  ? <tr key={i}><td>{t.team}</td><td colSpan={4} className="muted">suppressed (&lt; 5 assigned)</td></tr>
                  : <tr key={i}><td>{t.team}</td><td>{t.purchased}</td><td>{t.assigned}</td><td>{t.active}</td><td>{t.habitual}</td></tr>)}
              </tbody>
            </table>
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
