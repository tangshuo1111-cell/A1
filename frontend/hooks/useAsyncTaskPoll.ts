"use client";

import { useEffect, useState } from "react";

import { fetchTaskStatus } from "@/lib/api";
import {
  resolveBackgroundTaskId,
  shouldPollBackgroundTask,
} from "@/lib/chatTaskFields";
import type { ChatResponseBody, TaskStatusBody } from "@/lib/types";

export interface AsyncTaskPollState {
  taskId: string | null;
  taskStatus: TaskStatusBody | null;
  polling: boolean;
  pollError: string | null;
}

const POLL_INTERVAL_MS = 3000;

export function useAsyncTaskPoll(
  lastTurn: ChatResponseBody | null,
): AsyncTaskPollState {
  const taskId = resolveBackgroundTaskId(lastTurn);
  const shouldPoll = shouldPollBackgroundTask(lastTurn);

  const [taskStatus, setTaskStatus] = useState<TaskStatusBody | null>(null);
  const [polling, setPolling] = useState(false);
  const [pollError, setPollError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId || !shouldPoll) {
      setTaskStatus(null);
      setPolling(false);
      setPollError(null);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function pollOnce() {
      setPolling(true);
      try {
        const body = await fetchTaskStatus(taskId);
        if (cancelled) return;
        setTaskStatus(body);
        setPollError(null);
        const st = String(body.status ?? body.raw_status ?? "").toLowerCase();
        if (st === "pending" || st === "running" || st === "queued") {
          timer = setTimeout(pollOnce, POLL_INTERVAL_MS);
        } else {
          setPolling(false);
        }
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

  return { taskId, taskStatus, polling, pollError };
}
