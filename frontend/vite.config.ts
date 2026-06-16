/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // Warn at 500 kB per chunk; target is keeping the main bundle under 300 kB gzipped
    chunkSizeWarningLimit: 500,
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://backend:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.test.{ts,tsx}",
        "src/main.tsx",
        "src/setupTests.ts",
        "src/types/**",
      ],
      // Anti-regression floor (current ~95/85/83/95); raise as coverage grows.
      thresholds: {
        statements: 90,
        branches: 82,
        functions: 78,
        lines: 90,
      },
    },
  },
});
