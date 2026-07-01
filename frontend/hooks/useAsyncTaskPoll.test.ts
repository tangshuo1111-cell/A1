import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAsyncTaskPoll } from "./useAsyncTaskPoll";
import type { ChatResponseBody } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  fetchTaskStatus: vi.fn(),
  fetchTaskResult: vi.fn(),
}));

import { fetchTaskResult, fetchTaskStatus } from "@/lib/api";

const mockStatus = fetchTaskStatus as ReturnType<typeof vi.fn>;
const mockResult = fetchTaskResult as ReturnType<typeof vi.fn>;

function makeTurn(overrides: Partial<ChatResponseBody> = {}): ChatResponseBody {
  return {
    ok: true,
    task_id: "task-001",
    task_status: "pending",
    answer_type: "async_pending",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useAsyncTaskPoll", () => {
  it("轮询到 succeeded 后调用 onTaskComplete 并传入 answer", async () => {
    mockStatus.mockResolvedValueOnce({ status: "running" }).mockResolvedValueOnce({ status: "succeeded" });
    mockResult.mockResolvedValueOnce({
      ready: true,
      result: { answer: "最终答案" },
      task_enqueue_to_finish_ms: 1200,
    });

    const onComplete = vi.fn();
    const trackedTurns = [makeTurn()];
    const { result } = renderHook(() =>
      useAsyncTaskPoll(trackedTurns, onComplete),
    );

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1), { timeout: 15000 });

    const payload = onComplete.mock.calls[0][0];
    expect(payload.answer).toBe("最终答案");
    expect(payload.status).toBe("succeeded");
    expect(payload.taskId).toBe("task-001");
    expect(result.current.polling).toBe(false);
    expect(result.current.tasks[0]?.taskId).toBe("task-001");
  });

  it("轮询到 failed 后调用 onTaskComplete 并传入 errorMessage", async () => {
    mockStatus.mockResolvedValueOnce({ status: "failed" });
    mockResult.mockResolvedValueOnce({
      ready: false,
      result: null,
      error: { message: "处理超时" },
    });

    const onComplete = vi.fn();
    const trackedTurns = [makeTurn()];
    renderHook(() => useAsyncTaskPoll(trackedTurns, onComplete));

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1), { timeout: 8000 });

    const payload = onComplete.mock.calls[0][0];
    expect(payload.answer).toBeNull();
    expect(payload.errorMessage).toBe("处理超时");
  });

  it("lastTurn 无 task_id 时不轮询", () => {
    const onComplete = vi.fn();
    renderHook(() => useAsyncTaskPoll([{ ok: true } as ChatResponseBody], onComplete));
    expect(mockStatus).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("任务状态写回后不会同步重复触发轮询", async () => {
    let releaseStatus: ((value: { status: string }) => void) | null = null;
    mockStatus.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          releaseStatus = resolve;
        }),
    );
    mockResult.mockResolvedValueOnce({
      ready: true,
      result: { answer: "收尾答案" },
    });

    const onComplete = vi.fn();
    const trackedTurns = [makeTurn()];
    renderHook(() => useAsyncTaskPoll(trackedTurns, onComplete));

    await waitFor(() => expect(mockStatus).toHaveBeenCalledTimes(1));
    expect(releaseStatus).not.toBeNull();
    releaseStatus?.({ status: "succeeded" });
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    expect(mockStatus).toHaveBeenCalledTimes(1);
  });
});
