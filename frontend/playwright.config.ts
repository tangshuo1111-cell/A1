import fs from "node:fs";
import { defineConfig, devices } from "@playwright/test";

const systemChromeCandidates = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
];

const systemChromeExecutable = systemChromeCandidates.find((p) => fs.existsSync(p));

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:3001",
    trace: "on-first-retry",
    browserName: "chromium",
    ...(systemChromeExecutable
      ? {
          launchOptions: {
            executablePath: systemChromeExecutable,
          },
        }
      : {}),
  },
  webServer: {
    command:
      "set NODE_OPTIONS=--max-old-space-size=4096 && npm run dev -- --hostname 127.0.0.1 --port 3001",
    url: "http://127.0.0.1:3001",
    reuseExistingServer: true,
    timeout: 180_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
