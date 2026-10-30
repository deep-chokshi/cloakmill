import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch:
    process.env.CLOAKMILL_TEST_DISCONNECTED === "1"
      ? "disabled.spec.ts"
      : "workspace.spec.ts",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:4318", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command:
      process.env.CLOAKMILL_TEST_DISCONNECTED === "1"
        ? "npm start"
        : "npm run start:sample",
    url: "http://127.0.0.1:4318",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
