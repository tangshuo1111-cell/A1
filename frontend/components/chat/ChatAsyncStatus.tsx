"use client";

import {
  isMaterialPending,
  isPartialPending,
  readPendingKind,
} from "@/lib/chatTaskFields";
import type { AsyncTaskPollState } from "@/hooks/useAsyncTaskPoll";
import {
  humanizePendingKind,
  humanizeTaskStatus,
} from "@/lib/contextMeta/statusCopy";
import { humanizeTaskFailure } from "@/lib/taskFailureCopy";
import type { ChatResponseBody } from "@/lib/types";

interface ChatAsyncStatusProps {
  lastTurn: ChatResponseBody | null;
  poll: AsyncTaskPollState;
  onAction?: (text: string) => void;
}

function formatElapsedMs(ms: number | null | undefined): string | null {
  if (ms == null || ms <= 0) return null;
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} 秒`;
}

export function ChatAsyncStatus({ lastTurn, poll, onAction }: ChatAsyncStatusProps) {
  if (!lastTurn) return null;

  const pendingKind = readPendingKind(lastTurn);
  const material = isMaterialPending(lastTurn);
  const partial = isPartialPending(lastTurn);
  const tasks = poll.tasks;

  const isTaskPendingKind =
    pendingKind === "processing_pending" || pendingKind === "fast_pending";
  const showPendingKindCard = Boolean(pendingKind) && (!isTaskPendingKind || tasks.length > 0);

  if (tasks.length === 0 && !showPendingKindCard && !material && !partial) return null;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-2 px-4 pb-2 md:px-6">
      {tasks.map((task) => {
        const statusLabel = task.taskStatus
          ? humanizeTaskStatus(task.taskStatus.status || task.taskStatus.raw_status)
          : humanizeTaskStatus(task.sourceTurn.task_status);
        const progress =
          typeof task.taskStatus?.progress === "number"
            ? Math.max(0, Math.min(100, Math.round(task.taskStatus.progress * 100)))
            : null;
        const stage = String(task.taskStatus?.stage ?? "").trim();
        const taskFailure =
          task.pollError ||
          (task.taskResult?.error && typeof task.taskResult.error.message === "string"
            ? task.taskResult.error.message
            : "") ||
          String(task.taskStatus?.failure_reason ?? "").trim();
        const failureCopy = humanizeTaskFailure(taskFailure);
        return (
          <div
            key={task.taskId}
            className="rounded-lg border border-sky-900/20 bg-sky-950/10 px-3 py-2 text-[12px] text-ink-secondary dark:border-sky-700/30 dark:bg-sky-950/40"
            role="status"
            aria-live="polite"
          >
            <p className="font-medium text-ink-primary">后台任务</p>
            <p className="mt-1 font-mono text-[11px] text-ink-tertiary">
              task_id: {task.taskId}
            </p>
            <p className="mt-0.5">
              状态： {statusLabel}
              {task.polling ? "（轮询中…）" : null}
            </p>
            {stage ? <p className="mt-0.5 text-ink-tertiary">阶段：{stage}</p> : null}
            {progress != null ? (
              <p className="mt-0.5 text-ink-tertiary">进度：{progress}%</p>
            ) : null}
            {formatElapsedMs(task.backgroundElapsedMs) ? (
              <p className="mt-0.5 text-ink-tertiary">
                后台完成耗时：{formatElapsedMs(task.backgroundElapsedMs)}
              </p>
            ) : null}
            {task.taskResult?.ready && task.taskResult.result ? (
              <p className="mt-1 text-ink-secondary">
                最终结果已写入下方对话（或见任务结果接口）。
              </p>
            ) : null}
            {failureCopy ? (
              <div className="mt-1 space-y-1">
                <p className="text-amber-800 dark:text-amber-300">{failureCopy.summary}</p>
                {failureCopy.detail !== failureCopy.summary ? (
                  <p className="text-[11px] text-ink-tertiary">{failureCopy.detail}</p>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}

      {showPendingKindCard ? (
        <div className="rounded-lg border border-line-subtle bg-surface-elevated/50 px-3 py-2 text-[12px] text-ink-secondary">
          <p className="font-medium text-ink-primary">
            {humanizePendingKind(pendingKind) ?? pendingKind}
          </p>
        </div>
      ) : null}

      {material ? (
        <div className="rounded-lg border border-violet-900/25 bg-violet-950/10 px-3 py-2 text-[12px] leading-relaxed text-ink-secondary dark:bg-violet-950/30">
          <p className="font-medium text-ink-primary">待确认入库</p>
          <p className="mt-1">
            材料已准备好（material_pending）。确认后将保存到知识库，支持后续检索与追问。
          </p>
          {onAction ? (
            <button
              type="button"
              onClick={() => onAction("保存到知识库")}
              className="mt-2 rounded border border-violet-400/40 bg-violet-500/10 px-2.5 py-1 text-[11px] font-medium text-violet-700 hover:bg-violet-500/20 dark:text-violet-300"
            >
              保存到知识库
            </button>
          ) : null}
        </div>
      ) : null}

      {partial ? (
        <div className="rounded-lg border border-amber-900/25 bg-amber-950/10 px-3 py-2 text-[12px] text-ink-secondary dark:bg-amber-950/30">
          <p className="font-medium text-ink-primary">部分完成</p>
          <p className="mt-1">本轮在 SLA 内返回了部分结果；可继续追问以获取完整内容。</p>
          {onAction ? (
            <button
              type="button"
              onClick={() => onAction("请继续上一轮的内容，补充完整")}
              className="mt-2 rounded border border-amber-400/40 bg-amber-500/10 px-2.5 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-500/20 dark:text-amber-300"
            >
              继续追问
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
