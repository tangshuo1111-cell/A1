import { expect, test } from "@playwright/test";

import {
  buildApiErrorBody,
  mockChatAgnoRoute,
  mockHealthOk,
  sendChatMessage,
} from "./helpers/routes";

test("degraded health plus chat storage error shows connection and assistant hints", async ({
  page,
}) => {
  await page.route("**/api-proxy/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, status: "degraded", latency_ms: 42 }),
    });
  });
  await mockChatAgnoRoute(page, {
    kind: "http",
    status: 503,
    body: buildApiErrorBody({ layer: "storage" }),
  });

  await sendChatMessage(page, "combo degraded + storage");

  await expect(page.getByText("degraded").first()).toBeVisible();
  await expect(page.getByText(/存储\/数据库异常/).first()).toBeVisible();
});

test("chat rate limit then cookies modal still opens after soft error", async ({ page }) => {
  await mockHealthOk(page);
  await page.route("**/api-proxy/config/video_cookies/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        source: "none",
        upload_max_bytes: 1048576,
        whitelist_domains: ["bilibili.com"],
        managed_file: {
          exists: false,
          size_bytes: 0,
          modified_iso: null,
          matched_whitelist_domains: [],
        },
      }),
    });
  });
  await mockChatAgnoRoute(page, {
    kind: "http",
    status: 429,
    body: { ok: false, error: { message: "rate limited" } },
  });

  await sendChatMessage(page, "combo error then cookies");

  await expect(page.getByText(/请求过于频繁/).first()).toBeVisible();
  await expect(page.getByText(/rate limited/).first()).toBeVisible();

  await page.getByRole("button", { name: "视频 cookies 设置" }).click();
  await expect(page.getByLabel("视频 cookies 上传引导")).toBeVisible();
});
