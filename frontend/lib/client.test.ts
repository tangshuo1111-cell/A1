import { afterEach, describe, expect, it, vi } from "vitest";

describe("client bearer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("bearerAuthHeader is empty without env", async () => {
    delete process.env.NEXT_PUBLIC_API_BEARER_TOKEN;
    const { bearerAuthHeader } = await import("./client");
    expect(bearerAuthHeader()).toEqual({});
  });

  it("bearerAuthHeader adds Authorization when NEXT_PUBLIC_API_BEARER_TOKEN set", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BEARER_TOKEN", "fixture-token");
    vi.resetModules();
    const { bearerAuthHeader } = await import("./client");
    expect(bearerAuthHeader()).toEqual({
      Authorization: "Bearer fixture-token",
    });
  });

  it("jsonFetch does not send Authorization when token empty", async () => {
    delete process.env.NEXT_PUBLIC_API_BEARER_TOKEN;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    const { jsonFetch } = await import("./client");
    await jsonFetch("/health", { method: "GET" });
    const hdrs = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
    expect(hdrs.Authorization).toBeUndefined();
  });

  it("jsonFetch sends Authorization Bearer when token set", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BEARER_TOKEN", "srv-secret");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    const { jsonFetch } = await import("./client");
    await jsonFetch("/health", { method: "GET" });
    const hdrs = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
    expect(hdrs.Authorization).toBe("Bearer srv-secret");
  });
});
