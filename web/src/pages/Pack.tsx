import { useRef, type MouseEvent } from "react";
import { Header } from "../components/ui";
import { boardpackUrl } from "../api/client";

/* The pack HTML comes from the backend unchanged (/api/boardpack?format=html). It is same-origin, so the front end restyles it
   on display: Inter, navy headings, hairline rules, and a navy (AA) print button instead of white on orange. */
const PACK_CSS = `body{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif!important;color:#1D1D1F!important}
h1,h2{color:#0B2E59!important;font-weight:600!important}h1{font-size:22px!important}
h2{font-size:16px!important;border-bottom:1px solid #E5E7EB!important;padding-bottom:4px}
td{border:1px solid #E5E7EB!important}tr:first-child td{background:#F9FAFB!important;font-weight:600}
button{background:#0B2E59!important;color:#fff!important;font:500 13px Inter,system-ui,sans-serif!important;border-radius:8px!important;padding:7px 14px!important;cursor:pointer}`;
const EMBED_CSS = PACK_CSS + "button{display:none!important}body{margin:20px 28px!important}";   // the preview has no second print action

function restyle(doc: Document | null | undefined, css: string) {
  if (!doc || !doc.head || doc.getElementById("np-v2-style")) return;
  const st = doc.createElement("style"); st.id = "np-v2-style"; st.textContent = css; doc.head.appendChild(st);
  /* Copy tidy on display only (the backend template and the Markdown export are unchanged): spaced hyphen -> colon. */
  const walk = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    if (n.nodeValue && n.nodeValue.includes("SYNTHETIC DATA - illustrative")) n.nodeValue = n.nodeValue.replace("SYNTHETIC DATA - illustrative", "SYNTHETIC DATA: illustrative");
  }
}

export default function Pack() {
  const frame = useRef<HTMLIFrameElement>(null);
  /* Same as v1: opens the printable pack in a new tab. The new tab is restyled once it has loaded. */
  const openPack = (e: MouseEvent) => {
    const w = window.open(boardpackUrl("html"), "_blank");
    if (!w) return;                                   // popup blocked: let the plain link open it
    e.preventDefault();
    let n = 0; const t = window.setInterval(() => {
      n += 1;
      try { if (w.document.readyState === "complete" && w.location.pathname === "/api/boardpack") { restyle(w.document, PACK_CSS); window.clearInterval(t); } } catch { window.clearInterval(t); }
      if (n > 100) window.clearInterval(t);
    }, 100);
  };
  return (
    <>
      <Header title="Board pack">One click: a board-ready summary of the current dataset.</Header>
      <p className="flex gap-2 mb-4">
        <a href={boardpackUrl("html")} target="_blank" className="no-underline" onClick={openPack}><button className="btn" data-testid="pack-html">Open printable pack (Save as PDF)</button></a>
        <a href={boardpackUrl("md")} className="no-underline"><button className="ghost" data-testid="pack-md">Download Markdown</button></a>
      </p>
      <iframe ref={frame} src={boardpackUrl("html")} title="Board pack preview" data-testid="pack-frame" onLoad={() => restyle(frame.current?.contentDocument, EMBED_CSS)}
        className="w-full h-[620px] border border-line rounded-tile bg-canvas"></iframe>
    </>
  );
}
