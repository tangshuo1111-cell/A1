import { describe, expect, it } from "vitest";
import {
  humanizePendingKind,
  humanizeTaskStatus,
} from "./statusCopy";

describe("statusCopy", () => {
  it("humanizeTaskStatus maps pending vs queued", () => {
    expect(humanizeTaskStatus("pending")).toBe("等待中");
    expect(humanizeTaskStatus("queued")).toBe("排队中");
    expect(humanizeTaskStatus("running")).toBe("处理中");
    expect(humanizeTaskStatus("done")).toBe("已完成");
    expect(humanizeTaskStatus("blocked")).toBe("已阻止");
  });

  it("humanizePendingKind maps escalate_to_complex per pm/10", () => {
    expect(humanizePendingKind("escalate_to_complex")).toBe("已切换到深度分析");
    expect(humanizePendingKind("escalate_to_async")).toBe("已转入后台任务");
  });
});
