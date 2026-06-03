export interface SitePreset {
  domain: string;
  brandZh: string;
  extension: { name: string; url: string };
  altExtensions?: { name: string; url: string }[];
  loginUrl: string;
  expiryNote: string;
}

export const SITE_PRESETS: SitePreset[] = [
  {
    domain: "bilibili.com",
    brandZh: "B 站",
    extension: {
      name: "Get cookies.txt LOCALLY (Chrome)",
      url: "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc",
    },
    altExtensions: [
      {
        name: "cookies.txt (Edge 加载项)",
        url: "https://microsoftedge.microsoft.com/addons/detail/get-cookiestxt-locally/jfgnfcdpicleoopnogmdbhkholdmdlol",
      },
      {
        name: "cookies.txt (Firefox)",
        url: "https://addons.mozilla.org/firefox/addon/cookies-txt/",
      },
    ],
    loginUrl: "https://www.bilibili.com",
    expiryNote: "B 站 cookies 一般 30 天左右过期；下次再失败时重做即可。",
  },
  {
    domain: "youtube.com",
    brandZh: "YouTube",
    extension: {
      name: "Get cookies.txt LOCALLY (Chrome)",
      url: "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc",
    },
    altExtensions: [
      {
        name: "cookies.txt (Edge 加载项)",
        url: "https://microsoftedge.microsoft.com/addons/detail/get-cookiestxt-locally/jfgnfcdpicleoopnogmdbhkholdmdlol",
      },
    ],
    loginUrl: "https://www.youtube.com",
    expiryNote:
      "YouTube cookies 短的几小时、长的几天就可能失效；建议每次失败重做（也是 1 分钟搞定）。",
  },
  {
    domain: "douyin.com",
    brandZh: "抖音",
    extension: {
      name: "Get cookies.txt LOCALLY (Chrome)",
      url: "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc",
    },
    loginUrl: "https://www.douyin.com",
    expiryNote: "抖音 cookies 通常 7~30 天有效。",
  },
  {
    domain: "tiktok.com",
    brandZh: "TikTok",
    extension: {
      name: "Get cookies.txt LOCALLY (Chrome)",
      url: "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc",
    },
    loginUrl: "https://www.tiktok.com",
    expiryNote: "TikTok cookies 一般几天到一周。",
  },
];

export function resolveSitePreset(
  url: string | null | undefined,
): SitePreset | null {
  if (!url) return null;
  let host = "";
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
  for (const p of SITE_PRESETS) {
    if (host === p.domain || host.endsWith("." + p.domain)) {
      return p;
    }
  }
  return null;
}

interface StepGuideProps {
  preset: SitePreset | null;
  matched: string[];
}

