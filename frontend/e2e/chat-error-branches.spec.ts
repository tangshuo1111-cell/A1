import { expect, test } from "@playwright/test";

import {
  buildApiErrorBody,
  mockChatAgnoRoute,
  mockHealthOk,
  sendChatMessage,
} from "./helpers/routes";

const CHAT_ERROR_BRANCHES = [
  {
    id: "network_offline",
    mock: { kind: "abort" as const },
    assistant: /当前无法连接后端服务/,
    softError: /无法连接到后端/,
  },
  {
    id: "http_429",
    mock: {
      kind: "http" as const,
      status: 429,
      body: { ok: false, error: { message: "rate limited" } },
    },
    assistant: /请求过于频繁/,
    softError: /rate limited/,
  },
  {
    id: "error_layer_storage",
    mock: {
      kind: "http" as const,
      status: 503,
      body: buildApiErrorBody({ layer: "storage" }),
    },
    assistant: /存储\/数据库异常/,
  },
  {
    id: "error_layer_tool",
    mock: {
      kind: "http" as const,
      status: 502,
      body: buildApiErrorBody({ layer: "tool" }),
    },
    assistant: /工具层异常/,
  },
  {
    id: "error_layer_route",
    mock: {
      kind: "http" as const,
      status: 502,
      body: buildApiErrorBody({ layer: "route" }),
    },
    assistant: /编排\/路由异常/,
  },
  {
    id: "error_layer_workflow",
    mock: {
      kind: "http" as const,
      status: 502,
      body: buildApiErrorBody({ layer: "workflow" }),
    },
    assistant: /编排\/路由异常/,
  },
  {
    id: "http_503_generic",
    mock: {
      kind: "http" as const,
      status: 503,
      body: { ok: false, error: "upstream_unavailable" },
    },
    assistant: /服务器暂时异常.*HTTP 503/,
    softError: /Service Unavailable|HTTP 503/i,
  },
  {
    id: "http_403_with_message",
    mock: {
      kind: "http" as const,
      status: 403,
      body: { ok: false, error: { message: "forbidden resource" } },
    },
    assistant: /请求未能完成（403）：forbidden resource/,
    softError: /forbidden resource/,
  },
  {
    id: "http_503_with_request_id",
    mock: {
      kind: "http" as const,
      status: 503,
      body: buildApiErrorBody({ requestId: "req-e2e-503" }),
    },
    assistant: /服务器暂时异常（HTTP 503）.*req-e2e-503/,
  },
] as const;

for (const item of CHAT_ERROR_BRANCHES) {
  test(`chat error branch ${item.id} shows assistant-facing copy`, async ({ page }) => {
    await mockHealthOk(page);
    await mockChatAgnoRoute(page, item.mock);
    await sendChatMessage(page, `trigger ${item.id}`);

    await expect(page.getByText(item.assistant).first()).toBeVisible();
    if ("softError" in item && item.softError) {
      await expect(page.getByText(item.softError).first()).toBeVisible();
    }
  });
}
