import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError } from "@/lib/client";
import {
  deleteVideoCookies,
  fetchVideoCookiesStatus,
  uploadVideoCookies,
} from "@/lib/api";
import type { VideoCookiesStatusBody } from "@/lib/types";

export interface UseCookiesUploadOptions {
  open: boolean;
  triggeringUrl?: string | null;
  onResolved?: (triggeringUrl: string) => void;
}

export function useCookiesUpload({
  open,
  triggeringUrl,
  onResolved,
}: UseCookiesUploadOptions) {
  const [status, setStatus] = useState<VideoCookiesStatusBody | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<"upload" | "delete" | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErrMsg(null);
    try {
      const s = await fetchVideoCookiesStatus();
      setStatus(s);
    } catch (e) {
      setErrMsg(
        e instanceof ApiRequestError
          ? e.status === 0
            ? "无法连接后端，请确认 API 已启动。"
            : `读取状态失败：${e.message}`
          : "读取状态失败",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      void refresh();
      setOkMsg(null);
    }
  }, [open, refresh]);

  const handleFile = useCallback(
    async (file: File | null) => {
      if (!file || busy) return;
      setBusy("upload");
      setErrMsg(null);
      setOkMsg(null);
      try {
        const r = await uploadVideoCookies(file);
        const matched = r.matched_whitelist_domains.join(" / ") || "（识别中）";

        const merge = r.merge;
        let mergeNote = "";
        if (merge) {
          const newDomains = merge.new_domains.join("、");
          const kept = merge.kept_old_domains;
          const replaced = merge.replaced_domains;
          const parts: string[] = [];
          if (newDomains) parts.push(`本次：${newDomains}`);
          if (replaced.length > 0)
            parts.push(`已刷新登录态：${replaced.join("、")}`);
          if (kept.length > 0) parts.push(`已保留：${kept.join("、")}`);
          if (parts.length > 0) mergeNote = `（${parts.join("；")}）`;
        }

        const triggerHost = (() => {
          if (!triggeringUrl) return null;
          try {
            return new URL(triggeringUrl).hostname.toLowerCase();
          } catch {
            return null;
          }
        })();
        const cookiesNowCoverTrigger =
          !!triggerHost &&
          r.matched_whitelist_domains.some(
            (d) => triggerHost === d || triggerHost.endsWith("." + d),
          );

        if (cookiesNowCoverTrigger && triggeringUrl && onResolved) {
          setOkMsg(
            `上传成功！已为 ${matched} 启用 cookies${mergeNote}，正在自动重新尝试这条链接……`,
          );
          await new Promise((res) => setTimeout(res, 700));
          onResolved(triggeringUrl);
        } else {
          setOkMsg(`上传成功！当前可用站点：${matched}${mergeNote}`);
          await refresh();
        }
      } catch (e) {
        setErrMsg(
          e instanceof ApiRequestError
            ? e.message || `HTTP ${e.status}`
            : "上传失败",
        );
      } finally {
        setBusy(null);
      }
    },
    [busy, refresh, triggeringUrl, onResolved],
  );

  const handleDelete = useCallback(async () => {
    if (busy) return;
    setBusy("delete");
    setErrMsg(null);
    setOkMsg(null);
    try {
      const r = await deleteVideoCookies();
      setOkMsg(
        r.removed ? "已清除当前 cookies 文件。" : "当前没有可清除的文件。",
      );
      await refresh();
    } catch (e) {
      setErrMsg(
        e instanceof ApiRequestError
          ? e.message || `HTTP ${e.status}`
          : "清除失败",
      );
    } finally {
      setBusy(null);
    }
  }, [busy, refresh]);

  return {
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
  };
}
