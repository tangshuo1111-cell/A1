import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  postChat: vi.fn(),
  fetchWebVideoMetadata: vi.fn(),
}));

vi.mock("@/lib/videoUrl", () => ({
  extractFirstWhitelistVideoUrl: vi.fn(() => null),
}));

import { postChat } from "@/lib/api";
import { useChatSession } from "./useChatSession";

const mockPost = postChat as ReturnType<typeof vi.fn>;

function makeOpts() {
  return {
    connection: "ok" as const,
    setConnection: vi.fn(),
    setSoftError: vi.fn(),
    applyVideoSignal: vi.fn(),
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
});

describe("useChatSession — session 持久化", () => {
  it("收到 session_id 后写入 sessionStorage", async () => {
    mockPost.mockResolvedValueOnce({
      ok: true,
      session_id: "sess-abc",
      answer: "你好",
    });

    const { result } = renderHook(() => useChatSession(makeOpts()));

    await act(async () => {
      result.current.setInput("你好");
    });
    await act(async () => {
      await result.current.send();
    });

    expect(sessionStorage.getItem("maqa_session_id")).toBe("sess-abc");
  });

  it("刷新后从 sessionStorage 恢复 session_id 并在下一轮带上", async () => {
    sessionStorage.setItem("maqa_session_id", "sess-restored");

    mockPost.mockResolvedValueOnce({
      ok: true,
      session_id: "sess-restored",
      answer: "继续",
    });

    const { result } = renderHook(() => useChatSession(makeOpts()));

    await act(async () => {
      result.current.setInput("继续聊");
    });
    await act(async () => {
      await result.current.send();
    });

    expect(mockPost).toHaveBeenCalledWith(
      expect.objectContaining({ session_id: "sess-restored" }),
    );
  });

  it("请求失败时 messages 里出现错误提示", async () => {
    const { ApiRequestError } = await import("@/lib/client");
    mockPost.mockRejectedValueOnce(new ApiRequestError("Internal Server Error", 500, {}));

    const { result } = renderHook(() => useChatSession(makeOpts()));

    await act(async () => {
      result.current.setInput("触发错误");
    });
    await act(async () => {
      await result.current.send();
    });

    const msgs = result.current.messages;
    expect(msgs.length).toBeGreaterThan(0);
    const last = msgs[msgs.length - 1];
    expect(last.role).toBe("assistant");
    expect(last.content).toBeTruthy();
  });

  it("后台任务响应会写入 activeTaskTurns，后续普通回答不会中断进行中的后台任务追踪", async () => {
    mockPost
      .mockResolvedValueOnce({
        ok: true,
        session_id: "sess-task",
        answer: "已提交后台任务",
        task_id: "task-001",
        task_status: "pending",
        extra: { pending_kind: "processing_pending" },
      })
      .mockResolvedValueOnce({
        ok: true,
        session_id: "sess-task",
        answer: "第二轮普通回答",
        task_status: "succeeded",
      });

    const { result } = renderHook(() => useChatSession(makeOpts()));

    await act(async () => {
      result.current.setInput("先发后台任务");
    });
    await act(async () => {
      await result.current.send();
    });

    await waitFor(() => expect(result.current.activeTaskTurns).toHaveLength(1));
    expect(result.current.activeTaskTurns[0]?.task_id).toBe("task-001");
  });

  it("后台任务完成后会从 activeTaskTurns 退场并清理 lastTurn pending 状态", async () => {
    mockPost.mockResolvedValueOnce({
      ok: true,
      session_id: "sess-task",
      answer: "已提交后台任务",
      task_id: "task-001",
      task_status: "pending",
      extra: { pending_kind: "processing_pending" },
    });

    const { result } = renderHook(() => useChatSession(makeOpts()));

    await act(async () => {
      result.current.setInput("先发后台任务");
    });
    await act(async () => {
      await result.current.send();
    });

    expect(result.current.lastTurn?.task_status).toBe("pending");

    await act(async () => {
      result.current.settleBackgroundTask({
        taskId: "task-001",
        status: "failed",
        errorMessage: "下载失败",
      });
    });

    await waitFor(() => expect(result.current.activeTaskTurns).toHaveLength(0));
    expect(result.current.lastTurn?.task_status).toBe("failed");
    expect(
      (result.current.lastTurn?.extra as Record<string, unknown> | null)?.pending_kind,
    ).toBe("none");
  });
});
