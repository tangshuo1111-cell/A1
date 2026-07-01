"use client";

/**
 * 消息滚动区：用户 / 助手气泡区分柔和，长文可读（展示层）。
 * 协作：ChatExperience 传入 messages 与 isGenerating。
 */

import { useEffect, useRef, useState } from "react";
import { sanitizeAssistantAnswer } from "@/lib/answerSanitizer";
import type { ChatMessage } from "@/lib/types";

interface ChatMessageListProps {
  messages: ChatMessage[];
  isGenerating: boolean;
  generatingSince: number | null;
}

function formatElapsedSeconds(ms: number): string {
  const sec = Math.max(0, ms) / 1000;
  return `${sec.toFixed(sec >= 10 ? 1 : 1)} 秒`;
}

export function ChatMessageList({
  messages,
  isGenerating,
  generatingSince,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [nowMs, setNowMs] = useState<number>(Date.now());

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isGenerating]);

  useEffect(() => {
    if (!isGenerating || !generatingSince) {
      return;
    }
    const timer = window.setInterval(() => {
      setNowMs(Date.now());
    }, 250);
    return () => window.clearInterval(timer);
  }, [isGenerating, generatingSince]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-6 pt-2 md:px-6">
      <div className="mx-auto flex max-w-2xl flex-col gap-5">
        {messages.map((m) => {
          const display =
            m.role === "assistant"
              ? sanitizeAssistantAnswer(m.content)
              : m.content;
          return (
            <article
              key={m.id}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={
                  m.role === "user"
                    ? "max-w-[min(100%,36rem)] rounded-[var(--radius-lg)] rounded-br-md border border-line-subtle bg-surface-card px-4 py-3 text-sm leading-relaxed text-ink-primary shadow-[var(--shadow-soft)]"
                    : "max-w-[min(100%,40rem)] rounded-[var(--radius-lg)] rounded-bl-md border border-line-subtle bg-surface-elevated/80 px-4 py-3 text-sm leading-relaxed text-ink-primary"
                }
              >
                <p className="whitespace-pre-wrap break-words">{display}</p>
                {m.role === "assistant" &&
                (m.chainLabel || m.elapsedMs != null || (m.sourceHints && m.sourceHints.length > 0)) ? (
                  <div className="mt-2 border-t border-line-subtle/60 pt-2 space-y-1">
                    {(m.chainLabel || m.elapsedMs != null) ? (
                      <p className="text-[10px] leading-snug text-ink-tertiary">
                        {m.chainLabel ? (
                          <span className="font-medium text-ink-secondary">
                            {m.chainLabel}
                          </span>
                        ) : null}
                        {m.chainLabel && m.elapsedMs != null ? " · " : null}
                        {m.elapsedMs != null
                          ? `本轮耗时 ${formatElapsedSeconds(m.elapsedMs)}`
                          : null}
                      </p>
                    ) : null}
                    {m.sourceHints && m.sourceHints.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {m.sourceHints.map((hint) => (
                          <span
                            key={hint}
                            className="inline-block rounded-full border border-line-subtle bg-surface-input px-2 py-0.5 text-[10px] text-ink-tertiary"
                          >
                            {hint}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </article>
          );
        })}
        {isGenerating ? (
          <div className="flex justify-start">
            <div className="flex items-center gap-3 rounded-[var(--radius-lg)] border border-line-subtle bg-surface-elevated/60 px-4 py-3">
              <div className="flex flex-col gap-1">
                <span className="text-xs text-ink-tertiary">正在整理回复</span>
                <span className="text-[11px] font-medium text-ink-secondary">
                  {generatingSince
                    ? `已等待 ${formatElapsedSeconds(nowMs - generatingSince)}`
                    : "已等待 0.0 秒"}
                </span>
              </div>
              <span className="flex gap-1" aria-hidden>
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="maqa-breathe-dot size-1 rounded-full bg-accent-soft"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </span>
            </div>
          </div>
        ) : null}
        <div ref={bottomRef} className="h-1 shrink-0" />
      </div>
    </div>
  );
}
