"use client";

import { useCallback, useState } from "react";
import { ApiRequestError } from "@/lib/client";
import { sanitizeAssistantAnswer } from "@/lib/answerSanitizer";
import { fetchWebVideoMetadata, postChat } from "@/lib/api";
import { extractFirstWhitelistVideoUrl } from "@/lib/videoUrl";
import { extractSourceHints } from "@/lib/contextMeta";
import { detectVideoCookiesNeed } from "@/hooks/useVideoGuide";
import type { CookiesGuideSignal } from "@/hooks/useVideoGuide";
import type {
  ApiErrorBody,
  ChatMessage,
  ChatResponseBody,
  ConnectionState,
} from "@/lib/types";

const SESSION_STORAGE_KEY = "maqa_session_id";

function readStoredSessionId(): string | null {
  try {
    return sessionStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredSessionId(sid: string): void {
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, sid);
  } catch {
    /* ignore quota / private-mode errors */
  }
}

function id() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function assistantErrorMessage(err: unknown): string {
  if (err instanceof ApiRequestError) {
    if (err.status === 0) {
      return "当前无法连接后端服务。请在本机启动 API（例如运行 uvicorn）后再试。";
    }
    if (err.status >= 500) {
      const layer =
        err.body &&
        typeof err.body === "object" &&
        "error" in err.body &&
        typeof (err.body as ApiErrorBody).error?.error_layer === "string"
          ? (err.body as ApiErrorBody).error!.error_layer
          : null;
      if (layer === "storage") {
        return "服务器存储/数据库异常（可检查 PostgreSQL 连接与 DATABASE_URL 配置）。详情见响应体或日志。";
      }
      if (layer === "tool") {
        return "服务器工具层异常（502）。请查看后端日志中的 tool 相关错误。";
      }
      if (layer === "route" || layer === "workflow") {
        return "服务器编排/路由异常（502）。请查看后端日志中的 workflow 或 LLM 路由。";
      }
      const rid =
        err.body &&
        typeof err.body === "object" &&
        "request_id" in err.body &&
        typeof (err.body as { request_id?: string }).request_id === "string"
          ? (err.body as { request_id: string }).request_id
          : null;
      const tail = rid ? ` request_id=${rid}` : "";
      return `服务器暂时异常（HTTP ${err.status}）。${tail}`.trim();
    }
    if (err.status === 429) {
      return "请求过于频繁，请稍后再试。";
    }
    const msg = err.message?.trim();
    if (msg) {
      return `请求未能完成（${err.status}）：${msg}`;
    }
    return `请求未能完成（HTTP ${err.status}）。`;
  }
  return "发生未知错误，请稍后再试。";
}

function shouldTrackTaskTurn(turn: ChatResponseBody | null): boolean {
  if (!turn) return false;
  const taskId = typeof turn.task_id === "string" ? turn.task_id.trim() : "";
  if (!taskId) return false;
  const status = String(turn.task_status ?? "").trim().toLowerCase();
  if (status === "pending" || status === "running" || status === "queued") {
    return true;
  }
  const ex =
    turn.extra && typeof turn.extra === "object" ? (turn.extra as Record<string, unknown>) : null;
  const pendingKind = typeof ex?.pending_kind === "string" ? ex.pending_kind.trim() : "";
  return pendingKind === "processing_pending" || pendingKind === "fast_pending";
}

function normalizeTaskId(turn: ChatResponseBody | null | undefined): string {
  return typeof turn?.task_id === "string" ? turn.task_id.trim() : "";
}

function normalizeTaskStatus(status: string | null | undefined): string {
  return String(status ?? "").trim().toLowerCase();
}

function clearPendingKind(extra: ChatResponseBody["extra"]): Record<string, unknown> | null {
  if (!extra || typeof extra !== "object") return null;
  const next = { ...(extra as Record<string, unknown>) };
  if ("pending_kind" in next) {
    next.pending_kind = "none";
  }
  return next;
}

