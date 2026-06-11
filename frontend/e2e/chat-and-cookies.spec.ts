import { expect, test } from "@playwright/test";

test("chat send flow renders assistant reply via public route", async ({ page }) => {
  await page.route("**/api-proxy/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, status: "ok" }),
    });
  });
  await page.route("**/api-proxy/chat/agno", async (route) => {
    const req = route.request();
    const body = req.postDataJSON() as { message?: string; session_id?: string | null };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        session_id: body.session_id || "e2e-session",
        answer: `assistant:${body.message || ""}`,
        pipeline_ok: true,
        interaction_mode_zh: "快速回答",
        workflow_elapsed_ms: 1234,
        extra: { lane: "fast" },
      }),
    });
  });

  await page.goto("/");
  await page.getByLabel("Message input").fill("hello e2e");
  await page.getByLabel("Send").click();

  await expect(page.getByText(/^hello e2e$/)).toBeVisible();
  await expect(page.getByText("assistant:hello e2e")).toBeVisible();
  await expect(page.getByText(/^快速回答$/)).toBeVisible();
});

test("video cookies modal supports status, upload, and delete", async ({ page }) => {
  let uploaded = false;

  await page.route("**/api-proxy/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, status: "ok" }),
    });
  });
  await page.route("**/api-proxy/config/video_cookies/status", async (route) => {
    const body = uploaded
      ? {
          ok: true,
          source: "file",
          upload_max_bytes: 1048576,
          whitelist_domains: ["bilibili.com", "youtube.com"],
          managed_file: {
            exists: true,
            size_bytes: 128,
            modified_iso: "2026-06-11T08:00:00Z",
            matched_whitelist_domains: ["bilibili.com"],
          },
        }
      : {
          ok: true,
          source: "none",
          upload_max_bytes: 1048576,
          whitelist_domains: ["bilibili.com", "youtube.com"],
          managed_file: {
            exists: false,
            size_bytes: 0,
            modified_iso: null,
            matched_whitelist_domains: [],
          },
        };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.route("**/api-proxy/config/video_cookies/upload", async (route) => {
    uploaded = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        matched_whitelist_domains: ["bilibili.com"],
        merge: {
          new_domains: ["bilibili.com"],
          kept_old_domains: [],
          replaced_domains: [],
        },
      }),
    });
  });
  await page.route("**/api-proxy/config/video_cookies", async (route) => {
    uploaded = false;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, removed: true }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "视频 cookies 设置" }).click();
  await expect(page.getByLabel("视频 cookies 上传引导")).toBeVisible();
  await expect(page.getByText("当前 cookies 状态")).toBeVisible();

  await page
    .locator('input[type="file"]')
    .setInputFiles({
      name: "cookies.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tname\tvalue\n"),
    });

  await expect(page.getByText("上传成功！当前可用站点：bilibili.com")).toBeVisible();
  await expect(page.getByText("已配置 cookies 文件")).toBeVisible();
  await page.getByRole("button", { name: /清除当前 cookies/ }).click();
  await expect(page.getByText("已清除当前 cookies 文件。")).toBeVisible();
});

test("async task flow polls and appends background answer", async ({ page }) => {
  let statusPolls = 0;

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
        session_id: "async-session",
        answer: "已提交后台任务",
        task_id: "task-e2e-1",
        task_status: "pending",
        interaction_mode_zh: "后台任务",
        extra: { pending_kind: "processing_pending" },
      }),
    });
  });
  await page.route("**/api-proxy/tasks/task-e2e-1", async (route) => {
    statusPolls += 1;
    const status = statusPolls >= 2 ? "succeeded" : "running";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        task_id: "task-e2e-1",
        status,
        raw_status: status,
      }),
    });
  });
  await page.route("**/api-proxy/tasks/task-e2e-1/result", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        task_id: "task-e2e-1",
        status: "succeeded",
        raw_status: "succeeded",
        ready: true,
        duration_ms: 1800,
        result: { answer: "后台任务最终答案" },
      }),
    });
  });

  await page.goto("/");
  await page.getByLabel("Message input").fill("需要后台任务");
  await page.getByLabel("Send").click();

  await expect(page.getByText(/^后台任务$/).first()).toBeVisible();
  await expect(page.getByText(/task_id: task-e2e-1/)).toBeVisible();
  await expect(page.getByText("后台任务最终答案")).toBeVisible();
});

test("long video confirmation gate and session restore work end-to-end", async ({ page }) => {
  const seenSessionIds: Array<string | null | undefined> = [];

  await page.route("**/api-proxy/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, status: "ok" }),
    });
  });
  await page.route("**/api-proxy/video/metadata", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        duration_sec: 601,
        title: "超长视频",
        asr_auto_max_sec: 300,
        asr_effective_max_sec: 900,
      }),
    });
  });
  await page.route("**/api-proxy/chat/agno", async (route) => {
    const body = route.request().postDataJSON() as {
      message?: string;
      session_id?: string | null;
      confirm_long_web_video_asr?: boolean;
    };
    seenSessionIds.push(body.session_id);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        session_id: body.session_id || "persisted-session-e2e",
        answer: body.confirm_long_web_video_asr ? "已确认长视频处理" : `echo:${body.message || ""}`,
        interaction_mode_zh: "快速回答",
        workflow_elapsed_ms: 321,
        extra: { lane: "fast" },
      }),
    });
  });

  await page.goto("/");
  await page.getByLabel("Message input").fill("https://www.youtube.com/watch?v=longvideo");
  await page.getByLabel("Send").click();
  await expect(page.getByText("长视频语音识别确认")).toBeVisible();
  await page.getByRole("button", { name: "确认并发送" }).click();
  await expect(page.getByText("已确认长视频处理")).toBeVisible();

  await page.reload();
  await page.getByLabel("Message input").fill("第二轮消息");
  await page.getByLabel("Send").click();
  await expect(page.getByText("echo:第二轮消息")).toBeVisible();
  await expect.poll(() => seenSessionIds).toContain("persisted-session-e2e");
});
