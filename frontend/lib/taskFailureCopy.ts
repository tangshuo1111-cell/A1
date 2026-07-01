export interface TaskFailureCopy {
  summary: string;
  detail: string;
}

export function humanizeTaskFailure(raw: string | null | undefined): TaskFailureCopy | null {
  const detail = String(raw ?? "").trim();
  if (!detail) return null;

  const normalized = detail.toLowerCase();
  if (normalized.includes("yt_dlp_audio_failed")) {
    return {
      summary:
        "视频音频下载失败，可能是站点限制、cookies 失效、链接权限不足或当前网络不可用。",
      detail,
    };
  }
  if (normalized.includes("downloaderror")) {
    return {
      summary: "后台下载失败，请检查链接可访问性、登录态或网络后重试。",
      detail,
    };
  }
  if (normalized.includes("task status unavailable")) {
    return {
      summary: "后台任务状态暂时不可用，请稍后重试。",
      detail,
    };
  }

  return {
    summary: detail,
    detail,
  };
}
