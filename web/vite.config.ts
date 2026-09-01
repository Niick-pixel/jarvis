/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server and API both stay on loopback. The proxy means the browser only ever talks to
// one origin, so there is no CORS surface and nothing to misconfigure outward.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8080",
        changeOrigin: false,
      },
    },
  },
  build: { outDir: "dist", sourcemap: true },
  // One test file, and it needs no DOM: the SSE frame parser is a pure function over a string.
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
