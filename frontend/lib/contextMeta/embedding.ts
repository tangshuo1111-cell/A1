/** /health checks.embedding.mode → 用户可读文案 */

export function humanizeEmbeddingMode(raw: string | null | undefined): string | null {
  if (!raw) return null;
  switch (raw) {
    case "index_present":
      return "语义索引已就绪";
    case "enabled_no_rows":
      return "语义索引为空，当前可能使用关键词检索";
    case "disabled":
      return "关键词检索（语义检索已关闭）";
    case "check_failed":
      return "索引状态检查失败";
    default:
      if (raw.startsWith("check_failed:")) {
        return "索引状态检查失败";
      }
      return null;
  }
}
