"use client";

/**
 * 右侧状态解释轨：把后端已有 trace/extra 转成用户可理解的“这次怎么答的”。
 */

import { ChevronDown } from "lucide-react";
import {
  buildContextLines,
  buildV15PrimaryRows,
  collectLegacyExtraLines,
  collectOtherExtraReplayLines,
} from "@/lib/contextMeta";
import { humanizeEmbeddingMode } from "@/lib/contextMeta/embedding";
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

  const embLabel = humanizeEmbeddingMode(emb);

  return (
    <div className="space-y-4 pt-1">
      {embLabel ? (
        <Row label="语义检索" value={embLabel} />
      ) : null}
      {lastTurn ? (
        <>
          <details className="group/meta border border-line-subtle/80 bg-surface-elevated/20 px-2 py-2">
            <summary className="cursor-pointer list-none text-[10px] font-medium uppercase tracking-[0.1em] text-ink-faint">
              这次回答的状态说明
            </summary>
            <div className="mt-2 space-y-2">
              <Row label="主路径" value={ctx?.laneLabel ?? undefined} />
              <Row label="处理状态" value={ctx?.statusLabel ?? undefined} />
              <Row label="为何升级 / 等待" value={ctx?.upgradeReason ?? undefined} />
              <Row label="材料概览" value={ctx?.materialsSummary ?? undefined} />
              <Row label="材料数量" value={ctx?.materialsCountLabel ?? undefined} />
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
              可解释主链
            </p>
            <div className="space-y-2">
              {ctx?.v15Plan ? <Row label="路径规划" value={ctx.v15Plan} mono /> : null}
              {ctx?.v15Bundle ? <Row label="材料与执行摘要" value={ctx.v15Bundle} mono /> : null}
              {ctx?.v14RetrievalLine ? (
                <Row label="检索记录" value={ctx.v14RetrievalLine} mono />
              ) : null}
              {ctx?.v15FinalStatus ? (
                <Row label="执行结果" value={ctx.v15FinalStatus} mono />
              ) : null}
              {ctx?.toolsSummary ? <Row label="调用线索" value={ctx.toolsSummary} mono /> : null}
              {ctx?.retrievalLabel ? <Row label="路径提示" value={ctx.retrievalLabel} mono /> : null}
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
                其它系统字段（原始回放）
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
                兼容字段（折叠）— 非当前默认主链
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
          发送第一条消息后显示这次回答走了哪条路径、用了哪些材料、为什么升级或等待。
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
          回答依据与状态
        </p>
        <p className="mb-4 text-[10px] text-ink-faint/90">
          展示本轮回答走了哪条路径、用了哪些材料、是否升级到复杂处理，以及系统返回的关键状态。
          更底层的兼容字段仍保留在折叠区，便于排查。
        </p>
        <PanelBody lastTurn={lastTurn} health={health} />
      </aside>

      <div className="border-t border-line-subtle bg-surface-elevated/30 lg:hidden">
        <details className="group px-4 py-2">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 py-2 text-[11px] font-medium text-ink-tertiary marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="uppercase tracking-[0.12em]">回答依据与状态</span>
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
