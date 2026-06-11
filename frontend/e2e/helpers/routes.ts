import type { Page } from "@playwright/test";

export async function mockHealthOk(page: Page): Promise<void> {
  await page.route("**/api-proxy/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, status: "ok" }),
    });
  });
}

export type ChatRouteMock =
  | { kind: "abort" }
  | { kind: "http"; status: number; body?: unknown };

export async function mockChatAgnoRoute(page: Page, mock: ChatRouteMock): Promise<void> {
  await page.route("**/api-proxy/chat/agno", async (route) => {
    if (mock.kind === "abort") {
      await route.abort("failed");
      return;
    }
    await route.fulfill({
      status: mock.status,
      contentType: "application/json",
      body: JSON.stringify(mock.body ?? { ok: false }),
    });
  });
}

export function buildApiErrorBody(opts: {
  layer?: string;
  message?: string;
  requestId?: string;
}): Record<string, unknown> {
  return {
    ok: false,
    request_id: opts.requestId,
    error: {
      message: opts.message ?? "synthetic error",
      error_layer: opts.layer,
    },
  };
}

export async function sendChatMessage(page: Page, text: string): Promise<void> {
  await page.goto("/");
  await page.getByLabel("Message input").fill(text);
  await page.getByLabel("Send").click();
}

export async function mockAsyncTaskChat(
  page: Page,
  taskId: string,
  answer = "已提交后台任务",
): Promise<void> {
  await page.route("**/api-proxy/chat/agno", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        session_id: "async-error-session",
        answer,
        task_id: taskId,
        task_status: "pending",
        interaction_mode_zh: "后台任务",
        extra: { pending_kind: "processing_pending" },
      }),
    });
  });
}
