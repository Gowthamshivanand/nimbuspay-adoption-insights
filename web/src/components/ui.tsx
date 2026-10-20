import { useState, type ReactNode } from "react";

/* KPI tile. data-metric M\d\d opens "Explain this number" (handled by a document listener in App, as before). */
export function Kpi({ id, label, val, sub = "", eyebrow }: { id: string; label: string; val: ReactNode; sub?: string; eyebrow?: string }) {
  /* eyebrow: a plain grey label for tiles whose slot is not a metric ID (e.g. "Funnel check"); data-metric/testid unchanged. */
  return (
    <div className="kpi" data-metric={id} data-testid={`kpi-${id}`} title="Click: explain this number">
      <div className={eyebrow ? "eyebrow" : "id"}>{eyebrow ?? id}</div>
      <div className="v">{val}</div>
      <div className="l">{label}</div>
      {sub ? <div className="muted text-[12px] mt-0.5">{sub}</div> : <div className="muted text-[12px]"></div>}
    </div>
  );
}

/* Horizontal bars: rows of [label, value, display?] scaled to max. */
export function Bars({ rows, max }: { rows: [string, number, ReactNode?][]; max: number }) {
  return (
    <div className="flex flex-col gap-2">
      {rows.map(([l, v, n], i) => (
        <div className="flex gap-3 items-center" key={i}>
          <span className="w-[170px] shrink-0 text-muted text-[13px]">{l}</span>
          <div className="bar flex-1"><i style={{ width: `${max ? (100 * v) / max : 0}%` }}></i></div>
          <span className="w-[80px] text-right tabular-nums">{n ?? v}</span>
        </div>
      ))}
    </div>
  );
}

export function Header({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-6">
      <h1>{title}</h1>
      {children ? <p className="lede">{children}</p> : null}
    </div>
  );
}

/* Modal: backdrop click closes; wrapper id lets tests wait for it to detach (#lin, #why). */
export function Modal({ id, onClose, children, width = 740, testid }: { id: string; onClose: () => void; children: ReactNode; width?: number; testid: string }) {
  return (
    <div id={id}>
      <div className="modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        <div className="tile why overflow-auto shadow-[0_8px_30px_rgba(0,0,0,0.08)]" style={{ maxWidth: width, width: "94%", maxHeight: "86vh" }} data-testid={testid}>
          {children}
        </div>
      </div>
    </div>
  );
}

/* Styled file picker: the real <input type=file> stays in the form (same name, accept, required, testid) but is visually hidden. */
export function FileField({ name, accept, label, testid, required = true }: { name: string; accept: string; label: string; testid?: string; required?: boolean }) {
  const [file, setFile] = useState("");
  return (
    <span className="inline-flex items-center gap-2 min-w-0">
      <label className="ghost cursor-pointer whitespace-nowrap focus-within:border-navy">
        {label}
        <input type="file" name={name} accept={accept} required={required} data-testid={testid} className="sr-only"
          onChange={(e) => setFile(e.currentTarget.files && e.currentTarget.files[0] ? e.currentTarget.files[0].name : "")} />
      </label>
      <span className="muted text-[12px] truncate">{file || "No file yet"}</span>
    </span>
  );
}
