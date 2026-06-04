"use client";

import {
  isMaterialPending,
  isPartialPending,
  readPendingKind,
  resolveBackgroundTaskId,
} from "@/lib/chatTaskFields";
import type { AsyncTaskPollState } from "@/hooks/useAsyncTaskPoll";
import type { ChatResponseBody } from "@/lib/types";

interface ChatAsyncStatusProps {
  lastTurn: ChatResponseBody | null;
  poll: AsyncTaskPollState;
}

function formatElapsedMs(ms: number | null | undefined): string | null {
  if (ms == null || ms <= 0) return null;
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} 秒`;
}

function statusLabel(raw: string | undefined): string {
  const st = (raw ?? "").toLowerCase();
  if (st === "pending" || st === "queued") return "排队中";
  if (st === "running" || st === "in_progress") return "处理中";
  if (st === "succeeded" || st === "done") return "已完成";
  if (st === "failed" || st === "error") return "失败";
  if (st === "partial") return "部分完成";
  return raw || "—";
}

export function ChatAsyncStatus({ lastTurn, poll }: ChatAsyncStatusProps) {
  if (!lastTurn) return null;

  const taskId = resolveBackgroundTaskId(lastTurn);
  const pendingKind = readPendingKind(lastTurn);
  const material = isMaterialPending(lastTurn);
  const partial = isPartialPending(lastTurn);
  const showTask =
    taskId &&
    (poll.polling ||
      poll.taskStatus ||
      String(lastTurn.task_status ?? "").toLowerCase() === "pending");

  if (!showTask && !pendingKind && !material && !partial) return null;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-2 px-4 pb-2 md:px-6">
      {(showTask || taskId) && (
        <div
          className="rounded-lg border border-sky-900/20 bg-sky-950/10 px-3 py-2 text-[12px] text-ink-secondary dark:border-sky-700/30 dark:bg-sky-950/40"
          role="status"
          aria-live="polite"
        >
          <p className="font-medium text-ink-primary">后台任务</p>
          <p className="mt-1 font-mono text-[11px] text-ink-tertiary">
            task_id: {taskId}
          </p>
          <p className="mt-0.5">
            状态：{" "}
            {poll.taskStatus
              ? statusLabel(poll.taskStatus.status || poll.taskStatus.raw_status)
              : statusLabel(lastTurn.task_status ?? undefined)}
            {poll.polling ? "（轮询中…）" : null}
          </p>
          {formatElapsedMs(poll.backgroundElapsedMs) ? (
            <p className="mt-0.5 text-ink-tertiary">
              后台完成耗时：{formatElapsedMs(poll.backgroundElapsedMs)}
            </p>
          ) : null}
          {poll.taskResult?.ready && poll.taskResult.result ? (
            <p className="mt-1 text-ink-secondary">
              最终结果已写入下方对话（或见任务结果接口）。
            </p>
          ) : null}
          {poll.pollError ? (
            <p className="mt-1 text-amber-800 dark:text-amber-300">{poll.pollError}</p>
          ) : null}
        </div>
      )}

      {pendingKind ? (
        <div className="rounded-lg border border-line-subtle bg-surface-elevated/50 px-3 py-2 text-[12px] text-ink-secondary">
          <p>
            <span className="font-medium text-ink-primary">pending_kind</span>:{" "}
            <code className="font-mono text-[11px]">{pendingKind}</code>
          </p>
        </div>
      ) : null}

      {material ? (
        <div className="rounded-lg border border-violet-900/25 bg-violet-950/10 px-3 py-2 text-[12px] leading-relaxed text-ink-secondary dark:bg-violet-950/30">
          <p className="font-medium text-ink-primary">待确认入库</p>
          <p className="mt-1">
            材料已准备好（material_pending）。如需保存到知识库，请直接回复「保存到知识库」或按助手提示确认。
          </p>
        </div>
      ) : null}

      {partial ? (
        <div className="rounded-lg border border-amber-900/25 bg-amber-950/10 px-3 py-2 text-[12px] text-ink-secondary dark:bg-amber-950/30">
          <p className="font-medium text-ink-primary">部分完成</p>
          <p className="mt-1">本轮在 SLA 内返回了部分结果；可稍后继续追问或等待后台任务完成。</p>
        </div>
      ) : null}
    </div>
  );
}
