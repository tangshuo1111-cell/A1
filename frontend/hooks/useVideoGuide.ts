"use client";

import { useCallback, useState } from "react";
import type { ChatResponseBody } from "@/lib/types";

/* ---------------------------------------------------------------------------
 * V11 R3：从 chat extra 里识别"视频 URL 链失败 + cookies 缺失"信号
 * --------------------------------------------------------------------------- */
export interface VideoCookiesNeed {
  url: string | null;
  hint: string;
}

/**
 * ``"no_video_in_round"`` — 本轮根本没碰视频（保留用户正在看的卡片）；
 * ``null`` — 本轮碰了视频但不需要弹卡（重置陈旧卡片）；
 * 对象 — 本轮需要弹卡。
 */
export type CookiesGuideSignal = VideoCookiesNeed | null | "no_video_in_round";

export function detectVideoCookiesNeed(res: ChatResponseBody): CookiesGuideSignal {
  const extra = res.extra;
  if (!extra || typeof extra !== "object") return "no_video_in_round";
  const e = extra as Record<string, unknown>;

  const url = typeof e["v11_main_video_url"] === "string" ? (e["v11_main_video_url"] as string) : null;
  if (!url) return "no_video_in_round";

  const ok = e["v11_middle_video_url_ok"];
  if (ok !== "false" && ok !== false) return null;

  const cookies =
    typeof e["v11_middle_video_url_cookies"] === "string"
      ? (e["v11_middle_video_url_cookies"] as string)
      : "none";

  const stage =
    typeof e["v11_middle_video_url_stage"] === "string" ? (e["v11_middle_video_url_stage"] as string) : null;
  const errCode =
    typeof e["v11_middle_video_url_error"] === "string" ? (e["v11_middle_video_url_error"] as string) : null;

  if (isCookiesUnrelatedFailure(errCode)) {
    return null;
  }

  const hint = classifyVideoFailure({ cookies, stage, errCode });
  return { url, hint };
}

function isCookiesUnrelatedFailure(errCode: string | null): boolean {
  if (!errCode) return false;
  if (errCode.startsWith("fetch_raised:DownloadError")) return true;
  if (errCode.includes("DownloadError")) return true;
  if (errCode.includes("UNEXPECTED_EOF_WHILE_READING")) return true;
  if (errCode.includes("SSL:")) return true;
  if (errCode.startsWith("url_contains_non_ascii")) return true;
  if (errCode.includes("reason=non_ascii_in_url")) return true;
  if (errCode.startsWith("web_video_asr_needs_confirmation")) return true;
  if (errCode.startsWith("duration_exceeds_limit")) return true;
  if (errCode.startsWith("asr_failed")) return true;
  if (errCode.startsWith("no_audio_file_after_download")) return true;
  if (errCode.startsWith("no_subtitle_and_asr_disabled_by_caller")) return true;
  if (errCode.startsWith("no_subtitle_and_asr_unavailable")) return true;
  if (errCode.includes("reason=video_unavailable")) return true;
  if (errCode.includes("reason=video_private")) return true;
  if (errCode.includes("reason=video_members_only")) return true;
  if (errCode.includes("reason=video_region_locked")) return true;
  if (errCode.includes("reason=video_premiere_pending")) return true;
  if (errCode.startsWith("yt_dlp_metadata_failed:OSError") ||
      errCode.startsWith("yt_dlp_metadata_failed:FileNotFoundError") ||
      errCode.startsWith("yt_dlp_metadata_failed:PermissionError") ||
      errCode.startsWith("yt_dlp_audio_failed:OSError")) {
    return true;
  }
  return false;
}

