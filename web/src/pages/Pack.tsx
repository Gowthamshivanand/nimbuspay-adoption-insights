import { Header } from "../components/ui";
import { boardpackUrl } from "../api/client";

export default function Pack() {
  return (
    <>
      <Header title="Board pack">One click: a board-ready summary of the current dataset.</Header>
      <p className="flex gap-2 mb-4">
        <a href={boardpackUrl("html")} target="_blank" className="no-underline"><button className="btn" data-testid="pack-html">Open printable pack (Save as PDF)</button></a>
        <a href={boardpackUrl("md")} className="no-underline"><button className="ghost" data-testid="pack-md">Download Markdown</button></a>
      </p>
      <iframe src={boardpackUrl("html")} title="Board pack preview" className="w-full h-[620px] border border-line rounded-tile bg-canvas"></iframe>
    </>
  );
}
