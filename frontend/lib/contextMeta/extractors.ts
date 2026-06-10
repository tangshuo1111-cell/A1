/**
 * 将后端 extra 等字段整理为可读、低噪的展示文案（纯函数工具层）。
 *
 * V15：默认展示区仅回放「白名单内的 extra」— 不写死业务语义。
 */

import type { ChatResponseBody } from "../types";
import type { ContextLines, V15DebugRow } from "./types";
import { isLegacyExtraKey } from "./legacy";
import {
  humanizeLane,
  humanizePendingKind,
  humanizeTaskStatus,
  insufficientEvidenceUserNote,
} from "./statusCopy";

function asStr(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "string" && v.trim()) return v.trim();
  return null;
}

function safeJson(v: unknown, max = 900): string {
  try {
    return JSON.stringify(v).slice(0, max);
  } catch {
    return "(unserializable)";
  }
}

function pushV16Rows(
  push: (label: string, v: unknown) => void,
  extra: Record<string, unknown>,
): void {
  push("v16 doc tool_name", extra.v16_doc_tool_name);
  push("v16 doc source_type", extra.v16_doc_source_type);
  push("v16 doc extract_method", extra.v16_doc_extract_method);
  push("v16 doc quality_level", extra.v16_doc_quality_level);
  push("v16 doc mcp_mode", extra.v16_doc_mcp_mode);
  push("v16 doc error_code", extra.v16_doc_error_code);
  push("v16 web tool_name", extra.v16_web_tool_name);
  push("v16 web source_type", extra.v16_web_source_type);
  push("v16 web fetch_method", extra.v16_web_fetch_method);
  push("v16 web extract_method", extra.v16_web_extract_method);
  push("v16 web quality_level", extra.v16_web_quality_level);
  push("v16 web mcp_mode", extra.v16_web_mcp_mode);
  push("v16 web error_code", extra.v16_web_error_code);
  push("v16 web domain", extra.v16_web_domain);
  push("v16 web cookie_used", extra.v16_web_cookie_used);
  push("v16 video tool_name", extra.v16_video_tool_name);
  push("v16 video source_type", extra.v16_video_source_type);
  push("v16 video error_code", extra.v16_video_error_code);
  push("v16 video transcript_source", extra.v16_video_transcript_source);
  push("v16 video quality_level", extra.v16_video_quality_level);
  push("v16 task result_source_id", extra.v16_task_result_source_id);
}

/**
 * V15 默认主链区：只使用 extra 中白名单键；不推断「已入库」等业务状态。
 */
export function buildV15PrimaryRows(
  extra: Record<string, unknown> | null | undefined,
): V15DebugRow[] {
  if (!extra || typeof extra !== "object") return [];
  const rows: V15DebugRow[] = [];

  const push = (label: string, v: unknown) => {
    if (v === null || v === undefined) return;
    if (typeof v === "string" && !v.trim()) return;
    const s =
      typeof v === "string" || typeof v === "number" || typeof v === "boolean"
        ? String(v)
        : safeJson(v);
    if (!s || s === "[]" || s === "{}") return;
    rows.push({ label, value: s });
  };

  push("pending_kind (§13 G3)", extra.pending_kind);
  push("mode", extra.mode);
  push("lane", extra.lane);

  push("Main plan_id (v15)", extra.v15_plan_id);
  push("needs_retrieval", extra.v15_needs_retrieval);
  push("retrieval_strategy (plan request)", extra.v15_retrieval_strategy);
  push("needs_pending", extra.v15_needs_pending);
  push("pending_reference", extra.v15_pending_reference);
  push("answer_mode", extra.v15_answer_mode);
  push("tools_allowed", extra.v15_tools_allowed);

  push("Bundle id (v15)", extra.v15_bundle_id);
  push("execution_status (bundle)", extra.v15_execution_status);
  push("material_sufficiency", extra.v15_material_sufficiency);

  push("temporary_materials_count", extra.v15_temporary_materials_count);
  push("temporary_materials_preview", extra.v15_temporary_materials_preview);

  push("retrieved_chunks_count", extra.v15_retrieved_chunks_count);
  push("v12_used_context（后端切片）", extra.v12_used_context);
  push("v12_retrieval_debug（chunk 级）", extra.v12_retrieval_debug);

  push("tool_calls", extra.v15_tool_calls);
  push("failures", extra.v15_failures);
  push("commit_results", extra.v15_commit_results);

  push("filters / retrieval_filters", extra.v15_retrieval_filters);
  push("锚点 retrieved source_id（若返回）", extra.v15_retrieved_source_id);

  push("pending_status", extra.v13_material_status);
  push("commit artifact (extra.v13_commit)", extra.v13_commit);

  push("strategy/trace 原文：V14 retrieval 行", extra.v14_retrieval_trace_line);
  push("strategy/trace 原文：V14 score 行", extra.v14_score_trace_line);
  pushV16Rows(push, extra);

  const ct = extra.collaboration_trace;
  if (Array.isArray(ct) && ct.length > 0) {
    push(
      "collaboration_trace（前 12 段）",
      ct
        .slice(0, 12)
        .map((ln) =>
          typeof ln === "string" ? ln.slice(0, 360) : safeJson(ln, 260),
        )
        .join("\n"),
    );
  }

  return rows;
}

