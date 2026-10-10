/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

// The SPA talks to Django through this proxy so the browser sees one origin:
// session cookies and CSRF work without any CORS configuration in development.
const apiTarget = process.env.VITE_API_PROXY ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false },
      "/admin": { target: apiTarget, changeOrigin: false },
      "/static": { target: apiTarget, changeOrigin: false },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: { provider: "v8", include: ["src/**/*.{ts,tsx}"], exclude: ["src/api/schema.d.ts"] },
  },
});
