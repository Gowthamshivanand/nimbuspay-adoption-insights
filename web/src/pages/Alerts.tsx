import type { J } from "../lib/api";
import { useApp } from "../lib/store";
import { Header } from "../components/ui";
import { tidy } from "../lib/format";

export default function Alerts() {
  const { ST } = useApp();
  return (
    <>
      <Header title="Alerts">Rule-based alerts from the governed metrics for {ST.dataset_label}.</Header>
      <div className="tile !p-0 overflow-auto">
        <table data-testid="alerts">
          <tbody>
            <tr><th>Severity</th><th>Metric</th><th>Alert</th></tr>
            {ST.alerts.length ? ST.alerts.map((a: J, i: number) => <tr key={i}><td className={`sev-${a.severity}`}>{a.severity}</td><td className="whitespace-nowrap">{a.metric}</td><td>{tidy(a.text)}</td></tr>)
              : <tr><td colSpan={3}>No alerts</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
