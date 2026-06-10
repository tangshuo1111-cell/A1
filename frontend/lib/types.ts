/**
 * 与 FastAPI 对齐的 HTTP 类型定义（数据契约层）。
 * 协作：lib/api.ts、components/chat/* 消费；以后端 schemas_http 与 health 响应为准。
 */

export interface HealthBody {
  status: string;
  service?: string;
  checks?: Record<string, unknown>;
  latency_ms?: number;
}

export interface ChatPayload {
  message: string;
  session_id: string | null;
  /**
   * V9 R1：可选。POST /chat/agno 的 V2 知识开关（默认 false）。
   * 与后端 api/schemas_http.py: ChatRequest.use_knowledge 对齐。
   */
  use_knowledge?: boolean;
  /**
   * V16：用户已在前端确认对超长网页视频走 ASR（超过 asr_auto_max_sec）。
   */
  confirm_long_web_video_asr?: boolean;
}

/** POST /video/metadata 响应（与 FastAPI probe 对齐） */
export interface WebVideoMetadataBody {
  ok: boolean;
  duration_sec?: number;
  title?: string;
  asr_auto_max_sec?: number;
  asr_effective_max_sec?: number;
  asr_abs_max_sec?: number;
  cookies?: string;
  error?: string;
}

/** POST /chat 成功体（ok === true） */
export interface ChatResponseBody {
  ok: true;
  task_id?: string | null;
  session_id?: string | null;
  request_id?: string | null;
  answer?: string | null;
  answer_type?: string | null;
  task_status?: string | null;
  has_insufficient_info_notice?: boolean | null;
  router_source?: string | null;
  primary_path?: string | null;
  evidence_state?: string | null;
  extra?: Record<string, unknown> | null;
  /** 业务是否完全成功（task_status === done） */
  pipeline_ok?: boolean | null;
  debug_stage?: string | null;
  /** none | route | retrieval | tool | answer | storage | workflow */
  error_layer?: string | null;
  pipeline_error_code?: string | null;
  pipeline_hint_zh?: string | null;
  /** 本轮工作流耗时（毫秒） */
  workflow_elapsed_ms?: number | null;
  /** 用户可读的本轮模式（如「按知识库检索回答」） */
  interaction_mode_zh?: string | null;
}

export interface TaskStatusBody {
  ok: true;
  task_id: string;
  status: string;
  raw_status: string;
  task_type?: string;
  source_type?: string;
  stage?: string;
  progress?: number;
  session_id?: string | null;
  request_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number;
  error_code?: string;
  failure_reason?: string;
  next_action_hint?: string;
  result_pending_id?: string;
  result_source_id?: string;
  result_ttl_seconds?: number;
  expires_at?: string | null;
  task_enqueue_to_finish_ms?: number;
  result_ready?: boolean;
}

export interface TaskResultBody extends TaskStatusBody {
  ready: boolean;
  result?: Record<string, unknown> | null;
  error?: Record<string, string> | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** 本轮助手回复对应的交互模式（仅 assistant） */
  chainLabel?: string | null;
  /** 本轮工作流耗时 ms（仅 assistant） */
  elapsedMs?: number | null;
  /** 来源标签，供消息下方折叠展示（仅 assistant） */
  sourceHints?: string[] | null;
}

export interface ApiErrorBody {
  ok: false;
  request_id?: string;
  error: {
    code?: string;
    message?: string;
    category?: string;
    error_layer?: string;
    debug_stage?: string;
  };
}

export type ConnectionState = "checking" | "ok" | "degraded" | "offline";

/* ---------------------------------------------------------------------------
 * V11 R3：视频 URL 链 cookies 文件管理
 * ---------------------------------------------------------------------------
 * 与 api/routes/video_cookies.py 严格对齐。 */

export interface VideoCookiesFileStatus {
  exists: boolean;
  size_bytes: number;
  modified_iso: string | null;
  /** cookies.txt 里识别出的所有域名（已去重 + 去前缀点 + 小写） */
  domains: string[];
  /** domains 里命中后端白名单的子集（决定真正能给哪些站用） */
  matched_whitelist_domains: string[];
}

export interface VideoCookiesStatusBody {
  /** "browser:<name>" / "file" / "none" */
  source: string;
  /** 仅 source=file 时有；可能是用户 .env 配的、也可能是 R3 上传的 managed 路径 */
  effective_path: string | null;
  /** 后端 R3 上传接口写入的固定路径（前端只展示，不可改） */
  managed_path: string;
  managed_file: VideoCookiesFileStatus;
  whitelist_domains: string[];
  upload_max_bytes: number;
}

/** V11 R5 B：上传时的合并细节（按 domain 合并新旧 cookies） */
export interface VideoCookiesMergeInfo {
  /** 本次新上传文件中识别出的所有 domain */
  new_domains: string[];
  /** 旧文件里独有、被本次合并保留下来的 domain */
  kept_old_domains: string[];
  /** 旧文件里同 domain、被本次新文件覆盖（刷新登录态）的 domain */
  replaced_domains: string[];
}

export interface VideoCookiesUploadOk {
  ok: true;
  managed_path: string;
  size_bytes: number;
  /** 合并后磁盘里所有命中白名单的 domain（不再只是本次上传的） */
  matched_whitelist_domains: string[];
  /** 合并后磁盘里所有 domain */
  all_domains: string[];
  hot_reloaded: true;
  /** V11 R5 B：合并细节，前端展示"已保留 xx，刷新了 yy" */
  merge?: VideoCookiesMergeInfo;
}
