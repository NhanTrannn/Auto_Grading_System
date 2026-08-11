import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

// One backend behind this dev server: /api -> backend/app on port 8000,
// which serves grading, the pipeline, the barem library and the OCR modules
// (/api/v1/ocr/*). There was a second proxy entry, /ocr -> port 8081, back
// when the OCR modules ran as their own FastAPI service.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
