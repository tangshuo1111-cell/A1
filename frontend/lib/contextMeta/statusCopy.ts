/**
 * 用户可见状态文案 — 单一事实源（SSOT）。
 *
 * 治理：
 * - 产品口径：`docs/pm/10_用户可见状态文案.md`
 * - 主区摘要：`TurnStatusSummary` ← `buildContextLines` ← 本文件
 * - 异步区：`ChatAsyncStatus` 复用 `humanizeTaskStatus` / `humanizePendingKind`
 * - 禁止在组件内再写一套 task_status / pending_kind 中文映射
 */

export function humanizeLane(raw: string | null): string | null {
  if (!raw) return null;
  switch (raw) {
    case "kb":
      return "知识库直答";
    case "document":
      return "文档理解";
    case "web":
      return "网页读取";
    case "video":
      return "视频处理";
    case "general":
      return "通用回答";
    default:
      return raw;
  }
}

/** 顶层 task_status / 后台任务 status（与 pm/10 task_status 表一致） */
export function humanizeTaskStatus(raw: string | null | undefined): string {
  const st = (raw ?? "").trim().toLowerCase();
  if (!st) return "—";
  switch (st) {
    case "done":
    case "succeeded":
      return "已完成";
    case "partial":
      return "部分完成";
    case "failed":
    case "error":
      return "未完成";
    case "blocked":
      return "已阻止";
    case "queued":
      return "排队中";
    case "running":
    case "in_progress":
      return "处理中";
    case "pending":
      return "等待中";
    default:
      return raw ?? "—";
  }
}

/** extra.pending_kind（与 pm/10 pending_kind 表一致） */
export function humanizePendingKind(raw: string | null | undefined): string | null {
  if (!raw) return null;
  switch (raw) {
    case "escalate_to_complex":
      return "已切换到深度分析";
    case "escalate_to_async":
      return "已转入后台任务";
    case "more_web_material":
      return "需要补充网页材料";
    case "more_document_material":
      return "需要补充文档材料";
    case "more_video_material":
      return "需要补充视频材料";
    case "more_kb_material":
      return "需要补充知识库材料";
    case "fast_pending":
      return "快速通道等待中";
    case "processing_pending":
      return "后台处理中";
    case "material_pending":
      return "待确认入库";
    case "partial_pending":
      return "部分完成";
    case "none":
      return null;
    default:
      return raw;
  }
}

/** insufficient_evidence / 保守交付（pm/10 soft 语义） */
export function insufficientEvidenceUserNote(): string {
  return "证据偏薄，回答偏保守";
}
