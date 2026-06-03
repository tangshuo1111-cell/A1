"use client";

import { useMemo } from "react";
import { X } from "lucide-react";
import { useCookiesUpload } from "@/hooks/useCookiesUpload";
import { StepGuide, resolveSitePreset } from "./cookies-guide/StepGuide";
import { CookiesStatusCard } from "./cookies-guide/CookiesStatusCard";
import { UploadZone } from "./cookies-guide/UploadZone";

const FAQ_ITEMS: [string, string][] = [
  ["为什么要 cookies？", "因为 B 站、YouTube 等已经基本不允许匿名抓取（反爬 / 风控）。yt-dlp 拿你登录态的 cookies 等价于以你本人身份访问，所以站方会放行。"],
  ["cookies 会被传到哪？", "只走本机后端，落到 _local/data/cookies/video_cookies.txt。**不写 .env、不上传任何外部 API**。重启后端后会自动失效（除非你手动配 .env），点「清除」即可即时清掉。"],
  ["什么时候需要重做？", "cookies 会过期：B 站 ~30 天、YouTube 几小时～几天、抖音/TikTok 几天到一周。下次贴链接还失败 → 来这里重新导一份就行。"],
  ["每个站都要单独导吗？", "建议是。cookies 是按域名隔离的，扩展一次只能导当前打开站的 cookies。但你可以**累加**：先上传 B 站，再上传 YouTube，系统会以最后上传的为准——所以推荐**多站合并到一份 cookies.txt 后再上传**（手动把多份 cookies.txt 拼接也行）。"],
];

function FaqSection() {
  return (
    <details className="mt-4 rounded-lg border border-line-subtle px-3 py-2 text-[11.5px] text-ink-tertiary">
      <summary className="cursor-pointer text-[12px] font-medium text-ink-secondary">
        常见疑问 / 安全说明
      </summary>
      <div className="mt-2 space-y-1.5 leading-relaxed">
        {FAQ_ITEMS.map(([q, a]) => (
          <p key={q}>
            <span className="font-medium text-ink-primary">{q}</span> {a}
          </p>
        ))}
      </div>
    </details>
  );
}

interface VideoCookiesGuideProps {
  open: boolean;
  onClose: () => void;
  triggeringUrl?: string | null;
  failureHint?: string | null;
  onResolved?: (triggeringUrl: string) => void;
}

export function VideoCookiesGuide({
  open,
  onClose,
  triggeringUrl,
  failureHint,
  onResolved,
}: VideoCookiesGuideProps) {
  const {
    status,
    loading,
    busy,
    errMsg,
    okMsg,
    drag,
    setDrag,
    fileRef,
    handleFile,
    handleDelete,
  } = useCookiesUpload({ open, triggeringUrl, onResolved });

  const preset = useMemo(
    () => resolveSitePreset(triggeringUrl ?? null),
    [triggeringUrl],
  );
  const matched = status?.managed_file.matched_whitelist_domains ?? [];

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="视频 cookies 上传引导"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-line-default bg-surface-card shadow-2xl">
        {/* 顶部 */}
        <div className="flex items-start justify-between gap-4 border-b border-line-subtle px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-ink-primary">
              视频下载需要你提供 cookies
            </h2>
            <p className="mt-1 text-[12px] leading-snug text-ink-tertiary">
              {failureHint ??
                "刚才的视频链接抓不到内容，多半是因为视频站要求登录态。把你浏览器里的 cookies 导一份给我，下次就能正常解析。"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="rounded-md p-1 text-ink-tertiary hover:bg-surface-input hover:text-ink-primary"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <CookiesStatusCard
            status={status}
            loading={loading}
            errMsg={errMsg}
            busy={busy}
            onDelete={() => void handleDelete()}
          />

          <StepGuide preset={preset} matched={matched} />

          <UploadZone
            drag={drag}
            onDragChange={setDrag}
            onFile={(f) => void handleFile(f)}
            busy={busy}
            fileRef={fileRef}
            status={status}
            okMsg={okMsg}
            errMsg={errMsg}
          />

          <FaqSection />
        </div>

        <div className="flex justify-end gap-2 border-t border-line-subtle bg-surface-input/40 px-6 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-line-default bg-surface-card px-3 py-1.5 text-[12px] font-medium text-ink-primary hover:bg-surface-input"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
