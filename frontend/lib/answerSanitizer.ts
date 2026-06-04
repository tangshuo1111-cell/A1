/**
 * 助手正文最后一道清洗：拦截明显内部标签 + 清理 markdown 乱格式（保留 emoji）。
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
  s = s.replace(/^\s*-{3,}\s*$/gm, "");
  s = s.replace(/^\s{0,3}#{1,6}\s+/gm, "");
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "$1");
  s = s.replace(/\n{3,}/g, "\n\n");
  return s.trim();
}
