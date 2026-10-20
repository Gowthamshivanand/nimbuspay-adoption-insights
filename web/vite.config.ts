import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build lands in app/web, which FastAPI serves at "/" (assets under /assets/).
// `npm run dev` proxies /api to the backend on 8000 (python -m app).
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "../app/web", emptyOutDir: true, assetsDir: "assets", sourcemap: false },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
