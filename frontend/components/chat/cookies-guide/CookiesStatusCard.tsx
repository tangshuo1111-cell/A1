import { CheckCircle2, FileWarning, Trash2 } from "lucide-react";
import type { VideoCookiesStatusBody } from "@/lib/types";

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function describeSource(
  s: string,
): { tone: "ok" | "warn" | "info"; text: string } {
  if (s === "file") return { tone: "ok", text: "已配置 cookies 文件" };
  if (s.startsWith("browser:")) {
    const b = s.slice(8);
    return {
      tone: "warn",
      text: `当前从浏览器读 cookies（${b}）；Win11 上常因 DPAPI 失败，建议改用上传文件方式`,
    };
  }
  return {
    tone: "info",
    text: "尚未配置 cookies（匿名访问 → 主流视频站会失败）",
  };
}

interface CookiesStatusCardProps {
  status: VideoCookiesStatusBody | null;
  loading: boolean;
  errMsg: string | null;
  busy: "upload" | "delete" | null;
  onDelete: () => void;
}

export function CookiesStatusCard({
  status,
  loading,
  errMsg,
  busy,
  onDelete,
}: CookiesStatusCardProps) {
  const sourceDesc = status ? describeSource(status.source) : null;
  const matched = status?.managed_file.matched_whitelist_domains ?? [];
  const sizeText = status ? formatBytes(status.managed_file.size_bytes) : "";
  const modText = status ? formatTime(status.managed_file.modified_iso) : "";

  return (
    <section className="mb-5 rounded-xl border border-line-subtle bg-surface-input/40 px-4 py-3">
      <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-ink-faint">
        当前 cookies 状态
      </p>
      {loading && !status ? (
        <p className="mt-1 text-[12px] text-ink-tertiary">读取中…</p>
      ) : status ? (
        <>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-ink-secondary">
            <span
              className={
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium " +
                (sourceDesc?.tone === "ok"
                  ? "bg-emerald-100 text-emerald-800"
                  : sourceDesc?.tone === "warn"
                    ? "bg-amber-100 text-amber-900"
                    : "bg-zinc-100 text-zinc-700")
              }
            >
              {sourceDesc?.tone === "ok" ? (
                <CheckCircle2 className="size-3" />
              ) : (
                <FileWarning className="size-3" />
              )}
              {sourceDesc?.text}
            </span>
          </div>
          {status.managed_file.exists ? (
            <dl className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-tertiary sm:grid-cols-2">
              <div>
                <dt className="inline text-ink-faint">已涵盖站点：</dt>
                <dd className="inline text-ink-secondary">
                  {matched.length > 0
                    ? matched.join(" / ")
                    : "（无白名单匹配）"}
                </dd>
              </div>
              <div>
                <dt className="inline text-ink-faint">文件大小：</dt>
                <dd className="inline text-ink-secondary">{sizeText}</dd>
              </div>
              <div>
                <dt className="inline text-ink-faint">最后更新：</dt>
                <dd className="inline text-ink-secondary">{modText}</dd>
              </div>
              <div className="sm:col-span-1">
                <button
                  type="button"
                  onClick={onDelete}
                  disabled={!!busy}
                  className="inline-flex items-center gap-1 text-[11px] text-rose-700 hover:text-rose-900 disabled:opacity-50"
                >
                  <Trash2 className="size-3" /> 清除当前 cookies
                </button>
              </div>
            </dl>
          ) : null}
        </>
      ) : (
        <p className="mt-1 text-[12px] text-ink-tertiary">
          {errMsg ?? "无法读取状态。"}
        </p>
      )}
    </section>
  );
}
