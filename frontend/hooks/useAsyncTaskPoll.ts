"use client";

import { useEffect, useRef, useState } from "react";

import { fetchTaskResult, fetchTaskStatus } from "@/lib/api";
import {
  resolveBackgroundTaskId,
  shouldPollBackgroundTask,
} from "@/lib/chatTaskFields";
import type { ChatResponseBody, TaskResultBody, TaskStatusBody } from "@/lib/types";

export interface AsyncTaskCompletePayload {
  taskId: string;
  status: string;
  answer: string | null;
  backgroundElapsedMs?: number;
  errorMessage?: string;
}

export interface AsyncTaskPollState {
  tasks: AsyncTaskTaskState[];
  polling: boolean;
}

export interface AsyncTaskTaskState {
  taskId: string;
  sourceTurn: ChatResponseBody;
  taskStatus: TaskStatusBody | null;
  taskResult: TaskResultBody | null;
  backgroundElapsedMs: number | null;
  polling: boolean;
  pollError: string | null;
}

const POLL_INTERVAL_MS = 3000;
const TERMINAL_STATUSES = new Set([
  "succeeded",
  "partial",
  "failed",
  "expired",
  "cancelled",
  "done",
  "error",
]);

function extractTaskAnswer(body: TaskResultBody): string | null {
  const r = body.result;
  if (!r || typeof r !== "object") return null;
  const rec = r as Record<string, unknown>;
  const raw = rec.answer ?? rec.final_answer;
  if (typeof raw !== "string") return null;
  const trimmed = raw.trim();
  return trimmed || null;
}

function resolveBackgroundElapsedMs(body: TaskResultBody): number | undefined {
  const direct = body.task_enqueue_to_finish_ms;
  if (typeof direct === "number" && direct > 0) return direct;
  const dur = body.duration_ms;
  if (typeof dur === "number" && dur > 0) return Math.round(dur);
  return undefined;
}

function isActiveStatus(status: string | null | undefined): boolean {
  const st = String(status ?? "").toLowerCase();
  return st === "pending" || st === "running" || st === "queued";
}

