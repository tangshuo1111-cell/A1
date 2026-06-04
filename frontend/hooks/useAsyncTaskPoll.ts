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
  taskId: string | null;
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

export function useAsyncTaskPoll(
  lastTurn: ChatResponseBody | null,
  onTaskComplete?: (payload: AsyncTaskCompletePayload) => void,
): AsyncTaskPollState {
  const taskId = resolveBackgroundTaskId(lastTurn);
  const shouldPoll = shouldPollBackgroundTask(lastTurn);

  const [taskStatus, setTaskStatus] = useState<TaskStatusBody | null>(null);
  const [taskResult, setTaskResult] = useState<TaskResultBody | null>(null);
  const [backgroundElapsedMs, setBackgroundElapsedMs] = useState<number | null>(null);
  const [polling, setPolling] = useState(false);
  const [pollError, setPollError] = useState<string | null>(null);
  const completedRef = useRef<Set<string>>(new Set());
  const onCompleteRef = useRef(onTaskComplete);
  onCompleteRef.current = onTaskComplete;

  useEffect(() => {
    if (!taskId || !shouldPoll) {
      setTaskStatus(null);
      setTaskResult(null);
      setBackgroundElapsedMs(null);
      setPolling(false);
      setPollError(null);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function pollOnce() {
      setPolling(true);
      try {
        const body = await fetchTaskStatus(taskId!);
        if (cancelled) return;
        setTaskStatus(body);
        setPollError(null);
        const st = String(body.status ?? body.raw_status ?? "").toLowerCase();
        if (st === "pending" || st === "running" || st === "queued") {
          timer = setTimeout(pollOnce, POLL_INTERVAL_MS);
          return;
        }

        setPolling(false);
        if (!TERMINAL_STATUSES.has(st)) {
          return;
        }

        const resultBody = await fetchTaskResult(taskId!);
        if (cancelled) return;
        setTaskResult(resultBody);
        const bgMs = resolveBackgroundElapsedMs(resultBody);
        if (bgMs != null) setBackgroundElapsedMs(bgMs);

        if (completedRef.current.has(taskId!)) return;
        completedRef.current.add(taskId!);

        const answer = extractTaskAnswer(resultBody);
        const errMsg =
          resultBody.error && typeof resultBody.error.message === "string"
            ? resultBody.error.message
            : undefined;
        onCompleteRef.current?.({
          taskId: taskId!,
          status: st,
          answer,
          backgroundElapsedMs: bgMs,
          errorMessage: errMsg,
        });
      } catch (err) {
        if (cancelled) return;
        setPollError(err instanceof Error ? err.message : "任务状态查询失败");
        setPolling(false);
      }
    }

    pollOnce();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [taskId, shouldPoll, lastTurn?.task_status]);

  return {
    taskId,
    taskStatus,
    taskResult,
    backgroundElapsedMs,
    polling,
    pollError,
  };
}
