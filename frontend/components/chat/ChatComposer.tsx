"use client";

/**
 * 底部输入区：大圆角、轻阴影、与发送按钮统一暖色体系（展示层）。
 * Enter 发送，Shift+Enter 换行；协作 ChatExperience。
 */

import { ArrowUp } from "lucide-react";
import { useCallback, useEffect, useRef } from "react";

interface ChatComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  placeholder?: string;
}

export function ChatComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = "Message…",
}: ChatComposerProps) {
  const taRef = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    const max = 160;
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, []);

  useEffect(() => {
    resize();
  }, [value, resize]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && value.trim()) onSubmit();
    }
  };

  return (
    <div className="border-t border-line-subtle bg-surface-page/90 px-4 py-4 backdrop-blur-[6px] md:px-6">
      <div className="mx-auto flex max-w-2xl gap-2">
        <div className="relative min-h-[48px] flex-1 rounded-[var(--radius-xl)] border border-line-default bg-surface-input shadow-[var(--shadow-soft)] transition-[border-color,box-shadow] focus-within:border-accent-soft/50 focus-within:shadow-[0_0_0_3px_var(--accent-muted)]">
          <textarea
            ref={taRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={disabled}
            placeholder={placeholder}
            className="max-h-40 min-h-[48px] w-full resize-none rounded-[var(--radius-xl)] bg-transparent px-4 py-3 pr-3 text-sm leading-relaxed text-ink-primary placeholder:text-ink-faint focus:outline-none disabled:opacity-50"
            aria-label="Message input"
          />
        </div>
        <button
          type="button"
          disabled={disabled || !value.trim()}
          onClick={onSubmit}
          className="flex size-12 shrink-0 items-center justify-center rounded-[var(--radius-lg)] border border-line-default bg-surface-card text-accent shadow-[var(--shadow-soft)] transition-colors hover:border-accent-soft/45 hover:bg-accent-muted disabled:pointer-events-none disabled:opacity-35"
          aria-label="Send"
        >
          <ArrowUp className="size-5" strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}
