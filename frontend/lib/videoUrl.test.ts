import { describe, expect, it } from "vitest";

import { extractFirstWhitelistVideoUrl } from "./videoUrl";

describe("extractFirstWhitelistVideoUrl", () => {
  it("returns first http(s) URL on whitelist by hostname", () => {
    const msg = "先看 https://www.bilibili.com/video/BVxxx 再想 https://evil.com/z";
    expect(extractFirstWhitelistVideoUrl(msg)).toBe("https://www.bilibili.com/video/BVxxx");
  });

  it("matches subdomains of whitelist roots", () => {
    expect(
      extractFirstWhitelistVideoUrl("https://m.youtube.com/watch?v=1"),
    ).toBe("https://m.youtube.com/watch?v=1");
  });

  it("returns null when no whitelist URL appears", () => {
    expect(extractFirstWhitelistVideoUrl("仅文本无链接")).toBeNull();
    expect(extractFirstWhitelistVideoUrl("")).toBeNull();
  });
});
