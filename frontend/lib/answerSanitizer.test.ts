import { describe, expect, it } from "vitest";

import { sanitizeAssistantAnswer } from "./answerSanitizer";

describe("sanitizeAssistantAnswer", () => {
  it("strips banned substrings and collapses excessive newlines", () => {
    const raw = "a [doc_path] b（写作提示）x\n\n\n\n\nc";
    expect(sanitizeAssistantAnswer(raw)).toBe("a  bx\n\nc");
  });
});
