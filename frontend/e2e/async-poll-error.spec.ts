import { expect, test } from "@playwright/test";

import { mockAsyncTaskChat, mockHealthOk, sendChatMessage } from "./helpers/routes";

const TASK_ID = "task-poll-fail-e2e";

const POLL_ERROR_BRANCHES = [
  {
    id: "task_status_http_500",
    mockStatus: 500,
    body: { ok: false, error: { message: "task status unavailable" } },
    visible: /task status unavailable/,
  },
  {
    id: "task_status_abort",
    mockStatus: "abort" as const,
    body: null,
    visible: /Failed|fetch|任务状态查询失败/i,
  },
] as const;

for (const item of POLL_ERROR_BRANCHES) {
  test(`async poll error branch ${item.id} surfaces pollError`, async ({ page }) => {
    await mockHealthOk(page);
    await mockAsyncTaskChat(page, TASK_ID);

    await page.route(`**/api-proxy/tasks/${TASK_ID}`, async (route) => {
      if (item.mockStatus === "abort") {
        await route.abort("failed");
        return;
      }
      await route.fulfill({
        status: item.mockStatus,
        contentType: "application/json",
        body: JSON.stringify(item.body),
      });
    });

    await sendChatMessage(page, `poll error ${item.id}`);

    await expect(page.getByText(/task_id: task-poll-fail-e2e/)).toBeVisible();
    await expect(page.getByText(item.visible).first()).toBeVisible();
  });
}