/** 折叠：除 V15 白名单字段外，其余非 legacy 顶层键 */
export const V15_WHITE_KEYS = new Set([
  "pending_kind",
  "mode",
  "lane",
  "v15_plan_id",
  "v15_bundle_id",
  "v15_needs_retrieval",
  "v15_retrieval_strategy",
  "v15_needs_pending",
  "v15_pending_reference",
  "v15_answer_mode",
  "v15_tools_allowed",
  "v15_material_sufficiency",
  "v15_execution_status",
  "v15_failures",
  "v15_tool_calls",
  "v15_temporary_materials_count",
  "v15_temporary_materials_preview",
  "v15_commit_results",
  "v15_retrieved_chunks_count",
  "v15_retrieval_filters",
  "v15_retrieved_source_id",
  "use_knowledge",
  "lane",
  "agno",
  "rag_context_chars",
  "v12_retrieved_chunks_count",
  "v12_retrieval_debug",
  "v12_used_context",
  "v13_material_status",
  "v13_source_type",
  "v13_used_pending_text",
  "v13_commit",
  "v14_retrieval_trace_line",
  "v14_score_trace_line",
  "collaboration_trace",
  "v16_doc_tool_name",
  "v16_doc_source_type",
  "v16_doc_extract_method",
  "v16_doc_quality_level",
  "v16_doc_mcp_mode",
  "v16_doc_error_code",
  "v16_web_tool_name",
  "v16_web_source_type",
  "v16_web_fetch_method",
  "v16_web_extract_method",
  "v16_web_quality_level",
  "v16_web_mcp_mode",
  "v16_web_error_code",
  "v16_web_url",
  "v16_web_domain",
  "v16_web_cookie_used",
  "v16_video_tool_name",
  "v16_video_source_type",
  "v16_video_error_code",
  "v16_video_transcript_source",
  "v16_video_quality_level",
  "v16_task_result_source_id",
]);

export function collectOtherExtraReplayLines(
  extra: Record<string, unknown>,
): Array<{ key: string; value: string }> {
  const out: Array<{ key: string; value: string }> = [];
  for (const [k, v] of Object.entries(extra)) {
    if (isLegacyExtraKey(k)) continue;
    if (V15_WHITE_KEYS.has(k)) continue;
    if (
      typeof v === "string" ||
      typeof v === "number" ||
      typeof v === "boolean"
    ) {
      out.push({ key: k, value: String(v).slice(0, 600) });
    } else if (v === null || v === undefined) {
      continue;
    } else {
      out.push({ key: k, value: safeJson(v, 900) });
    }
  }
  return out.slice(0, 32);
}

/** 折叠区：每条为 [键名, JSON 或小段字符串]（来自后端 extra） */
export function collectLegacyExtraLines(
  extra: Record<string, unknown> | null | undefined,
): Array<{ key: string; value: string }> {
  if (!extra || typeof extra !== "object") return [];
  const rows: Array<{ key: string; value: string }> = [];
  for (const [k, v] of Object.entries(extra)) {
    if (!isLegacyExtraKey(k)) continue;
    let s = "";
    if (
      typeof v === "string" ||
      typeof v === "number" ||
      typeof v === "boolean"
    ) {
      s = String(v);
    } else if (v === null || v === undefined) {
      s = "";
    } else {
      try {
        s = JSON.stringify(v).slice(0, 1200);
      } catch {
        s = "(unserializable)";
      }
    }
    rows.push({ key: k, value: s.slice(0, 800) });
  }
  return rows.slice(0, 24);
}

function joinTrace(trace: unknown): string | null {
  if (!Array.isArray(trace) || trace.length === 0) return null;
  const parts = trace
    .map((x) => {
      if (typeof x === "string") return x;
      if (x && typeof x === "object" && "channel" in x) {
        const ch = (x as { channel?: string }).channel;
        return ch ?? JSON.stringify(x).slice(0, 80);
      }
      return String(x).slice(0, 120);
    })
    .filter(Boolean);
  if (!parts.length) return null;
  return parts.slice(0, 5).join(" · ");
}

