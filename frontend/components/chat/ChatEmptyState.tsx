"use client";

/**
 * 首屏空状态：克制欢迎语 + 示例 prompt（展示层）。
 * 气质接近成熟产品首次打开，而非教程或营销长页。
 */

import { Sparkles } from "lucide-react";

const SUGGESTIONS = [
  "你好，今天先随便聊两句。",
  "知识库里目前有哪些主题或文件线索？",
  "帮我去查一下广州今天的天气（公开网页摘要）。",
];

interface ChatEmptyStateProps {
  onPick: (text: string) => void;
}

export function ChatEmptyState({ onPick }: ChatEmptyStateProps) {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center px-4 py-16 text-center">
      <div
        className="mb-6 flex size-11 items-center justify-center rounded-2xl border border-line-default bg-surface-card shadow-[var(--shadow-soft)]"
        aria-hidden
      >
        <Sparkles
          className="size-5 text-accent opacity-90"
          strokeWidth={1.25}
        />
      </div>
      <h1 className="mb-2 text-lg font-medium tracking-tight text-ink-primary md:text-xl">
        从这里开始
      </h1>
      <p className="mb-10 max-w-sm text-pretty text-sm leading-relaxed text-ink-secondary">
        轻量多 Agent 演示：可闲聊、可走知识库、可读示例文件，也可在开启网页检索时整理公开摘要。
      </p>
      <p className="mb-3 w-full text-left text-[10px] font-medium uppercase tracking-[0.14em] text-ink-faint">
        Try
      </p>
      <ul className="flex w-full flex-col gap-2">
        {SUGGESTIONS.map((s) => (
          <li key={s}>
            <button
              type="button"
              onClick={() => onPick(s)}
              className="group w-full rounded-[var(--radius-md)] border border-line-default bg-surface-elevated px-4 py-3 text-left text-sm leading-snug text-ink-secondary shadow-[0_1px_0_rgba(44,38,34,0.02)] transition-colors hover:border-accent-soft/40 hover:bg-surface-card hover:text-ink-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-soft"
            >
              <span className="block group-hover:text-ink-primary">{s}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
