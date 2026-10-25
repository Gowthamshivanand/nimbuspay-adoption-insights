import { useState, type ReactNode } from "react";

/* KPI tile. data-metric M\d\d opens "Explain this number" (handled by a document listener in App, as before). */
export function Kpi({ id, label, val, sub = "", eyebrow }: { id: string; label: string; val: ReactNode; sub?: string; eyebrow?: string }) {
  return (
    <div className="kpi" data-metric={id} data-testid={`kpi-${id}`} title="Click: explain this number">
      <div className={eyebrow ? "eyebrow" : "id"}>{eyebrow ?? id}</div>
      <div className="v">{val}</div>
      <div className="l">{label}</div>
      {sub ? <div className="muted text-[12px] mt-0.5">{sub}</div> : <div className="muted text-[12px]"></div>}
    </div>
  );
}

type Tone = "accent" | "navy" | "slate";

/* Horizontal bars: rows of [label, value, display?, tone?] scaled to max. Numbers are in the DOM immediately. */
export function Bars({ rows, max, legend }: { rows: [string, number, ReactNode?, Tone?][]; max: number; legend?: [string, Tone?][] }) {
  return (
    <div>
      {legend ? (
        <div className="legend">
          {legend.map(([name, tone]) => <span key={name}><i className={tone || "accent"} />{name}</span>)}
        </div>
      ) : null}
      <div className="flex flex-col gap-2.5">
        {rows.map(([l, v, n, tone], i) => (
          <div className="bar-row" key={i} title={`${l}: ${typeof n === "string" || typeof n === "number" ? n : v}`}>
            <span className="bar-label">{l}</span>
            <div className="bar" role="img" aria-label={`${l} ${n ?? v}`}><i className={tone || "accent"} style={{ width: `${max ? Math.max(0, Math.min(100, (100 * Number(v)) / max)) : 0}%` }} /></div>
            <span className="bar-val">{n ?? v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Header({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="page-head">
      <h1>{title}</h1>
      {children ? <p className="lede">{children}</p> : null}
    </div>
  );
}

export function Subnav({ items }: { items: { id: string; label: string }[] }) {
  return (
    <div className="subnav" role="navigation" aria-label="On this page">
      {items.map((it) => (
        <a key={it.id} href={"#" + it.id} onClick={(e) => { e.preventDefault(); document.getElementById(it.id)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>{it.label}</a>
      ))}
    </div>
  );
}

/* Decorative count-up. The visible text animates; do not use on values tests read immediately. */
export function CountUp({ n }: { n: number }) {
  return <span className="tabular-nums">{n}</span>;
}

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skel" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      <div className="skel-bar skel-card" />
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skel-bar" style={{ width: `${92 - (i % 3) * 12}%` }} />)}
    </div>
  );
}

export function Modal({ id, onClose, children, width = 740, testid, placement = "center" }: { id: string; onClose: () => void; children: ReactNode; width?: number; testid: string; placement?: "center" | "sheet" }) {
  const sheet = placement === "sheet";
  return (
    <div id={id}>
      <div className={`modal${sheet ? " sheet" : ""}`} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        <div className={`tile why overflow-auto${sheet ? " sheet-card" : ""}`} style={sheet ? undefined : { maxWidth: width, width: "94%", maxHeight: "86vh", boxShadow: "var(--np-shadow-pop)" }} data-testid={testid}>
          {children}
        </div>
      </div>
    </div>
  );
}

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
