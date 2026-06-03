/**
 * 业务 API 封装（应用服务层）。
 * 仅暴露与页面相关的后端入口；禁止在组件内散落 fetch。
 * 协作：lib/client.ts、lib/types.ts；被 components/chat/ChatExperience 等调用。
 *
 * V9 R3：postChat 连后端 POST /chat/agno（V6 三强 Agent + V7 视频链 + V8 会话记忆），
 *   这是当前唯一的公开 chat 主路由；旧 LangGraph 主链（POST /chat、POST /chat/async）
 *   已物理删除，无回退入口。
 */

import { jsonFetch, multipartFetch } from "./client";
import type {
  ChatPayload,
  ChatResponseBody,
  HealthBody,
  TaskResultBody,
  TaskStatusBody,
  VideoCookiesStatusBody,
  VideoCookiesUploadOk,
  WebVideoMetadataBody,
} from "./types";

/** V9 R3 默认主 chat 路径（前端唯一默认连接点）。 */
export const DEFAULT_CHAT_PATH = "/chat/agno";

export async function fetchHealth(): Promise<HealthBody> {
  return jsonFetch<HealthBody>("/health", { method: "GET" });
}

export async function postChat(payload: ChatPayload): Promise<ChatResponseBody> {
  const body: Record<string, unknown> = {
    message: payload.message,
    session_id: payload.session_id,
  };
  if (typeof payload.use_knowledge === "boolean") {
    body.use_knowledge = payload.use_knowledge;
  }
  if (typeof payload.confirm_long_web_video_asr === "boolean") {
    body.confirm_long_web_video_asr = payload.confirm_long_web_video_asr;
  }
  return jsonFetch<ChatResponseBody>(DEFAULT_CHAT_PATH, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchTaskStatus(taskId: string): Promise<TaskStatusBody> {
  return jsonFetch<TaskStatusBody>(`/tasks/${encodeURIComponent(taskId)}`, {
    method: "GET",
  });
}

export async function fetchTaskResult(taskId: string): Promise<TaskResultBody> {
  return jsonFetch<TaskResultBody>(`/tasks/${encodeURIComponent(taskId)}/result`, {
    method: "GET",
  });
}

/** V16：探针网页视频时长（不下媒体），供长视频 ASR 确认 */
export async function fetchWebVideoMetadata(url: string): Promise<WebVideoMetadataBody> {
  return jsonFetch<WebVideoMetadataBody>("/video/metadata", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

/* ---------------------------------------------------------------------------
 * V11 R3：视频 cookies 管理
 * --------------------------------------------------------------------------- */
export async function fetchVideoCookiesStatus(): Promise<VideoCookiesStatusBody> {
  return jsonFetch<VideoCookiesStatusBody>("/config/video_cookies/status", {
    method: "GET",
  });
}

export async function uploadVideoCookies(file: File): Promise<VideoCookiesUploadOk> {
  const fd = new FormData();
  fd.append("file", file, file.name || "cookies.txt");
  return multipartFetch<VideoCookiesUploadOk>("/config/video_cookies/upload", fd);
}

export async function deleteVideoCookies(): Promise<{ ok: boolean; removed: boolean }> {
  return jsonFetch<{ ok: boolean; removed: boolean }>("/config/video_cookies", {
    method: "DELETE",
  });
}
