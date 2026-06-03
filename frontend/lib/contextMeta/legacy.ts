/** Legacy / 兼容字段：仅调试折叠区展示，不作为默认主链状态 */
export const LEGACY_EXTRA_KEY_PREFIXES = [
  "v11_",
  "v10_main_explicit_kind",
  "v11_middle_",
];

export function isLegacyExtraKey(k: string): boolean {
  if (LEGACY_EXTRA_KEY_PREFIXES.some((p) => k.startsWith(p))) return true;
  if (k === "v11_main_video_url") return true;
  if (
    k.startsWith("v7_middle_pan_video_ingest") ||
    k === "v7_middle_pan_video_ingested"
  ) {
    return true;
  }
  return false;
}
