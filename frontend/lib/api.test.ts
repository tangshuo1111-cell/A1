import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./client", () => ({
  jsonFetch: vi.fn(),
  multipartFetch: vi.fn(),
}));

import * as client from "./client";
import { DEFAULT_CHAT_PATH, fetchHealth, postChat } from "./api";

describe("api", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("DEFAULT_CHAT_PATH points at sole public chat route", () => {
    expect(DEFAULT_CHAT_PATH).toBe("/chat/agno");
  });

  it("fetchHealth reads /health via jsonFetch", async () => {
    vi.mocked(client.jsonFetch).mockResolvedValueOnce({ ok: true } as never);
    await fetchHealth();
    expect(client.jsonFetch).toHaveBeenCalledWith("/health", { method: "GET" });
  });

  it("postChat POSTs optional flags when booleans provided", async () => {
    vi.mocked(client.jsonFetch).mockResolvedValueOnce({} as never);
    await postChat({
      message: "m",
      session_id: "s",
      use_knowledge: true,
      confirm_long_web_video_asr: false,
    });
    expect(client.jsonFetch).toHaveBeenCalledTimes(1);
    expect(client.jsonFetch).toHaveBeenCalledWith(
      DEFAULT_CHAT_PATH,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          message: "m",
          session_id: "s",
          use_knowledge: true,
          confirm_long_web_video_asr: false,
        }),
      }),
    );
  });

  it("postChat omits unspecified optional booleans from JSON body", async () => {
    vi.mocked(client.jsonFetch).mockResolvedValueOnce({} as never);
    await postChat({ message: "x", session_id: null });
    const init = vi.mocked(client.jsonFetch).mock.calls[0][1] as { body?: string };
    const bodyObj = JSON.parse(init.body ?? "{}") as Record<string, unknown>;
    expect(bodyObj).toEqual({ message: "x", session_id: null });
    expect("use_knowledge" in bodyObj).toBe(false);
    expect("confirm_long_web_video_asr" in bodyObj).toBe(false);
  });
});
