/**
 * §13 G3 — 聊天/任务/pending 统一读顶层 task_id + extra.pending_kind（禁止 extra.video_task_id）。
 */
import type { ChatResponseBody } from "./types";

export const PENDING_KIND_VALUES = [
  "fast_pending",
  "processing_pending",
  "material_pending",
  "partial_pending",
  "none",
] as const;

export type PendingKind = (typeof PENDING_KIND_VALUES)[number] | string;

export function readExtraRecord(
  extra: ChatResponseBody["extra"],
): Record<string, unknown> | null {
  if (!extra || typeof extra !== "object") return null;
  return extra as Record<string, unknown>;
}

/** 后台任务 ID：仅读顶层 task_id（S11 已停写 extra.video_task_id）。 */
export function resolveBackgroundTaskId(turn: ChatResponseBody | null): string | null {
  if (!turn) return null;
  const id = typeof turn.task_id === "string" ? turn.task_id.trim() : "";
  return id || null;
}

export function readPendingKind(turn: ChatResponseBody | null): PendingKind | null {
  const ex = readExtraRecord(turn?.extra ?? null);
  if (!ex) return null;
  const raw = ex.pending_kind;
  if (typeof raw !== "string" || !raw.trim()) return null;
  return raw.trim();
}

const ACTIVE_TASK_STATUSES = new Set([
  "pending",
  "running",
  "queued",
  "in_progress",
]);

/** 是否需要对 GET /tasks/{id} 轮询。 */
export function shouldPollBackgroundTask(turn: ChatResponseBody | null): boolean {
  const taskId = resolveBackgroundTaskId(turn);
  if (!taskId) return false;
  const st = String(turn?.task_status ?? "")
    .trim()
    .toLowerCase();
  if (!st) {
    const kind = readPendingKind(turn);
    return kind === "processing_pending" || kind === "fast_pending";
  }
  return ACTIVE_TASK_STATUSES.has(st);
}

export function isMaterialPending(turn: ChatResponseBody | null): boolean {
  return readPendingKind(turn) === "material_pending";
}

export function isPartialPending(turn: ChatResponseBody | null): boolean {
  return readPendingKind(turn) === "partial_pending";
}
