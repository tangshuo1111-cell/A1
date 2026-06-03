"use client";

/**
 * 聊天主流程容器（客户端容器层）。
 * 组合 hooks 与 UI 子组件；自身不含业务逻辑。
 */

import { useState } from "react";
import { AppHeader } from "@/components/layout/AppHeader";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { ChatEmptyState } from "@/components/chat/ChatEmptyState";
import { ChatMessageList } from "@/components/chat/ChatMessageList";
import { ContextRail } from "@/components/chat/ContextRail";
import { VideoCookiesGuide } from "@/components/chat/VideoCookiesGuide";
import { useHealthStatus } from "@/hooks/useHealthStatus";
import { useVideoGuide } from "@/hooks/useVideoGuide";
import { useAsyncTaskPoll } from "@/hooks/useAsyncTaskPoll";
import { useChatSession } from "@/hooks/useChatSession";
import { ChatAsyncStatus } from "@/components/chat/ChatAsyncStatus";

const ENV_FORCE_DEBUG_RAIL = process.env.NEXT_PUBLIC_SHOW_DEBUG_PANEL === "1";

export function ChatExperience() {
  const {
    health,
    connection,
    healthLatency,
    softError,
    setSoftError,
    setConnection,
  } = useHealthStatus();

  const { cookiesGuide, openManual, close: closeGuide, applySignal } = useVideoGuide();

  const {
    messages,
    input,
    setInput,
    isGenerating,
    generatingSince,
    lastTurn,
    pipelineNotice,
    longVideoGate,
    setLongVideoGate,
    sendText,
    send,
  } = useChatSession({
    connection,
    setConnection,
    setSoftError,
    applyVideoSignal: applySignal,
  });

  const asyncTaskPoll = useAsyncTaskPoll(lastTurn);

  const [debugRailOpen, setDebugRailOpen] = useState(false);
  const showDebugRail = ENV_FORCE_DEBUG_RAIL || debugRailOpen;
  const empty = messages.length === 0 && !isGenerating;

  return (
    <div className="flex h-[100dvh] max-h-[100dvh] flex-col bg-surface-page text-ink-primary">
      <AppHeader connection={connection} healthLatencyMs={healthLatency} />

      {!ENV_FORCE_DEBUG_RAIL ? (
        <div className="flex justify-end gap-3 border-b border-line-subtle px-5 py-1.5 md:px-8">
          <button
            type="button"
            onClick={openManual}
            className="text-[11px] font-medium text-ink-tertiary underline-offset-2 hover:text-ink-secondary hover:underline"
            title="为 B 站 / YouTube 等视频站配置 cookies"
          >
            视频 cookies 设置
          </button>
          <button
            type="button"
            onClick={() => setDebugRailOpen((v) => !v)}
            className="text-[11px] font-medium text-ink-tertiary underline-offset-2 hover:text-ink-secondary hover:underline"
          >
            {debugRailOpen ? "隐藏调试面板" : "显示调试面板"}
          </button>
        </div>
      ) : null}

      {softError ? (
        <div
          className="border-b border-[var(--line-default)] bg-[var(--state-error-bg)] px-5 py-2.5 text-center text-[12px] text-[var(--state-error)] md:px-8"
          role="status"
        >
          {softError}
        </div>
      ) : null}

      {pipelineNotice ? (
        <div
          className="border-b border-amber-200/80 bg-amber-50 px-5 py-2 text-center text-[11px] leading-snug text-amber-950 md:px-8 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100"
          role="status"
        >
          <span className="font-medium">排查提示 · </span>
          {pipelineNotice}
        </div>
      ) : null}

      <ChatAsyncStatus lastTurn={lastTurn} poll={asyncTaskPoll} />

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main className="flex min-h-0 min-w-0 flex-1 flex-col">
          {empty ? (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <ChatEmptyState onPick={(t) => setInput(t)} />
            </div>
          ) : (
            <ChatMessageList
              messages={messages}
              isGenerating={isGenerating}
              generatingSince={generatingSince}
            />
          )}
          <ChatComposer
            value={input}
            onChange={setInput}
            onSubmit={() => void send()}
            disabled={isGenerating || connection === "offline"}
          />
        </main>
        {showDebugRail ? (
          <ContextRail lastTurn={lastTurn} health={health} />
        ) : null}
      </div>

      <VideoCookiesGuide
        open={cookiesGuide.open}
        onClose={closeGuide}
        triggeringUrl={cookiesGuide.url}
        failureHint={cookiesGuide.hint}
        onResolved={(url) => {
          closeGuide();
          void sendText(url, { isAutoRetry: true });
        }}
      />

      {longVideoGate ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="long-video-gate-title"
        >
          <div className="max-w-md rounded-lg border border-line-subtle bg-surface-page p-5 shadow-lg">
            <p
              id="long-video-gate-title"
              className="text-sm font-medium text-ink-primary"
            >
              长视频语音识别确认
            </p>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">
              检测到视频约 {Math.round(longVideoGate.durationSec)} 秒（约{" "}
              {Math.max(1, Math.round(longVideoGate.durationSec / 60))} 分钟），已超过免确认上限{" "}
              {longVideoGate.autoMax} 秒。继续将下载音频并使用云端 ASR，可能耗时并产生费用。
              {longVideoGate.title ? (
                <>
                  <br />
                  <span className="text-ink-tertiary">标题：{longVideoGate.title}</span>
                </>
              ) : null}
            </p>
            <p className="mt-2 text-[12px] text-ink-tertiary">
              当前策略下可处理上限约 {longVideoGate.effectiveMax} 秒（后端{" "}
              <code className="rounded bg-surface-input px-1 text-[11px]">
                VIDEO_MAX_AUDIO_SECONDS
              </code>{" "}
              与{" "}
              <code className="rounded bg-surface-input px-1 text-[11px]">
                V16_WEB_VIDEO_ASR_ABS_MAX_SEC
              </code>{" "}
              取较小值）。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded border border-line-subtle px-3 py-1.5 text-[12px] text-ink-secondary hover:bg-surface-input"
                onClick={() => setLongVideoGate(null)}
              >
                取消
              </button>
              <button
                type="button"
                className="rounded bg-[var(--accent)] px-3 py-1.5 text-[12px] font-medium text-white hover:opacity-90"
                onClick={() => {
                  const g = longVideoGate;
                  setLongVideoGate(null);
                  void sendText(g.messageText, {
                    confirmLongWebVideoAsr: true,
                    skipLongVideoProbe: true,
                    isAutoRetry: g.isAutoRetry,
                  });
                }}
              >
                确认并发送
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
