/**
 * 与后端 ``video.url_fetch.extract_video_url`` / 白名单域名对齐的轻量解析（仅前端探针用）。
 */

const VIDEO_HOSTS = new Set([
  "bilibili.com",
  "b23.tv",
  "youtube.com",
  "youtu.be",
  "youtube-nocookie.com",
  "tiktok.com",
  "douyin.com",
  "vm.tiktok.com",
  "twitter.com",
  "x.com",
  "vimeo.com",
]);

/** RFC3986 URL-safe 子集，与后端 ``_URL_REGEX`` 一致 */
const URL_IN_TEXT =
  /https?:\/\/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]+/g;

function hostOnWhitelist(hostname: string): boolean {
  const h = hostname.trim().toLowerCase();
  if (!h) return false;
  for (const w of VIDEO_HOSTS) {
    if (h === w || h.endsWith("." + w)) return true;
  }
  return false;
}

/** 从用户输入中取出第一个白名单视频 URL；无则 null */
export function extractFirstWhitelistVideoUrl(message: string): string | null {
  const text = (message || "").trim();
  if (!text) return null;
  const matches = text.matchAll(URL_IN_TEXT);
  for (const m of matches) {
    const raw = m[0];
    try {
      const host = new URL(raw).hostname;
      if (hostOnWhitelist(host)) return raw;
    } catch {
      /* ignore */
    }
  }
  return null;
}
