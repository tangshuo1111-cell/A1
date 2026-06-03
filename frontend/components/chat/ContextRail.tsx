"use client";

/**
 * 右侧调试轨：本轮 extra 回填（不以关键词猜测业务：入库/检索策略仅显示后端返回值）。
 */

import { ChevronDown } from "lucide-react";
import {
  buildContextLines,
  buildV15PrimaryRows,
  collectLegacyExtraLines,
  collectOtherExtraReplayLines,
} from "@/lib/contextMeta";
import type { ChatResponseBody, HealthBody } from "@/lib/types";
import { readPendingKind } from "@/lib/chatTaskFields";

interface ContextRailProps {
  lastTurn: ChatResponseBody | null;
  health: HealthBody | null;
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string | null | undefined;
  mono?: boolean;
}) {
  if (!value && value !== "0") return null;
  return (
    <div className="space-y-0.5">
      <p className="text-[9px] font-medium uppercase tracking-[0.12em] text-ink-faint">
        {label}
      </p>
      <p
        className={`break-words text-[11px] leading-snug text-ink-secondary ${mono ? "font-mono text-[10px] text-ink-tertiary" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}

function PanelBody({
  lastTurn,
  health,
}: {
  lastTurn: ChatResponseBody | null;
  health: HealthBody | null;
}) {
  const ex =
    lastTurn?.extra && typeof lastTurn.extra === "object" && lastTurn.extra !== null
      ? (lastTurn.extra as Record<string, unknown>)
      : null;
  const ctx = lastTurn ? buildContextLines(lastTurn) : null;
  const v15Rows = ex ? buildV15PrimaryRows(ex) : [];
  const legacyLines = ex ? collectLegacyExtraLines(ex) : [];
  const otherLines = ex ? collectOtherExtraReplayLines(ex) : [];
  const timingRows = ex
    ? [
        ["Total", ex.timing_total_ms ?? lastTurn?.workflow_elapsed_ms],
        ["Main", ex.main_ms],
        ["Middle", ex.middle_ms],
        ["Answer", ex.answer_ms],
        ["Fast answer", ex.fast_answer_ms],
        ["Weather", ex.fast_weather_elapsed_ms],
        ["Session snapshot", ex.session_snapshot_ms],
        ["Session update", ex.session_update_ms],
        ["Extra build", ex.extra_build_ms],
      ]
        .map(([label, value]) => ({
          label: String(label),
          value:
            typeof value === "number"
              ? `${(value / 1000).toFixed(1)} 秒`
              : typeof value === "string" && value
                ? value
                : "",
        }))
        .filter((r) => r.value)
    : [];

  const emb =
    health?.checks &&
    typeof health.checks.embedding === "object" &&
    health.checks.embedding !== null &&
    "mode" in health.checks.embedding
      ? String((health.checks.embedding as { mode?: string }).mode)
      : null;

  return (
    <div className="space-y-4 pt-1">
      {lastTurn ? (
        <>
          <details className="group/meta border border-line-subtle/80 bg-surface-elevated/20 px-2 py-2">
            <summary className="cursor-pointer list-none text-[10px] font-medium uppercase tracking-[0.1em] text-ink-faint">
              ID / Router / Workflow（次要元数据）
            </summary>
            <div className="mt-2 space-y-2">
              <Row label="Session" value={lastTurn.session_id ?? undefined} mono />
              <Row label="Task" value={lastTurn.task_id ?? undefined} mono />
              <Row label="Task status" value={lastTurn.task_status ?? undefined} />
              <Row label="pending_kind" value={readPendingKind(lastTurn) ?? undefined} mono />
              <Row label="Request" value={lastTurn.request_id ?? undefined} mono />
              <Row label="Router" value={lastTurn.router_source ?? undefined} />
              <Row
                label="Answer channel（HTTP 外层）"
                value={
                  lastTurn?.extra &&
                  typeof lastTurn.extra === "object" &&
                  lastTurn.extra !== null &&
                  "answer_channel" in lastTurn.extra
                    ? String((lastTurn.extra as Record<string, unknown>).answer_channel)
                    : undefined
                }
              />
              <Row label="Evidence" value={lastTurn.evidence_state ?? undefined} />
              <Row label="Fallback" value={ctx?.fallbackNote ?? undefined} />
            </div>
          </details>

          <section className="rounded border border-emerald-900/25 bg-emerald-950/15 px-2 py-2 dark:bg-emerald-950/35">
            <p className="mb-2 text-[9px] font-semibold uppercase tracking-[0.14em] text-emerald-800/95 dark:text-emerald-300/95">
              V15 主链（extra 回放）
            </p>
            <div className="space-y-2">
              {ctx?.v15Plan ? <Row label="Plan 摘要（含 answer_mode）" value={ctx.v15Plan} mono /> : null}
              {ctx?.v15Bundle ? <Row label="Bundle 摘要（sufficiency/chunks/fail）" value={ctx.v15Bundle} mono /> : null}
              {ctx?.v14RetrievalLine ? (
                <Row label="检索 trace（V14 单行）" value={ctx.v14RetrievalLine} mono />
              ) : null}
              {ctx?.v15FinalStatus ? (
                <Row label="final_status（v15_execution / 对齐字段）" value={ctx.v15FinalStatus} mono />
              ) : null}
              {ctx?.toolsSummary ? <Row label="Legacy tools trace" value={ctx.toolsSummary} mono /> : null}
              {ctx?.retrievalLabel ? <Row label="primary_path hint" value={ctx.retrievalLabel} mono /> : null}
              {v15Rows.map((r) => (
                <Row key={r.label} label={r.label} value={r.value} mono />
              ))}
            </div>
          </section>

          {timingRows.length > 0 ? (
            <section className="rounded border border-line-subtle bg-surface-elevated/30 px-2 py-2">
              <p className="mb-2 text-[9px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
                耗时拆分
              </p>
              <div className="space-y-2">
                {timingRows.map((r) => (
                  <Row key={r.label} label={r.label} value={r.value} />
                ))}
              </div>
            </section>
          ) : null}

          {otherLines.length > 0 ? (
            <details className="group/other border-t border-line-subtle pt-3">
              <summary className="cursor-pointer list-none text-[10px] font-medium uppercase tracking-[0.12em] text-ink-faint">
                其它后端 extra（非 V15 白名单，原始回放）
              </summary>
              <div className="mt-2 space-y-2">
                {otherLines.map(({ key, value }) => (
                  <div key={key} className="space-y-0.5">
                    <p className="text-[9px] font-medium uppercase tracking-[0.1em] text-ink-faint">
                      {key}
                    </p>
                    <p className="break-all font-mono text-[10px] leading-snug text-ink-tertiary">
                      {value || "—"}
                    </p>
                  </div>
                ))}
              </div>
            </details>
          ) : null}

          {legacyLines.length > 0 ? (
            <details className="group/leg border-t border-line-subtle pt-3">
              <summary className="cursor-pointer list-none text-[10px] font-medium uppercase tracking-[0.12em] text-amber-800/90 dark:text-amber-300/90">
                Legacy / V11 兼容字段（折叠）— 非当前默认主链
              </summary>
              <div className="mt-2 space-y-2">
                {legacyLines.map(({ key, value }) => (
                  <div key={key} className="space-y-0.5">
                    <p className="text-[9px] font-medium uppercase tracking-[0.1em] text-ink-faint">
                      {key}
                    </p>
                    <p className="break-all font-mono text-[10px] leading-snug text-ink-tertiary">
                      {value || "—"}
                    </p>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </>
      ) : (
        <p className="text-[11px] leading-relaxed text-ink-faint">
          发送第一条消息后显示本轮 extra 回填。
        </p>
      )}
      {emb ? <Row label="Embedding" value={emb} /> : null}
    </div>
  );
}

export function ContextRail({ lastTurn, health }: ContextRailProps) {
  return (
    <>
      <aside className="hidden w-[240px] shrink-0 border-l border-line-subtle bg-surface-elevated/40 px-5 py-6 lg:block">
        <p className="mb-1 text-[10px] font-medium uppercase tracking-[0.14em] text-ink-faint">
          调试 · Context
        </p>
        <p className="mb-4 text-[10px] text-ink-faint/90">
          默认区为后端 extra/V15 白名单；V11 类键仅在「Legacy」折叠。
          「strategy_requested / filters_applied」若出现在 V14 retrieval 单行或 v15_retrieval_filters 即以原文为准——前端不推导。
        </p>
        <PanelBody lastTurn={lastTurn} health={health} />
      </aside>

      <div className="border-t border-line-subtle bg-surface-elevated/30 lg:hidden">
        <details className="group px-4 py-2">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 py-2 text-[11px] font-medium text-ink-tertiary marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="uppercase tracking-[0.12em]">调试 Context</span>
            <ChevronDown className="size-3.5 shrink-0 transition-transform group-open:rotate-180" />
          </summary>
          <div className="border-t border-line-subtle pb-4 pt-3">
            <PanelBody lastTurn={lastTurn} health={health} />
          </div>
        </details>
      </div>
    </>
  );
}