function classifyVideoFailure(params: {
  cookies: string;
  stage: string | null;
  errCode: string | null;
}): string {
  const { cookies, stage, errCode } = params;
  const ec = errCode ?? "?";
  const tag = `${stage ?? "?"}/${ec}`;
  const has = (kw: string) => ec.includes(kw);

  if (ec.startsWith("url_contains_non_ascii") || has("reason=non_ascii_in_url")) {
    return `URL 里混进了中文字符（${tag}）—— 最常见原因是 URL 后面没空格就接了"这个视频讲了什么"之类的提问。把 URL 和提问之间加一个空格，或者把 URL 单独发一行，再发提问。`;
  }
  if (ec.startsWith("duration_exceeds_limit")) {
    const m = ec.match(/(\d+)s>max:(\d+)s/);
    const dur = m ? parseInt(m[1], 10) : null;
    const max = m ? parseInt(m[2], 10) : null;
    if (dur !== null && max !== null) {
      const durMin = Math.round(dur / 60);
      const maxMin = Math.round(max / 60);
      return `这条视频时长约 ${durMin} 分钟，超过了后端给 ASR 兜底设的 ${maxMin} 分钟上限（视频太长云端 ASR 会很贵 / 受 SiliconFlow 单文件 25MB 限制）。可在 .env 把 VIDEO_MAX_AUDIO_SECONDS 调高（如 3600 = 60 分钟）后重启后端，或换一条带官方字幕的视频（字幕路径不受时长限制）。`;
    }
    return `视频时长超过后端 ASR 兜底上限（${tag}）。可调高 VIDEO_MAX_AUDIO_SECONDS 后重启后端，或换一条带官方字幕的视频。`;
  }
  if (ec.startsWith("asr_failed")) {
    return `云端 ASR 转写失败（${tag}）。请确认 ASR_ENABLED=1 且 SiliconFlow / OpenAI Key 已正确配置。`;
  }
  if (has("reason=video_unavailable") || has("reason=video_private") ||
      has("reason=video_members_only") || has("reason=video_region_locked") ||
      has("reason=video_premiere_pending")) {
    return `这条视频本身不可访问（${tag}）——可能是私享 / 会员专享 / 地区限制 / 还没首播。换条视频再试。`;
  }
  if (has("reason=http_401") || has("reason=login_required") ||
      has("reason=cookies_expired")) {
    return `登录态失效（${tag}）。重新导一份对应站点的 cookies。`;
  }
  if (has("reason=http_412_anti_bot") || has("reason=youtube_anti_bot") ||
      has("reason=http_403")) {
    return `站方反爬拦截（${tag}）。最常见是 cookies 过期 / 没带对站，重做一份对应站点的 cookies 即可。`;
  }
  if (has("reason=no_matching_format")) {
    return `站方返回的格式我这边没法用（${tag}）。多见于 YouTube SABR-only / 加密流，过几分钟再试或换条视频。`;
  }
  if (ec.startsWith("OSError")) {
    return `下载过程出系统错误（${tag}）。常见是网络抖动 / 临时目录权限或磁盘问题，跟 cookies 没关系，过几秒再发一次试试。`;
  }
  if (cookies === "file") {
    return `当前已用 cookies 文件，但视频抓取失败（${tag}）。如果反复失败、且不像是网络/视频本身的问题，可以重做一份对应站点的 cookies。`;
  }
  if (cookies.startsWith("browser:")) {
    return `当前从浏览器 (${cookies.slice(8)}) 读 cookies 失败（Win11 上的 DPAPI 限制常见）。改用上传文件方式更稳。`;
  }
  return `刚才匿名抓视频被拦了（${tag}）。给后端一份你浏览器的 cookies，下次就能正常解析。`;
}

/* ---------------------------------------------------------------------------
 * Hook: useVideoGuide
 * --------------------------------------------------------------------------- */
export interface CookiesGuideState {
  open: boolean;
  url: string | null;
  hint: string | null;
}

export function useVideoGuide() {
  const [cookiesGuide, setCookiesGuide] = useState<CookiesGuideState>({
    open: false,
    url: null,
    hint: null,
  });

  const openManual = useCallback(() => {
    setCookiesGuide({ open: true, url: null, hint: null });
  }, []);

  const close = useCallback(() => {
    setCookiesGuide({ open: false, url: null, hint: null });
  }, []);

  const applySignal = useCallback((sig: CookiesGuideSignal) => {
    if (sig === "no_video_in_round") return;
    if (sig === null) {
      setCookiesGuide({ open: false, url: null, hint: null });
    } else {
      setCookiesGuide({ open: true, url: sig.url, hint: sig.hint });
    }
  }, []);

  return { cookiesGuide, openManual, close, applySignal };
}
