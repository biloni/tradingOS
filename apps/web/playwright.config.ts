import { defineConfig, devices } from "@playwright/test";

/**
 * One journey only (ADR-030): the paper-order propose→confirm flow, run
 * against the real dev server + real FastAPI + real seeded Postgres data —
 * not mocked. This intentionally does NOT start the servers itself (no
 * `webServer` block): both `apps/api` (uvicorn) and `apps/web` (`pnpm dev`)
 * must already be running locally, matching this project's existing
 * manual local-dev workflow rather than adding new CI infra.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
