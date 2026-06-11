import { describe, expect, it } from "vitest";

import {
  copyAllowedProxyRequestHeaders,
  isProxyAllowedRequestHeader,
} from "./proxyAllowedHeaders";

describe("proxyAllowedHeaders", () => {
  it("allows auth and business headers only", () => {
    expect(isProxyAllowedRequestHeader("Authorization")).toBe(true);
    expect(isProxyAllowedRequestHeader("Content-Type")).toBe(true);
    expect(isProxyAllowedRequestHeader("X-Admin-Key")).toBe(true);
    expect(isProxyAllowedRequestHeader("Cookie")).toBe(false);
    expect(isProxyAllowedRequestHeader("X-Forwarded-For")).toBe(false);
  });

  it("filters outbound proxy headers", () => {
    const source = new Headers({
      Authorization: "Bearer secret-token",
      "Content-Type": "application/json",
      Cookie: "session=abc",
      "X-Custom-Client": "should-drop",
      "X-Session-ID": "sess-1",
    });
    const out = copyAllowedProxyRequestHeaders(source);
    expect(out.get("Authorization")).toBe("Bearer secret-token");
    expect(out.get("Content-Type")).toBe("application/json");
    expect(out.get("X-Session-ID")).toBe("sess-1");
    expect(out.get("Cookie")).toBeNull();
    expect(out.get("X-Custom-Client")).toBeNull();
  });
});
