import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

createRoot(document.getElementById("root")!).render(<StrictMode>
    {/* MemoryRouter: one route per tab, URL bar unchanged (same as v1: a reload starts on Data). Swap for HashRouter to get deep links. */}
    <MemoryRouter initialEntries={["/data"]}><App /></MemoryRouter>
  </StrictMode>);
