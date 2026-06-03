import type { RefObject } from "react";
import { UploadCloud } from "lucide-react";
import type { VideoCookiesStatusBody } from "@/lib/types";
import { formatBytes } from "./CookiesStatusCard";

interface UploadZoneProps {
  drag: boolean;
  onDragChange: (dragging: boolean) => void;
  onFile: (file: File | null) => void;
  busy: "upload" | "delete" | null;
  fileRef: RefObject<HTMLInputElement | null>;
  status: VideoCookiesStatusBody | null;
  okMsg: string | null;
  errMsg: string | null;
}

export function UploadZone({
  drag,
  onDragChange,
  onFile,
  busy,
  fileRef,
  status,
  okMsg,
  errMsg,
}: UploadZoneProps) {
  return (
    <section className="mb-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          onDragChange(true);
        }}
        onDragLeave={() => onDragChange(false)}
        onDrop={(e) => {
          e.preventDefault();
          onDragChange(false);
          const f = e.dataTransfer.files?.[0] ?? null;
          onFile(f);
        }}
        className={
          "flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-7 text-center transition " +
          (drag
            ? "border-accent bg-accent-soft/40"
            : "border-line-default bg-surface-input/30 hover:border-accent-muted")
        }
      >
        <UploadCloud className="size-7 text-ink-tertiary" strokeWidth={1.25} />
        <p className="mt-2 text-[12.5px] font-medium text-ink-primary">
          把 cookies.txt 拖到这里，或者
        </p>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={!!busy}
          className="mt-2 inline-flex items-center gap-1 rounded-md border border-line-default bg-surface-card px-3 py-1.5 text-[12px] font-medium text-ink-primary shadow-sm hover:bg-surface-input disabled:opacity-50"
        >
          {busy === "upload" ? "上传中…" : "选择文件"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,text/plain"
          hidden
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />
        <p className="mt-2 text-[10.5px] text-ink-faint">
          ≤ {status ? formatBytes(status.upload_max_bytes) : "1 MB"}
          ，仅识别白名单站点：
          {(status?.whitelist_domains ?? []).slice(0, 6).join(" / ") || "—"}
        </p>
      </div>

      {okMsg ? (
        <p className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-[12px] text-emerald-900">
          {okMsg}
        </p>
      ) : null}
      {errMsg ? (
        <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-[12px] text-rose-900">
          {errMsg}
        </p>
      ) : null}
    </section>
  );
}
