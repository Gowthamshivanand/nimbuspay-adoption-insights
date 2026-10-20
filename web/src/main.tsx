import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { STATIC } from "./api/client";

/* Static demo only (VITE_STATIC=1, GitHub Pages): one slim navy line above the app. Not rendered in the normal build. */
const StaticBanner = () => (
  <div role="note" data-testid="static-banner" className="bg-navy text-white text-[12px] leading-5 px-6 py-1.5 text-center">
    Static demo: recorded responses from the real engine. The live agent runs in the full app.
  </div>
);

createRoot(document.getElementById("root")!).render(<StrictMode>
    {/* MemoryRouter: one route per tab, URL bar unchanged (same as v1: a reload starts on Data). Swap for HashRouter to get deep links. */}
    {STATIC ? <StaticBanner /> : null}
    <MemoryRouter initialEntries={["/data"]}><App /></MemoryRouter>
  </StrictMode>);
