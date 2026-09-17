import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig, loadEnv } from "vite";

// One backend behind this dev server: /api -> backend/app, which serves
// grading, the pipeline, the barem library and the OCR modules
// (/api/v1/ocr/*). There was a second proxy entry, /ocr -> port 8081, back
// when the OCR modules ran as their own FastAPI service.
export default defineConfig(({ mode }) => {
  // vite.config.ts runs in Node, not the browser, so it reads `.env` via
  // loadEnv() rather than `import.meta.env` (which is what browser code
  // uses — see DashboardLayout.tsx's BACKEND_PORT). Both read the SAME
  // VITE_BACKEND_PORT so there's one place to change it, not three.
  //
  // Default 8000 is FastAPI's usual port; override in `.env`
  // (VITE_BACKEND_PORT=...) when something else on the machine already
  // holds it — this dev machine does, backend runs on 8001 here (see
  // backend/docker-compose.prod.yaml).
  const env = loadEnv(mode, process.cwd(), "");
  const backendUrl = `http://localhost:${env.VITE_BACKEND_PORT || "8000"}`;

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": backendUrl,
      },
    },
    // `vite preview` (serves the production `dist/` build) does NOT inherit
    // `server.proxy` — it reads its own `preview.proxy` — so without this the
    // built app's relative "/api/v1" fetches (see src/services/api.ts) 404
    // once served outside the dev server. Same backend target as dev.
    preview: {
      port: 4173,
      proxy: {
        "/api": backendUrl,
      },
    },
  };
});