export function buildContextLines(res: ChatResponseBody): ContextLines {
  const extra = res.extra ?? {};
  const primary =
    asStr(res.primary_path) ??
    asStr((extra as { primary_path?: unknown }).primary_path) ??
    asStr((extra as { path_hints?: unknown }).path_hints);
  const lane = asStr((extra as { lane?: unknown }).lane);
  const taskStatus = asStr(res.task_status);
  const pendingKind = asStr((extra as { pending_kind?: unknown }).pending_kind);
  const chunksCount =
    typeof (extra as { v15_retrieved_chunks_count?: unknown }).v15_retrieved_chunks_count === "number"
      ? String((extra as { v15_retrieved_chunks_count: number }).v15_retrieved_chunks_count)
      : null;
  const tempCount =
    typeof (extra as { v15_temporary_materials_count?: unknown }).v15_temporary_materials_count === "number"
      ? String((extra as { v15_temporary_materials_count: number }).v15_temporary_materials_count)
      : null;

  const retrievalLabel = primary
    ? String(primary)
    : asStr(
          (extra as { middle_collect_priority?: unknown })
            .middle_collect_priority,
        )
      ? `priority · ${String((extra as { middle_collect_priority: unknown }).middle_collect_priority)}`
      : null;

  const toolsSummary =
    joinTrace((extra as { collection_trace?: unknown }).collection_trace) ??
    (Array.isArray((extra as { path_hints?: unknown }).path_hints) &&
    (extra as { path_hints: unknown[] }).path_hints.length
      ? `hints · ${(extra as { path_hints: string[] }).path_hints.slice(0, 3).join(", ")}`
      : null);

  let materialsSummary: string | null = null;
  const materialParts: string[] = [];
  if (chunksCount) materialParts.push(`检索片段 ${chunksCount}`);
  if (tempCount) materialParts.push(`临时材料 ${tempCount}`);
  const docQuality = asStr((extra as { v16_doc_quality_level?: unknown }).v16_doc_quality_level);
  if (docQuality) materialParts.push(`文档质量 ${docQuality}`);
  const webQuality = asStr((extra as { v16_web_quality_level?: unknown }).v16_web_quality_level);
  if (webQuality) materialParts.push(`网页质量 ${webQuality}`);
  const videoQuality = asStr((extra as { v16_video_quality_level?: unknown }).v16_video_quality_level);
  if (videoQuality) materialParts.push(`视频质量 ${videoQuality}`);
  if (materialParts.length > 0) {
    materialsSummary = materialParts.join(" · ");
  }

  const materialsCountLabel =
    chunksCount || tempCount
      ? [chunksCount ? `片段 ${chunksCount}` : null, tempCount ? `临时材料 ${tempCount}` : null]
          .filter(Boolean)
          .join(" / ")
      : null;

  let fallbackNote: string | null = null;
  if (res.has_insufficient_info_notice) {
    fallbackNote = "信息可能不完整 · 已标注说明";
  } else if (
    (extra as { insufficient_evidence?: boolean }).insufficient_evidence ===
    true
  ) {
    fallbackNote = insufficientEvidenceUserNote();
  } else if (
    asStr(
      (extra as { why_still_insufficient?: unknown }).why_still_insufficient,
    )
  ) {
    fallbackNote = asStr(
      (extra as { why_still_insufficient?: unknown }).why_still_insufficient,
    );
  }

  let v15Plan: string | null = null;
  const answerMode = asStr(
    (extra as { v15_answer_mode?: unknown }).v15_answer_mode,
  );
  const needsRetrieval = (extra as { v15_needs_retrieval?: unknown })
    .v15_needs_retrieval;
  const needsPending = (extra as { v15_needs_pending?: unknown })
    .v15_needs_pending;
  if (
    answerMode ||
    needsRetrieval !== undefined ||
    needsPending !== undefined
  ) {
    const parts: string[] = [];
    if (answerMode) parts.push(`mode=${answerMode}`);
    if (needsRetrieval !== undefined)
      parts.push(`rag=${needsRetrieval ? "yes" : "no"}`);
    if (needsPending !== undefined)
      parts.push(`pending=${needsPending ? "yes" : "no"}`);
    const strategy = asStr(
      (extra as { v15_retrieval_strategy?: unknown }).v15_retrieval_strategy,
    );
    if (strategy && strategy !== "auto") parts.push(`strategy=${strategy}`);
    v15Plan = parts.join(" · ") || null;
  }

  let v15Bundle: string | null = null;
  const sufficiency = asStr(
    (extra as { v15_material_sufficiency?: unknown }).v15_material_sufficiency,
  );
  const bundleChunksCount =
    typeof (extra as { v15_retrieved_chunks_count?: unknown })
      .v15_retrieved_chunks_count === "number"
      ? ((extra as { v15_retrieved_chunks_count?: number })
          .v15_retrieved_chunks_count ?? null)
      : null;
  const execStatus = asStr(
    (extra as { v15_execution_status?: unknown }).v15_execution_status,
  );
  const failures = Array.isArray(
    (extra as { v15_failures?: unknown }).v15_failures,
  )
    ? ((extra as { v15_failures: unknown[] }).v15_failures as unknown[])
    : [];
  if (sufficiency || bundleChunksCount !== null || failures.length > 0) {
    const parts: string[] = [];
    if (execStatus && execStatus !== "ok") parts.push(`exec=${execStatus}`);
    if (sufficiency) parts.push(`sufficiency=${sufficiency}`);
    if (bundleChunksCount !== null) parts.push(`chunks=${bundleChunksCount}`);
    if (failures.length > 0) {
      const failNames = failures
        .slice(0, 2)
        .map((f) =>
          f && typeof f === "object" && "tool" in f
            ? String((f as { tool: string }).tool)
            : "?",
        )
        .join(",");
      parts.push(`blocked=${failNames}`);
    }
    v15Bundle = parts.join(" · ") || null;
  }

  const v14RetrievalLine = asStr(
    (extra as { v14_retrieval_trace_line?: unknown }).v14_retrieval_trace_line,
  );
  const v15FinalStatus = asStr(
    (extra as { v15_execution_status?: unknown }).v15_execution_status,
  );

  let upgradeReason: string | null = null;
  if (humanizePendingKind(pendingKind)) {
    upgradeReason = humanizePendingKind(pendingKind);
  } else if (asStr((extra as { why_still_insufficient?: unknown }).why_still_insufficient)) {
    upgradeReason = asStr((extra as { why_still_insufficient?: unknown }).why_still_insufficient);
  } else if (asStr((extra as { v15_material_sufficiency?: unknown }).v15_material_sufficiency)) {
    upgradeReason = `材料判断：${asStr((extra as { v15_material_sufficiency?: unknown }).v15_material_sufficiency)}`;
  }

  return {
    retrievalLabel,
    toolsSummary,
    fallbackNote,
    laneLabel: humanizeLane(lane),
    statusLabel: taskStatus ? humanizeTaskStatus(taskStatus) : null,
    upgradeReason,
    materialsSummary,
    materialsCountLabel,
    v15Plan,
    v15Bundle,
    v14RetrievalLine,
    v15FinalStatus,
  };
}

