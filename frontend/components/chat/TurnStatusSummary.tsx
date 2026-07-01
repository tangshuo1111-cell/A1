"use client";

/**
 * 主对话区轻量状态摘要（2–3 行），详版见 ContextRail。
 */

import { buildContextLines } from "@/lib/contextMeta";
import { humanizeEmbeddingMode } from "@/lib/contextMeta/embedding";
import type { ChatResponseBody, HealthBody } from "@/lib/types";

interface TurnStatusSummaryProps {
  lastTurn: ChatResponseBody | null;
  health: HealthBody | null;
}

export function TurnStatusSummary({ lastTurn, health }: TurnStatusSummaryProps) {
  if (!lastTurn) return null;

  const ctx = buildContextLines(lastTurn);
  const lines: string[] = [];

  if (ctx.laneLabel) {
    const modeHint =
      lastTurn.interaction_mode_zh?.trim() ||
      (typeof lastTurn.extra === "object" &&
      lastTurn.extra !== null &&
      typeof (lastTurn.extra as { mode?: unknown }).mode === "string"
        ? String((lastTurn.extra as { mode: string }).mode)
        : "");
    lines.push(
      modeHint && modeHint !== ctx.laneLabel
        ? `${ctx.laneLabel} · ${modeHint}`
        : ctx.laneLabel,
    );
  }

  if (ctx.statusLabel) {
    lines.push(`状态：${ctx.statusLabel}`);
  }

  if (ctx.upgradeReason) {
    lines.push(ctx.upgradeReason);
  } else if (ctx.fallbackNote) {
    lines.push(ctx.fallbackNote);
  } else if (ctx.materialsSummary) {
    lines.push(`材料：${ctx.materialsSummary}`);
  }

  const embMode =
    health?.checks &&
    typeof health.checks.embedding === "object" &&
    health.checks.embedding !== null &&
    "mode" in health.checks.embedding
      ? String((health.checks.embedding as { mode?: string }).mode)
      : null;
  const embLabel = humanizeEmbeddingMode(embMode);
  if (embLabel === "语义索引为空，当前可能使用关键词检索") {
    lines.push(embLabel);
  }

  const runtimeMode =
    health?.checks &&
    typeof health.checks.runtime_mode === "object" &&
    health.checks.runtime_mode !== null
      ? (health.checks.runtime_mode as {
          fake_llm_enabled?: boolean;
          fake_llm_source_conflict?: boolean;
        })
      : null;
  const turnRuntimeMode =
    typeof lastTurn.extra === "object" && lastTurn.extra !== null
      ? (lastTurn.extra as {
          runtime_mode?: unknown;
          fake_llm_enabled?: unknown;
          fake_llm_source_conflict?: unknown;
        })
      : null;
  const fakeEnabled =
    runtimeMode?.fake_llm_enabled === true ||
    turnRuntimeMode?.runtime_mode === "fake_llm" ||
    turnRuntimeMode?.fake_llm_enabled === true;
  const fakeConflict =
    runtimeMode?.fake_llm_source_conflict === true ||
    turnRuntimeMode?.fake_llm_source_conflict === true;
  if (fakeEnabled) {
    lines.push("当前运行模式：FAKE LLM（仅验管线连通）");
  }
  if (fakeConflict) {
    lines.push("注意：进程环境与 .env 的 FAKE 配置冲突，当前以后端实际生效值为准");
  }

  if (!lines.length) return null;

  return (
    <div
      className="border-b border-line-subtle/80 bg-surface-elevated/30 px-5 py-2 text-[11px] leading-relaxed text-ink-secondary md:px-8"
      role="status"
      aria-live="polite"
    >
      {lines.slice(0, 3).map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}
