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
