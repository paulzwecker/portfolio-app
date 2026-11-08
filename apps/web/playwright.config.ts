import { defineConfig, devices } from "@playwright/test";
import { browserSettings } from "../../scripts/browser-environment.mjs";

const settings = browserSettings(process.env);
const webServerCommand = settings.production
  ? "node ../../scripts/web.mjs start"
  : "node ../../scripts/web.mjs dev";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: 2,
  expect: { timeout: 15_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: settings.baseURL,
    httpCredentials: settings.httpCredentials,
    trace: settings.managed ? "off" : "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: [
    ...(settings.managed
      ? [
          {
            command: "node e2e/fixtures/sensitivity-api.mjs",
            url: `${settings.apiURL}/health/live`,
            reuseExistingServer: false,
          },
        ]
      : []),
    {
      command: webServerCommand,
      url: settings.baseURL,
      reuseExistingServer: settings.reuseExistingServer,
      timeout: 120_000,
    },
  ],
});