export interface LongVideoGate {
  messageText: string;
  durationSec: number;
  title: string;
  autoMax: number;
  effectiveMax: number;
  isAutoRetry?: boolean;
}

export interface SendTextOpts {
  isAutoRetry?: boolean;
  confirmLongWebVideoAsr?: boolean;
  skipLongVideoProbe?: boolean;
}

export interface ChatSessionState {
  messages: ChatMessage[];
  input: string;
  setInput: (v: string) => void;
  isGenerating: boolean;
  generatingSince: number | null;
  lastTurn: ChatResponseBody | null;
  activeTaskTurns: ChatResponseBody[];
  pipelineNotice: string | null;
  longVideoGate: LongVideoGate | null;
  setLongVideoGate: (v: LongVideoGate | null) => void;
  sendText: (text: string, opts?: SendTextOpts) => Promise<void>;
  send: () => Promise<void>;
  appendAssistantMessage: (
    content: string,
    meta?: Pick<ChatMessage, "chainLabel" | "elapsedMs">,
  ) => void;
  settleBackgroundTask: (
    payload: {
      taskId: string;
      status: string;
      answer?: string | null;
      errorMessage?: string;
      backgroundElapsedMs?: number;
    },
  ) => void;
}

export function useChatSession(opts: {
  connection: ConnectionState;
  setConnection: (v: ConnectionState) => void;
  setSoftError: (v: string | null) => void;
  applyVideoSignal: (sig: CookiesGuideSignal) => void;
}): ChatSessionState {
  const { setConnection, setSoftError, applyVideoSignal } = opts;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(() => readStoredSessionId());
  const [lastTurn, setLastTurn] = useState<ChatResponseBody | null>(null);
  const [activeTaskTurns, setActiveTaskTurns] = useState<ChatResponseBody[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatingSince, setGeneratingSince] = useState<number | null>(null);
  const [pipelineNotice, setPipelineNotice] = useState<string | null>(null);
  const [longVideoGate, setLongVideoGate] = useState<LongVideoGate | null>(null);

  const appendAssistantMessage = useCallback(
    (
      content: string,
      meta?: Pick<ChatMessage, "chainLabel" | "elapsedMs">,
    ) => {
      const trimmed = content.trim();
      if (!trimmed) return;
      setMessages((m) => [
        ...m,
        {
          id: id(),
          role: "assistant",
          content: sanitizeAssistantAnswer(trimmed),
          chainLabel: meta?.chainLabel,
          elapsedMs: meta?.elapsedMs,
        },
      ]);
    },
    [],
  );

  const settleBackgroundTask = useCallback(
    (payload: {
      taskId: string;
      status: string;
      answer?: string | null;
      errorMessage?: string;
      backgroundElapsedMs?: number;
    }) => {
      const taskId = payload.taskId.trim();
      if (!taskId) return;

      setActiveTaskTurns((prev) =>
        prev.filter((turn) => normalizeTaskId(turn) !== taskId),
      );

      setLastTurn((prev) => {
        if (normalizeTaskId(prev) !== taskId) {
          return prev;
        }
        const nextStatus = normalizeTaskStatus(payload.status) || prev?.task_status || null;
        return prev
          ? {
              ...prev,
              task_status: nextStatus,
              answer: payload.answer?.trim() || prev.answer || null,
              workflow_elapsed_ms: payload.backgroundElapsedMs ?? prev.workflow_elapsed_ms ?? null,
              extra: clearPendingKind(prev.extra),
            }
          : prev;
      });
    },
    [],
  );

  const sendText = useCallback(
    async (text: string, sendOpts?: SendTextOpts) => {
      const t = text.trim();
      if (!t || isGenerating) return;

      const vurl = extractFirstWhitelistVideoUrl(t);
      if (vurl && !sendOpts?.confirmLongWebVideoAsr && !sendOpts?.skipLongVideoProbe) {
        try {
          const meta = await fetchWebVideoMetadata(vurl);
          if (
            meta.ok &&
            typeof meta.duration_sec === "number" &&
            typeof meta.asr_auto_max_sec === "number" &&
            meta.duration_sec > meta.asr_auto_max_sec
          ) {
            setLongVideoGate({
              messageText: t,
              durationSec: meta.duration_sec,
              title: (meta.title || "").trim(),
              autoMax: meta.asr_auto_max_sec,
              effectiveMax:
                typeof meta.asr_effective_max_sec === "number"
                  ? meta.asr_effective_max_sec
                  : meta.asr_auto_max_sec,
              isAutoRetry: sendOpts?.isAutoRetry,
            });
            return;
          }
        } catch {
          /* probe failure does not block sending */
        }
      }

      setSoftError(null);
      setPipelineNotice(null);
      const prefix = sendOpts?.isAutoRetry ? "（自动重试）" : "";
      const userMsg: ChatMessage = {
        id: id(),
        role: "user",
        content: prefix + t,
      };
      setMessages((m) => [...m, userMsg]);
      setIsGenerating(true);
      setGeneratingSince(Date.now());

      try {
        const res = await postChat({
          message: t,
          session_id: sessionId,
          confirm_long_web_video_asr: !!sendOpts?.confirmLongWebVideoAsr,
        });
        setLastTurn(res);
        if (shouldTrackTaskTurn(res)) {
          setActiveTaskTurns((prev) => {
            const taskId = normalizeTaskId(res);
            const next = prev.filter((item) => normalizeTaskId(item) !== taskId);
            return [res, ...next];
          });
        }
        if (res.session_id) {
          setSessionId(res.session_id);
          writeStoredSessionId(res.session_id);
        }
        if (res.pipeline_ok === false && res.pipeline_hint_zh) {
          setPipelineNotice(res.pipeline_hint_zh);
        }

        const sig = detectVideoCookiesNeed(res);
        applyVideoSignal(sig);

        const answerRaw = (res.answer ?? "").trim();
        const answerText = answerRaw
          ? sanitizeAssistantAnswer(res.answer as string)
          : "本轮未返回正文。可以换个说法或稍后重试。";

        const ex =
          res.extra && typeof res.extra === "object" ? (res.extra as Record<string, unknown>) : null;
        const sourceHints = extractSourceHints(ex, ex?.lane as string | undefined);

        setMessages((m) => [
          ...m,
          {
            id: id(),
            role: "assistant",
            content: answerText,
            chainLabel: res.interaction_mode_zh ?? undefined,
            elapsedMs:
              typeof res.workflow_elapsed_ms === "number"
                ? res.workflow_elapsed_ms
                : undefined,
            sourceHints: sourceHints.length > 0 ? sourceHints : null,
          },
        ]);
      } catch (e) {
        if (e instanceof ApiRequestError && e.status === 0) {
          setConnection("offline");
        }
        const msg =
          e instanceof ApiRequestError
            ? e.status === 0
              ? "无法连接到后端（网络或 API 未监听）。"
              : e.message || `HTTP ${e.status}`
            : "请求失败";
        setSoftError(msg);
        const userLine = assistantErrorMessage(e);
        setMessages((m) => [
          ...m,
          {
            id: id(),
            role: "assistant",
            content: sanitizeAssistantAnswer(userLine),
          },
        ]);
      } finally {
        setIsGenerating(false);
        setGeneratingSince(null);
      }
    },
    [isGenerating, sessionId, setSoftError, setConnection, applyVideoSignal],
  );

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || isGenerating) return;
    setInput("");
    await sendText(text);
  }, [input, isGenerating, sendText]);

  return {
    messages,
    input,
    setInput,
    isGenerating,
    generatingSince,
    lastTurn,
    activeTaskTurns,
    pipelineNotice,
    longVideoGate,
    setLongVideoGate,
    sendText,
    send,
    appendAssistantMessage,
    settleBackgroundTask,
  };
}
