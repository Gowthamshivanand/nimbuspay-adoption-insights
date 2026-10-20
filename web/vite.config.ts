import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build lands in app/web, which FastAPI serves at "/" (assets under /assets/).
// `npm run dev` proxies /api to the backend on 8000 (python -m app).
// Static demo for GitHub Pages (tools/build_pages_demo.sh): VITE_STATIC=1 switches the base path and VITE_OUT_DIR the output; normal builds are unchanged.
const STATIC = process.env.VITE_STATIC === "1";
export default defineConfig({
  plugins: [react()],
  base: STATIC ? "/nimbuspay-adoption-insights/" : "/",
  build: { outDir: (STATIC && process.env.VITE_OUT_DIR) || "../app/web", emptyOutDir: true, assetsDir: "assets", sourcemap: false },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