/**
 * 从 ChatResponseBody 提取用户侧可读的来源标签（非 debug 轨）。
 * 返回最多 3 条简短字符串，空时返回 []。
 */
export function extractSourceHints(
  extra: Record<string, unknown> | null | undefined,
  lane: string | null | undefined,
): string[] {
  if (!extra) return [];
  const hints: string[] = [];

  const laneStr = asStr(lane) ?? asStr(extra.lane);

  if (laneStr === "kb") {
    const count = extra.v15_retrieved_chunks_count ?? extra.v12_retrieved_chunks_count;
    if (typeof count === "number" && count > 0) {
      hints.push(`知识库 · ${count} 条片段`);
    } else {
      hints.push("知识库");
    }
    const srcId = asStr(extra.v15_retrieved_source_id);
    if (srcId) hints.push(srcId.slice(0, 40));
  } else if (laneStr === "web") {
    const domain = asStr(extra.v16_web_domain);
    if (domain) hints.push(`网页 · ${domain}`);
    else hints.push("网页");
  } else if (laneStr === "video") {
    const src = asStr(extra.v16_video_transcript_source);
    hints.push(src ? `视频 · ${src}` : "视频");
  } else if (laneStr === "document") {
    const srcType = asStr(extra.v16_doc_source_type);
    hints.push(srcType ? `文档 · ${srcType}` : "文档");
  } else if (laneStr === "general" || laneStr === "complex") {
    const tmpCount = extra.v15_temporary_materials_count;
    if (typeof tmpCount === "number" && tmpCount > 0) {
      hints.push(`${tmpCount} 个来源`);
    }
  }

  return hints.slice(0, 3);
}
