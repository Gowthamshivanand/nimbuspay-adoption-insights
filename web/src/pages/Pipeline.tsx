import { useApp } from "../lib/store";

/* Pipeline counting summary (Data and Engineering screens). */
export default function PipelineSummary() {
  const { ST } = useApp(); const q = ST.quality, g = ST.grouping;
  return (
    <div className="leading-7">
      Raw rows <b>{q.raw_rows}</b> {"->"} duplicates removed {q.duplicates}, after close {q.after_close} {"->"} clean events <b>{q.clean_events}</b> (late {q.late}, logins {q.logins}, never usage)<br />
      {"->"} logical interactions <b data-testid="interactions">{g.interactions}</b> ({g.exact} exact by interaction ID, {g.approximate} approximate by sessionisation) {"->"} qualifying <b>{g.qualifying}</b>. Raw events overstate use <b>{g.inflation}x</b>. Restated after late rows: {g.restated_qualifying}.
      {g.truth_questions ? <><br />Synthetic ground truth: {g.truth_questions} real questions; sessionisation error {g.sessionisation_error}.</> : null}
      {q.issues.length ? <><br />Validation notes: {q.issues.join("; ")}</> : null}
    </div>
  );
}
