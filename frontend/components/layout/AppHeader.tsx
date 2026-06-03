"use client";

/**
 * 极简顶栏（展示层 / layout）。
 * 仅品牌与连接状态，不抢主视觉；协作 SoftConnectionLabel 与 ChatExperience 传入的状态。
 */

import { SoftConnectionLabel } from "@/components/chat/SoftConnectionLabel";
import type { ConnectionState } from "@/lib/types";

interface AppHeaderProps {
  connection: ConnectionState;
  healthLatencyMs?: number | null;
}

export function AppHeader({ connection, healthLatencyMs }: AppHeaderProps) {
  return (
    <header className="flex shrink-0 items-center justify-between border-b border-line-subtle px-5 py-3 md:px-8">
      <div className="flex flex-col gap-0.5">
        <span className="text-[0.8125rem] font-medium tracking-tight text-ink-primary">
          Light MAQA
        </span>
        <span className="text-[11px] font-normal tracking-wide text-ink-tertiary">
          闲聊 · 知识库 · 工具与网页检索
        </span>
      </div>
      <SoftConnectionLabel state={connection} latencyMs={healthLatencyMs} />
    </header>
  );
}
