// Lakelink Fiber — Provable Resilience Intelligence frontend build (P24-APP-BUILD-SCAFFOLD).
// Databricks Apps runs `npm install` + `npm run build` at deploy time because package.json
// sits at the app root. Output goes to src/resilience_scorecard/__dist__, which the FastAPI
// backend (core.py) serves as an SPA.
import { fileURLToPath } from "node:url";
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";

const appRoot = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(appRoot, "src/resilience_scorecard/ui");
const distDir = path.resolve(appRoot, "src/resilience_scorecard/__dist__");

export default defineConfig({
  root: uiRoot,
  plugins: [
    // Must run before react(): generates routeTree.gen.ts from ui/routes/*.tsx
    TanStackRouterVite({
      target: "react",
      routesDirectory: path.resolve(uiRoot, "routes"),
      generatedRouteTree: path.resolve(uiRoot, "routeTree.gen.ts"),
      autoCodeSplitting: true,
    }),
    react(),
  ],
  resolve: {
    alias: { "@": uiRoot },
  },
  build: {
    outDir: distDir,
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