export function StepGuide({ preset, matched }: StepGuideProps) {
  return (
    <>
      {/* 站点提示 */}
      {preset ? (
        <section className="mb-5 rounded-xl border border-amber-300/70 bg-amber-50/70 px-4 py-3">
          <p className="text-[12px] leading-snug text-amber-900">
            <span className="font-semibold">
              检测到你贴的是 {preset.brandZh} 链接。
            </span>
            {matched.includes(preset.domain) ? (
              <>
                {" "}
                我们已经有 {preset.brandZh} 的 cookies
                了。失败原因有几种可能：
                <span className="font-medium">cookies 过期</span>（重做即可）、
                <span className="font-medium">站方反爬升级</span>
                （重做有概率救）、
                <span className="font-medium">网络/视频本身问题</span>
                （重做没用）。
                可以按下方步骤**重做一份**先排查 cookies 这条线。
              </>
            ) : (
              <>
                {" "}
                现有 cookies <span className="font-medium">不包含</span>{" "}
                {preset.brandZh}，请按下方三步为 {preset.brandZh}{" "}
                单独导一份。
              </>
            )}
          </p>
          <p className="mt-1 text-[11px] text-amber-800">
            {preset.expiryNote}
          </p>
        </section>
      ) : null}

      {/* 三步指南 */}
      <section className="mb-5">
        <h3 className="mb-2 text-[13px] font-semibold text-ink-primary">
          详细操作（一次约 1 分钟）
        </h3>
        <ol className="space-y-3 text-[12px] leading-relaxed text-ink-secondary">
          <li>
            <p>
              <span className="mr-1 inline-flex size-5 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-ink-primary">
                1
              </span>
              <span className="font-medium text-ink-primary">
                在浏览器装一个 cookies 导出扩展
              </span>
            </p>
            <ul className="ml-6 mt-1 list-disc space-y-0.5 text-[11.5px] text-ink-tertiary">
              <li>
                Chrome：{" "}
                <a
                  href={
                    preset?.extension.url ??
                    "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"
                  }
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent underline-offset-2 hover:underline"
                >
                  Get cookies.txt LOCALLY
                </a>
                （应用商店搜这个名字也行）
              </li>
              <li>
                Edge：{" "}
                <a
                  href="https://microsoftedge.microsoft.com/addons/detail/get-cookiestxt-locally/jfgnfcdpicleoopnogmdbhkholdmdlol"
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent underline-offset-2 hover:underline"
                >
                  Edge 加载项同名扩展
                </a>
              </li>
              <li>
                Firefox：{" "}
                <a
                  href="https://addons.mozilla.org/firefox/addon/cookies-txt/"
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent underline-offset-2 hover:underline"
                >
                  cookies.txt
                </a>
              </li>
            </ul>
          </li>

          <li>
            <p>
              <span className="mr-1 inline-flex size-5 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-ink-primary">
                2
              </span>
              <span className="font-medium text-ink-primary">
                登录视频站、点扩展导出
              </span>
            </p>
            <ul className="ml-6 mt-1 list-disc space-y-0.5 text-[11.5px] text-ink-tertiary">
              <li>
                打开{" "}
                <a
                  href={preset?.loginUrl ?? "https://www.bilibili.com"}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent underline-offset-2 hover:underline"
                >
                  {preset?.brandZh ?? "对应视频站"}
                </a>
                ，<span className="font-medium">先登录账号</span>。
              </li>
              <li>
                点扩展图标 → 选择「
                <span className="font-medium">
                  Export cookies for this site
                </span>
                」 （只导当前站，更安全）→ 浏览器弹出「另存为」，保存成{" "}
                <code className="rounded bg-surface-input px-1">
                  cookies.txt
                </code>
                。
              </li>
              <li>
                如果你需要同时支持多个站，每个站重复一次本步骤；也可以一次性导出
                All cookies 再上传（系统只取白名单内的）。
              </li>
            </ul>
          </li>

          <li>
            <p>
              <span className="mr-1 inline-flex size-5 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-ink-primary">
                3
              </span>
              <span className="font-medium text-ink-primary">
                把 cookies.txt 拖到下面方框，或点选择文件
              </span>
            </p>
            <p className="ml-6 mt-1 text-[11.5px] text-ink-tertiary">
              上传成功 →
              自动生效，下一次贴链接就能正常解析。**不会**写到 .env /
              不会上传到任何外部服务，只存在你这台电脑的 _local/data/cookies/ 目录。
            </p>
            <p className="ml-6 mt-1 text-[11.5px] text-emerald-600 dark:text-emerald-400">
              多站累加：再上传 YouTube 不会清掉之前传过的 B
              站；同站再传则刷新登录态。
              {matched.length > 0
                ? `（已配置：${matched.join("、")}）`
                : ""}
            </p>
            <p className="ml-6 mt-1 text-[11.5px] text-ink-tertiary">
              常见 cookie 寿命参考：B 站 1~3 月、YouTube 1~6
              月、抖音 1~2
              周；过期后系统会再次弹出本卡片，按提示重传那个站即可。
            </p>
          </li>
        </ol>
      </section>
    </>
  );
}
