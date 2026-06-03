"use client";

/**
 * 后端连接状态：点状指示 + 极轻文案（展示层）。
 * 避免大红错误块；offline 用柔和色带说明。
 */

import type { ConnectionState } from "@/lib/types";

interface SoftConnectionLabelProps {
  state: ConnectionState;
  latencyMs?: number | null;
}

const copy: Record<
  ConnectionState,
  { label: string; dot: string; sub?: string }
> = {
  checking: {
    label: "Checking",
    dot: "bg-ink-faint animate-pulse",
  },
  ok: {
    label: "Connected",
    dot: "bg-[var(--state-ok)]",
  },
  degraded: {
    label: "Connected",
    sub: "degraded",
    dot: "bg-[var(--state-warn)]",
  },
  offline: {
    label: "Unreachable",
    dot: "bg-[var(--state-error)]",
  },
};

export function SoftConnectionLabel({
  state,
  latencyMs,
}: SoftConnectionLabelProps) {
  const c = copy[state];
  return (
    <div className="flex items-center gap-2 text-right">
      <div
        className="flex flex-col items-end gap-0.5"
        title={
          latencyMs != null && state !== "offline"
            ? `Health ${latencyMs}ms`
            : undefined
        }
      >
        <div className="flex items-center gap-1.5">
          <span
            className={`inline-block size-1.5 rounded-full ${c.dot}`}
            aria-hidden
          />
          <span className="text-[11px] font-medium tracking-wide text-ink-secondary">
            {c.label}
          </span>
          {c.sub ? (
            <span className="text-[10px] text-ink-tertiary">· {c.sub}</span>
          ) : null}
        </div>
        {latencyMs != null && state !== "offline" ? (
          <span className="font-mono text-[10px] text-ink-faint">
            {latencyMs}ms
          </span>
        ) : null}
      </div>
    </div>
  );
}
