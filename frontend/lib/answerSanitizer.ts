/**
 * 助手正文最后一道清洗：拦截明显内部标签（兜底，根因应在后端）。
 */

const BANNED_SUBSTRINGS = [
  "[doc_path]",
  "[doc_file]",
  "[doc_title]",
  "[demo_keywords]",
  "（写作提示）",
  "answer_style_hint",
  "retrieval_debug",
  "gap_notes",
  "why_still_insufficient",
  "collection_trace",
  "zero_rag_hit",
  "local_file_failed",
] as const;

export function sanitizeAssistantAnswer(text: string): string {
  let s = text;
  for (const b of BANNED_SUBSTRINGS) {
    s = s.split(b).join("");
  }
  s = s.replace(/\[doc_[a-z]+\][^\n]*/gi, "");
  s = s.replace(/\n{3,}/g, "\n\n");
  return s.trim();
}
