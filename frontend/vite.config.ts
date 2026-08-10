import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

// Two separate backends sit behind this dev server:
//   /api  -> backend/app     (grading API, uvicorn app.main:app --port 8000)
//   /ocr  -> backend/ocr/app (OCR service, uvicorn app.main:app --port 8081)
// The OCR service exposes its routes at the root (/health, /module1/roi, ...),
// so the /ocr prefix is stripped before forwarding.
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
      "/ocr": {
        target: "http://localhost:8081",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/ocr/, ""),
      },
    },
  },
});
