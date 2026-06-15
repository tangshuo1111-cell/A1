# V3 Observable Fields Report

目的：在编写 `V3：Complex / Agent Collaboration` case 之前，先盘点 `/chat/agno` 真实可观测字段，避免按理想 Agent 结构拍脑袋写断言。

说明：

- “稳定性”表示该字段在当前代码中的对外暴露稳定程度，不代表业务一定正确。
- “是否可断言”分为：`硬断言`、`可断言/可警告`、`尽量提取`。
- “对应 Agent 阶段”是评测视角映射，不等于字段只属于该 Agent。

| 字段名 | 所在位置 | 稳定性 | 是否可断言 | 对应 Agent 阶段 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `task_status` | top / `extra.task_status` | 高 | 硬断言 | 全链路出口 | `ChatTurnResult` 顶层固定字段，且必须是 canonical 值。 |
| `primary_path` | top / `extra.primary_path` | 高 | 硬断言 | Main / Exit | 统一出口固定写入，适合做复杂路径、能力路径和假成功校验。 |
| `mode` | `extra.mode` | 高 | 硬断言 | Main / Exit | 统一出口写入，可用于 fast / complex / async 判定。 |
| `router_lane` | `extra.router_lane` | 高 | 硬断言 | Main / Exit | 统一出口写入，适合作为 lane 侧证据。 |
| `pending_kind` | `extra.pending_kind` | 高 | 硬断言 | Exit / Async | 统一出口写入，复杂阻断或后台转交时可断言。 |
| `material_sufficiency` | `extra.material_sufficiency` | 中高 | 硬断言 / 警告 | Middle / Quality Gate | 当前由 `TurnExitEnvelope` 写出，能直接支撑“证据不足是否诚实”。 |
| `quality_gate` | `extra.quality_gate` | 中高 | 硬断言 / 警告 | Quality Gate | 当前以字典形式整体写出，是 V3 重要评测依据。 |
| `quality_gate.pass` | `extra.quality_gate.pass` | 高 | 硬断言 / 警告 | Quality Gate | 当前显式平铺。 |
| `quality_gate.reason_codes` | `extra.quality_gate.reason_codes` | 中高 | 可断言 / 可警告 | Quality Gate | 当前显式平铺，适合判断材料不足、质量门阻断。 |
| `quality_gate.need_second_round` | `extra.quality_gate.need_second_round` | 中 | 可警告 | Quality Gate / Second Round | 当前平铺，但不应作为所有 case 的硬失败条件。 |
| `quality_gate.need_more_material` | `extra.quality_gate.need_more_material` | 中 | 可警告 | Quality Gate / Second Round | 当前平铺，适合辅助判定材料缺口。 |
| `insufficient_evidence` | `extra.insufficient_evidence` | 高 | 硬断言 / 警告 | Quality Gate / Answer | 当前统一出口计算，适合“证据不足但不诚实”校验。 |
| `failure_reason_code` | `extra.failure_reason_code` | 中高 | 可断言 / 可警告 | Exit | 适合失败或降级原因归类。 |
| `is_complex_task` | `extra.is_complex_task` | 中高 | 可断言 / 可警告 | Main / Exit | 由统一出口聚合得出，适合复杂题侧证据。 |
| `executor_profile` | `extra.executor_profile` | 中 | 可断言 / 可警告 | Main / Executor | 复杂链、快速链或异步链的辅助证据。 |
| `answer` | top | 高 | 硬断言 / 警告 | Answer | 最终回答正文，用于 groundedness、限制表达、假成功检测。 |
| `v6_main_pan_renwu` | `extra.v6_main_pan_renwu` | 中 | 可警告 | Main | 来自 answer agent 透传的协作诊断字段。 |
| `v6_main_pan_allow_kb` | `extra.v6_main_pan_allow_kb` | 中 | 尽量提取 | Main | 可用于判断是否显式允许 KB。 |
| `v6_main_pan_allow_web` | `extra.v6_main_pan_allow_web` | 中 | 尽量提取 | Main | 可用于判断是否显式允许 Web。 |
| `v6_main_pan_celue` | `extra.v6_main_pan_celue` | 中 | 尽量提取 | Main | 主协作策略标签，适合记录，不宜普遍硬断言。 |
| `v6_middle_pan_gou` | `extra.v6_middle_pan_gou` | 中 | 可警告 | Middle | Middle 的材料是否够用信号。 |
| `v6_middle_pan_bukong` | `extra.v6_middle_pan_bukong` | 中 | 尽量提取 | Middle | Middle 补空信号。 |
| `v6_middle_pan_laiyuan` | `extra.v6_middle_pan_laiyuan` | 中 | 可断言 / 可警告 | Middle | Middle 侧来源主信号，适合多来源 case 观测。 |
| `v6_middle_pan_que` | `extra.v6_middle_pan_que` | 中 | 可警告 | Middle | 缺什么材料的诊断字段。 |
| `v6_middle_pan_xia` | `extra.v6_middle_pan_xia` | 中 | 可警告 | Middle / Second Round | 下一步建议，适合辅助判断 second-round 缺口。 |
| `v6_answer_pan_dafengshi` | `extra.v6_answer_pan_dafengshi` | 中 | 尽量提取 | Answer | Answer 风格信号，可作为保守回答侧证据。 |
| `v6_answer_pan_jiegou` | `extra.v6_answer_pan_jiegou` | 中 | 尽量提取 | Answer | 回答结构信号，适合记录 answer 是否结构化。 |
| `v6_answer_pan_baoshou` | `extra.v6_answer_pan_baoshou` | 中 | 可警告 | Answer | 保守程度信号，适合与证据不足诚实性联合判断。 |
| `v6_answer_pan_lane` | `extra.v6_answer_pan_lane` | 中 | 尽量提取 | Answer | Answer 侧 lane 诊断。 |
| `v6_answer_pan_primary_path` | `extra.v6_answer_pan_primary_path` | 中 | 尽量提取 | Answer | Answer 侧 path 诊断。 |
| `retrieved_chunks` | `extra.retrieved_chunks` / 相关快照 | 低到中 | 尽量提取 | Middle / KB | 当前未见统一平铺保证，V3 只能兼容提取。 |
| `kb_hits` / `kb_hit_count` | `extra` / 相关快照 | 低到中 | 可警告 | Middle / KB | 当前字段命名可能不完全统一，适合作为辅证。 |
| `kb_evidence_tier` | `extra.kb_evidence_tier` 或 `v6_middle` 侧证据 | 中 | 可断言 / 可警告 | Middle / KB | 当前 Middle hint 中存在 tier 信号，适合复杂 KB case。 |
| `web_block` / `web_has_content` / `web_evidence_chars` | `extra` | 中 | 可断言 / 可警告 | Middle / Web | 可用于“网页是否真有材料”判断。 |
| `temporary_materials` | `extra` / bundle 相关 | 低到中 | 尽量提取 | Middle / Document | 当前更适合作为辅证。 |
| `failures` | `extra` / bundle 相关 | 低到中 | 尽量提取 | Middle | 可辅助判断材料抓取失败或降级。 |
| `source_briefs` | `extra` / bundle 相关 | 低 | 尽量提取 | Middle / Answer | 多来源复杂题可能出现，但当前不宜做硬前提。 |
| `comparison_matrix` | `extra` / bundle 相关 | 低 | 尽量提取 | Middle / Answer | 多来源比较 case 的高级信号，优先记录 warning。 |
| `feedback_gate_result` | `extra` / bundle 相关 | 低 | 尽量提取 | Second Round | 只作为 second-round 可观测性的辅证。 |
| `used_rounds` | `extra` / bundle 相关 | 低 | 尽量提取 | Second Round | 当前不稳定，不做硬断言。 |
| `router_source` | `extra` / 兼容字段 | 低到中 | 尽量提取 | Main | 代码内部稳定，但对 `/chat/agno` 顶层响应不保证统一平铺。 |
| `routing_explain` | `extra` / 兼容字段 | 低到中 | 尽量提取 | Main | 作为 Main 决策旁证很有价值，但必须允许缺失。 |
| `need_second_round` | `extra.quality_gate.need_second_round` | 中 | 可警告 | Quality Gate / Second Round | 以 quality gate 派生字段为准。 |
| `supplementary_retrieve` | `extra` / 兼容字段 | 低 | 尽量提取 | Middle / Second Round | 当前只适合作为辅证。 |

当前 V3 评测原则：

- 硬断言优先使用：`task_status`、`primary_path`、`mode`、`router_lane`、`pending_kind`、`material_sufficiency`、`quality_gate.*`、`insufficient_evidence`、回答正文的诚实性。
- `v6_*`、`retrieved_chunks`、`routing_explain`、`source_briefs`、`comparison_matrix`、`feedback_gate_result` 等字段属于“尽量提取字段”，缺失时应进入 warning / missing field，而不是直接把 case 判死。
- 如果回答**明确声称**基于某类材料，但响应中完全没有对应材料信号，则仍应判为真风险，不能因为字段不稳定而放过明显假成功。
