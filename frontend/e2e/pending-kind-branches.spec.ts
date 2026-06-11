import { expect, test } from "@playwright/test";

const PENDING_CASES = [
  {
    kind: "fast_pending",
    label: "快速通道等待中",
    extraAnswer: "fast pending reply",
  },
  {
    kind: "processing_pending",
    label: "后台处理中",
    extraAnswer: "processing pending reply",
    taskId: "task-pending-e2e",
  },
  {
    kind: "material_pending",
    label: "待确认入库",
    extraAnswer: "material ready",
    expectMaterialCard: true,
  },
  {
    kind: "partial_pending",
    label: "部分完成",
    extraAnswer: "partial slice",
    expectPartialCard: true,
  },
] as const;

for (const item of PENDING_CASES) {
  test(`pending_kind ${item.kind} renders correct UI branch`, async ({ page }) => {
    await page.route("**/api-proxy/health", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, status: "ok" }),
      });
    });
    await page.route("**/api-proxy/chat/agno", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session_id: `pending-${item.kind}`,
          answer: item.extraAnswer,
          task_id: "taskId" in item ? item.taskId : undefined,
          task_status: item.kind === "processing_pending" ? "pending" : "succeeded",
          interaction_mode_zh: "快速回答",
          workflow_elapsed_ms: 900,
          extra: { pending_kind: item.kind, lane: "fast" },
        }),
      });
    });
    if (item.kind === "processing_pending" && "taskId" in item) {
      await page.route(`**/api-proxy/tasks/${item.taskId}`, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            ok: true,
            task_id: item.taskId,
            status: "running",
            raw_status: "running",
          }),
        });
      });
    }

    await page.goto("/");
    await page.getByLabel("Message input").fill(`case ${item.kind}`);
    await page.getByLabel("Send").click();

    await expect(page.getByText(item.label).first()).toBeVisible();
    if ("expectMaterialCard" in item && item.expectMaterialCard) {
      await expect(page.getByRole("button", { name: "保存到知识库" })).toBeVisible();
    }
    if ("expectPartialCard" in item && item.expectPartialCard) {
      await expect(page.getByRole("button", { name: "继续追问" })).toBeVisible();
    }
  });
}

test("pending_kind none does not render pending status card", async ({ page }) => {
  await page.route("**/api-proxy/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, status: "ok" }),
    });
  });
  await page.route("**/api-proxy/chat/agno", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        session_id: "pending-none",
        answer: "clean reply",
        interaction_mode_zh: "快速回答",
        extra: { pending_kind: "none", lane: "fast" },
      }),
    });
  });

  await page.goto("/");
  await page.getByLabel("Message input").fill("no pending");
  await page.getByLabel("Send").click();

  await expect(page.getByText("clean reply")).toBeVisible();
  await expect(page.getByText("待确认入库")).toHaveCount(0);
  await expect(page.getByText("部分完成")).toHaveCount(0);
});
