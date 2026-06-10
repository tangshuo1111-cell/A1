import { act, renderHook } from "@testing-library/react";
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
  vi.clearAllMocks();
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
    mockPost.mockRejectedValueOnce(new ApiRequestError(500, "Internal Server Error", {}));

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
});