export function useAsyncTaskPoll(
  trackedTurns: ChatResponseBody[],
  onTaskComplete?: (payload: AsyncTaskCompletePayload) => void,
): AsyncTaskPollState {
  const [tasksById, setTasksById] = useState<Record<string, AsyncTaskTaskState>>({});
  const tasksByIdRef = useRef<Record<string, AsyncTaskTaskState>>({});
  const completedRef = useRef<Set<string>>(new Set());
  const activeTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const inFlightRef = useRef<Set<string>>(new Set());
  const unmountedRef = useRef(false);
  const onCompleteRef = useRef(onTaskComplete);
  onCompleteRef.current = onTaskComplete;
  tasksByIdRef.current = tasksById;

  useEffect(() => {
    const nextIds = new Set(
      trackedTurns
        .map((turn) => resolveBackgroundTaskId(turn))
        .filter((id): id is string => !!id),
    );
    setTasksById((prev) => {
      const next: Record<string, AsyncTaskTaskState> = {};
      let changed = false;
      for (const turn of trackedTurns) {
        const taskId = resolveBackgroundTaskId(turn);
        if (!taskId) continue;
        const existing = prev[taskId];
        const candidate: AsyncTaskTaskState = {
          taskId,
          sourceTurn: turn,
          taskStatus: existing?.taskStatus ?? null,
          taskResult: existing?.taskResult ?? null,
          backgroundElapsedMs: existing?.backgroundElapsedMs ?? null,
          polling: existing?.polling ?? false,
          pollError: existing?.pollError ?? null,
        };
        next[taskId] = candidate;
        if (!existing) {
          changed = true;
          continue;
        }
        if (
          existing.sourceTurn !== turn ||
          existing.taskStatus !== candidate.taskStatus ||
          existing.taskResult !== candidate.taskResult ||
          existing.backgroundElapsedMs !== candidate.backgroundElapsedMs ||
          existing.polling !== candidate.polling ||
          existing.pollError !== candidate.pollError
        ) {
          changed = true;
        }
      }
      if (!changed && Object.keys(prev).length === Object.keys(next).length) {
        return prev;
      }
      return next;
    });

    for (const [taskId, timer] of activeTimersRef.current.entries()) {
      if (!nextIds.has(taskId)) {
        clearTimeout(timer);
        activeTimersRef.current.delete(taskId);
        inFlightRef.current.delete(taskId);
      }
    }
  }, [trackedTurns]);

  useEffect(() => {
    unmountedRef.current = false;
    const timers = activeTimersRef.current;
    const inFlight = inFlightRef.current;
    return () => {
      unmountedRef.current = true;
      for (const timer of timers.values()) {
        clearTimeout(timer);
      }
      timers.clear();
      inFlight.clear();
    };
  }, []);

  useEffect(() => {
    async function pollTask(taskId: string) {
      if (inFlightRef.current.has(taskId)) {
        return;
      }
      inFlightRef.current.add(taskId);
      setTasksById((prev) => {
        const current = prev[taskId];
        if (!current) return prev;
        return {
          ...prev,
          [taskId]: {
            ...current,
            polling: true,
            pollError: null,
          },
        };
      });
      try {
        const body = await fetchTaskStatus(taskId);
        if (unmountedRef.current) return;
        setTasksById((prev) => {
          const current = prev[taskId];
          if (!current) return prev;
          return {
            ...prev,
            [taskId]: {
              ...current,
              taskStatus: body,
              polling: isActiveStatus(body.status ?? body.raw_status),
              pollError: null,
            },
          };
        });
        const st = String(body.status ?? body.raw_status ?? "").toLowerCase();
        if (isActiveStatus(st)) {
          const timer = setTimeout(() => {
            activeTimersRef.current.delete(taskId);
            void pollTask(taskId);
          }, POLL_INTERVAL_MS);
          activeTimersRef.current.set(taskId, timer);
          return;
        }
        activeTimersRef.current.delete(taskId);
        if (!TERMINAL_STATUSES.has(st)) {
          return;
        }

        const resultBody = await fetchTaskResult(taskId);
        if (unmountedRef.current) return;
        const bgMs = resolveBackgroundElapsedMs(resultBody) ?? null;
        setTasksById((prev) => {
          const current = prev[taskId];
          if (!current) return prev;
          return {
            ...prev,
            [taskId]: {
              ...current,
              taskResult: resultBody,
              backgroundElapsedMs: bgMs,
              polling: false,
              pollError: null,
            },
          };
        });

        if (completedRef.current.has(taskId)) return;
        completedRef.current.add(taskId);

        const answer = extractTaskAnswer(resultBody);
        const errMsg =
          resultBody.error && typeof resultBody.error.message === "string"
            ? resultBody.error.message
            : undefined;
        onCompleteRef.current?.({
          taskId,
          status: st,
          answer,
          backgroundElapsedMs: bgMs ?? undefined,
          errorMessage: errMsg,
        });
      } catch (err) {
        if (unmountedRef.current) return;
        activeTimersRef.current.delete(taskId);
        setTasksById((prev) => {
          const current = prev[taskId];
          if (!current) return prev;
          return {
            ...prev,
            [taskId]: {
              ...current,
              polling: false,
              pollError: err instanceof Error ? err.message : "任务状态查询失败",
            },
          };
        });
      } finally {
        inFlightRef.current.delete(taskId);
      }
    }

    for (const turn of trackedTurns) {
      const taskId = resolveBackgroundTaskId(turn);
      if (!taskId) continue;
      if (activeTimersRef.current.has(taskId)) continue;
      if (inFlightRef.current.has(taskId)) continue;
      const current = tasksByIdRef.current[taskId];
      if (current?.taskResult?.ready || completedRef.current.has(taskId)) continue;
      if (!shouldPollBackgroundTask(turn) && !isActiveStatus(current?.taskStatus?.status ?? current?.taskStatus?.raw_status)) {
        continue;
      }
      void pollTask(taskId);
    }
  }, [trackedTurns]);

  const tasks = trackedTurns
    .map((turn) => {
      const taskId = resolveBackgroundTaskId(turn);
      if (!taskId) return null;
      return tasksById[taskId] ?? {
        taskId,
        sourceTurn: turn,
        taskStatus: null,
        taskResult: null,
        backgroundElapsedMs: null,
        polling: false,
        pollError: null,
      };
    })
    .filter((item): item is AsyncTaskTaskState => item !== null);

  return {
    tasks,
    polling: tasks.some((item) => item.polling),
  };
}
