import { describe, expect, it } from "vitest";

import {
  isMaterialPending,
  readPendingKind,
  resolveBackgroundTaskId,
  shouldPollBackgroundTask,
} from "./chatTaskFields";
import type { ChatResponseBody } from "./types";

function turn(partial: Partial<ChatResponseBody>): ChatResponseBody {
  return {
    ok: true,
    ...partial,
  };
}

describe("chatTaskFields (G3)", () => {
  it("resolveBackgroundTaskId reads top-level task_id only", () => {
    const t = turn({
      task_id: "task-abc",
      extra: { video_task_id: "legacy-should-ignore" },
    });
    expect(resolveBackgroundTaskId(t)).toBe("task-abc");
  });

  it("shouldPollBackgroundTask when task_status pending", () => {
    expect(
      shouldPollBackgroundTask(
        turn({ task_id: "t1", task_status: "pending" }),
      ),
    ).toBe(true);
  });

  it("readPendingKind from extra.pending_kind", () => {
    expect(
      readPendingKind(
        turn({ extra: { pending_kind: "processing_pending" } }),
      ),
    ).toBe("processing_pending");
    expect(isMaterialPending(turn({ extra: { pending_kind: "material_pending" } }))).toBe(
      true,
    );
  });

  it("does not poll without task_id", () => {
    expect(shouldPollBackgroundTask(turn({ task_status: "pending" }))).toBe(false);
  });
});
