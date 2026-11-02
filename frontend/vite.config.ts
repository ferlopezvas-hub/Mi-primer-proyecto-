/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // La demo se publica como página estática: rutas relativas y un único bundle.
  base: mode === "demo" ? "./" : "/",
  server: { port: 5173, proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" } },
  preview: { port: 4173, proxy: { "/api": "http://localhost:8000" } },
  build: {
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    outDir: mode === "demo" ? "dist-demo" : "dist",
    rollupOptions: mode === "demo" ? { output: { inlineDynamicImports: true } } : {},
  },
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"], globals: true },
}));
