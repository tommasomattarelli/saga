import { defineConfig } from "@playwright/test";

// ponytail: mocked golden path — no backend/Docker. Real-backend run is a separate config.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  use: { baseURL: "http://localhost:3000" },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
