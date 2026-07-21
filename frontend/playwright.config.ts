import { defineConfig, devices } from "@playwright/test";

declare const process: {
  env: Record<string, string | undefined>;
  platform: string;
};

const python =
  process.env.E2E_PYTHON ??
  (process.platform === "win32" ? ".venv\\Scripts\\python.exe" : "python");
const channel = process.env.PLAYWRIGHT_CHANNEL as
  "chrome" | "chromium" | "msedge" | undefined;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:8000",
    channel,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      grep: /@desktop/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile",
      grep: /@mobile/,
      use: { ...devices["Pixel 5"] },
    },
  ],
  webServer: {
    command: `${python} -m uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8000`,
    cwd: "..",
    env: {
      ...process.env,
      ADMIN_USERNAME: "admin",
      ADMIN_PASSWORD: "e2e-password-not-a-secret",
      SESSION_SECRET: "e2e-session-secret-0123456789012345",
      DATA_DIR: ".test-tmp/e2e",
      TZ: "Asia/Shanghai",
    },
    url: "http://127.0.0.1:8000/api/health",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
