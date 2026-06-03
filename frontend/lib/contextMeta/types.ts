export interface ContextLines {
  retrievalLabel: string | null;
  toolsSummary: string | null;
  fallbackNote: string | null;
  /** V15 R1：plan 摘要（needs_retrieval / answer_mode / tools_allowed） */
  v15Plan: string | null;
  /** V15 R1：bundle 摘要（material_sufficiency / failures / retrieved_chunks） */
  v15Bundle: string | null;
  /** V14：后端 trace 行原文（strategy / hits / filters） */
  v14RetrievalLine: string | null;
  /** V15：与 execution_status 对齐，供 UI 对齐「最终链路状态」 */
  v15FinalStatus: string | null;
}

/** 一行：仅展示后端已有字段，缺省则不出行 */
export interface V15DebugRow {
  label: string;
  value: string;
}
