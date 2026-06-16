# Known Issues

目的：集中记录评测中已经确认、且当前版本**不在本轮修复**的真实产品缺陷，避免同一问题散落在多份版本文档和运行报告里。

使用规则：

- 这里只记录“已经被代码现实或真实评测确认”的问题。
- 不记录猜测性问题。
- 不记录普通 warning。
- 不记录单纯 case 口径问题。
- 不在这里展开长篇修复设计；修复方案放到后续专门治理轮次。

## 状态定义

- `Open`：已确认，尚未修复。
- `Deferred`：已确认，当前版本暂不修。
- `Fixed`：已修复。
- `Won't Fix`：确认不修。
- `Recheck Needed`：需要复测确认。

## Issue 模板

每条 known issue 至少包含：

- Issue ID
- 标题
- 来源版本
- 来源 case
- 问题类型
- 当前状态
- 原始证据
- 现象
- 为什么是真问题
- 影响范围
- 当前处理策略
- 后续建议
- 回归方式

---

## 复测摘要（2026-06-16）

真实环境复跑（`LIGHT_MAQA_FAKE_LLM=0`）：

| 套件 | 结果 | 说明 |
| ---- | ---- | ---- |
| `regression_all` | **42/42 passed** | V1 10/10、V2 16/16、V2.5 8/8、V3 8/8 |
| `real_external_smoke` | **7/7 capability passed** | 与 regression 独立 |

总览证据：`runtime_data/eval_sandbox/reports/eval_v4_regression_overview_20260616_112055.json`（不入库）

下文 KI-V2-001 / KI-V2.5-001 / KI-V2.5-002 / KI-V3-001 / KI-V3-002 / KI-V3-003 均为 **`Fixed`**；本轮复测未再命中对应 case 失败。

---

## KI-V2-001

- Issue ID：`KI-V2-001`
- 标题：`video_total_failure 非法视频 URL 被 document_fast succeeded 接管`
- 来源版本：`V2：Capability Chains + Fake Success Negatives`
- 来源 case：`video_total_failure`
- 问题类型：`video intent honesty / invalid video URL fallback error`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_capability_all_20260613_154809.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_capability_all_20260613_154809.md`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_capability_video_20260615_150530.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_capability_video_20260615_150530.md`
- 现象：
- 用户输入视频任务，但 URL 是 `https://example.com/not-a-real-video`
- 系统实际返回 `task_status=succeeded`
- 系统实际返回 `lane=document`
- 系统实际返回 `primary_path=document_fast`
- `capabilities_called` 为 `capability.document.parse_quick / capability.document.summarize`
- warning 显示 `video success without transcript evidence`
- 为什么是真问题：
- 非法/非视频 URL 没有诚实落到 `video failed / blocked / pending`
- 而是被 `document_fast succeeded` 接管
- 这会让视频链失败看起来像同步成功
- 影响范围：
- 非法视频 URL 输入
- video intent 识别后的失败诚实性
- V2 video total failure 回归口径
- 当前处理策略：
- 已于 2026-06-15 通过 ingress 视频意图信号 + video_fast 显式 unsupported 失败修复
- explicit video intent + unsupported URL 留在 video lane；`task_status=failed`；不再 web_async / document_fast
- 后续建议：
- video 意图命中后，应优先维持 video lane 的失败或阻断语义
- 禁止无 transcript / 无 video evidence 时被 document fast 成功接管
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v2_capability_all`
- 复测（2026-06-16）：`regression_all` 42/42；`video_total_failure` case 通过

---

## KI-V2.5-001

- Issue ID：`KI-V2.5-001`
- 标题：`background_task_followup_flow fake state success`
- 来源版本：`V2.5：Multi-turn State Closure`
- 来源 case：`background_task_followup_flow`
- 问题类型：`fake state success / 多轮状态闭环缺陷`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260612_175353.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260612_175353.md`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260615_123421.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260615_123421.md`
- 现象：
- turn_1 用户要求后台处理长视频，系统返回 `blocked + approval_gate + await_user_confirm`
- 这时没有可观测的 `task_id / background_task_id / pending_kind`
- turn_2 用户追问“现在处理完成了吗？”
- 系统返回 `succeeded + direct_llm`，表现得像后台任务已经完成
- 为什么是真问题：
- 这不是 `allowed_primary_paths` 太窄
- 也不是字段缺失导致误判
- 系统在没有后台任务追踪证据时给出了类似完成态的回答，属于真实状态假成功
- 影响范围：
- 视频后台任务 follow-up
- 多轮状态闭环诚实性
- 前端任务状态展示与用户认知
- 当前处理策略：
- 已于 2026-06-15 完成最小 L5 修复并冻结
- session approval hold 写入 + turn_2 状态追问抬升为既有 `approval_blocked` 出口
- approval blocked 原生文案去除无 task signal 时的误导性「后台」表述
- 后续建议：
- （已落实）follow-up 在无 `task_id / background_task_id / pending_kind` 时不得伪装已完成
- PG 模式下 `approval_hold` 跨重启持久化如需生产级保障，另立 migration 轮次
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v2_5_multiturn_state`
- 复测（2026-06-16）：`regression_all` 42/42；`background_task_followup_flow` 通过

- Issue ID：`KI-V2.5-002`
- 标题：`continue_without_context_flow 空上下文继续请求被 succeeded + direct_llm 处理`
- 来源版本：`V2.5：Multi-turn State Closure`
- 来源 case：`continue_without_context_flow`
- 问题类型：`follow-up context honesty / empty-session closure error`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260613_154930.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260613_154930.md`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260615_143810.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260615_143810.md`
- 现象：
- 空会话 turn_1 输入“继续刚才那个内容。”
- 系统返回 `task_status=succeeded`
- 系统返回 `primary_path=direct_llm`
- 回答文本要求用户澄清
- 但 closure rule 判定 `answer_mentions_previous=true`、`has_previous_steps=false`
- 因此被识别为空上下文假闭环
- 为什么是真问题：
- 这不是已有上下文上的正常 follow-up
- 也不是单纯 allowed 值过严
- 系统在没有上一轮可承接上下文时，仍然走了 `succeeded + direct_llm`
- 影响范围：
- 空会话 follow-up
- continue / 刚才 / 上一轮 指代类请求
- V2.5 session closure 诚实性
- 当前处理策略：
- 已于 2026-06-15 通过 `lift_empty_context_followup` 事实抬升修复
- 空上下文 follow-up 不再 `default_success`；`task_status=blocked`；answer 使用确定性澄清文案，不依赖 LLM 措辞
- 后续建议：
- 无 previous steps / 无 stitch context 时，应更保守地落到 blocked、clarify 或显式无上下文状态
- 禁止把空上下文继续请求记为成功闭环
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v2_5_multiturn_state`
- 复测（2026-06-16）：`regression_all` 42/42；`continue_without_context_flow` 通过

---

## KI-V3-001

- Issue ID：`KI-V3-001`
- 标题：`complex_document_reasoning 内联文档复杂分析协作证据不足`
- 来源版本：`V3：Complex / Agent Collaboration`
- 来源 case：`complex_document_reasoning`
- 问题类型：`complex material reasoning observability gap / 内联文档未进入材料链`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.md`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_135404.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_135404.md`
- 现象（修复前）：
- 用户提供内联文档材料并要求复杂分析
- case 已进入 `mode=complex`，但内联文档只停留在 `message`，未进入 `v13_text_content` / `temporary_materials`
- Middle / Answer 消费 KB benchmark 材料
- 真实响应返回 `primary_path=agno_basic_v2_kb`，`temporary_materials=0`
- 不能证明系统基于当前内联材料完成了复杂协作分析
- 修复摘要（2026-06-15）：
- `session_stage` 将 message 内联文档提升为 `v13_text_content`
- complex 编排 handoff：`answer_mode=temporary_material`，`needs_retrieval=False`（不走 `prepare_text` pending）
- `bundle_finalize` 注入 `[inline_document]` 至 `temporary_materials`
- `path_labels` 在真实 inline document 消费后标 `document_complex`
- 修复后 E2E：`v3_complex_agent` **7/8**；`complex_document_reasoning` **通过**
- 关键行为：`task_status=succeeded`、`primary_path=document_complex`、`mode=complex`、`temporary_materials=1`、Answer 消费 `inline_document`
- 为什么是真问题：
- 该 case 要测的是「基于当前用户提供材料的复杂分析」
- 路径标签必须跟随真实材料消费，不能只改 label 骗过评测
- 影响范围：
- 内联文档复杂分析题
- complex/document 材料 handoff 与路径标签诚实性
- V3 Main / Middle / Answer 材料归属可观测性
- 当前处理策略：
- 已于 2026-06-15 完成最小 L5 材料 handoff + L10 路径标签修复并冻结
- 未修改 eval runner / assertions / rule_catalog，未放宽 `allowed_primary_paths`
- 风险 / 观察项：
- 内联提取当前依赖强 cue（如「下面这段文档内容」）和末位冒号切分，其他写法可能未覆盖
- `complex_web_kb_compare` 在本轮 E2E 从 timeout 转为通过（7/8 之一），**不是本轮修复目标**，不标记为 Fixed，仅作观察项
- V3 当前已完成冻结：`KI-V3-001` 与 `KI-V3-002` 均已 Fixed，`v3_complex_agent` 已复核 8/8；`complex_web_kb_compare` 仍作为稳定性观察项，不单独标记为固定修复成果
- 后续建议：
- 扩展内联文档 cue / 切分策略时保持「先修材料事实、再修路径标签」原则
- 如需覆盖更多 inline 写法，另立专项轮次，勿回退 eval 标准
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v3_complex_agent`
- 复测（2026-06-16）：`regression_all` 42/42；`complex_document_reasoning` 通过

---

## KI-V3-002

- Issue ID：`KI-V3-002`
- 标题：`complex_interview_explanation 退化为 kb_fast`
- 来源版本：`V3：Complex / Agent Collaboration`
- 来源 case：`complex_interview_explanation`
- 问题类型：`complex agent collaboration degradation / kb_fast 接管`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.md`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_140542.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_140542.md`
- 现象（修复前）：
- 项目面试讲解型复杂问题返回：
- `task_status=succeeded`
- `primary_path=kb_fast`
- `mode=fast`（未进入 complex 三 Agent 协作链）
- 没有稳定体现预期的 complex agent collaboration 路径
- 修复摘要（2026-06-15）：
- 在 `complexity_policy.py`（单一 complex_candidate 事实源）补充「结构化讲解 / 面试叙事 / 对比解释」强信号（`structured_explanation`、`decision_tradeoff`）
- `mode_selector` 在强 reason code 下升格 `mode=complex`，不再被 `kb_fast` 早退吞掉
- 修复后 E2E：`v3_complex_agent` **8/8**；`complex_interview_explanation` **通过**
- 关键行为：`mode=complex`、`executor_profile=complex`、`primary_path=agno_basic_v2_kb`（非 `kb_fast`）；`collaboration_trace` 含 Main / Middle / Answer 协作证据
- 为什么是真问题：
- 面试讲解型问题不只是知识库问答
- 它还需要复杂意图识别、材料组织、表达取舍和 grounding
- 当前 V3 无法充分证明 Main / Middle / Answer 协作链路稳定成立
- 影响范围：
- 项目面试讲解类复杂题
- complex / kb_fast 边界
- V3 协作证据可信度
- 当前处理策略：
- 已于 2026-06-15 完成最小 complexity_policy 修复并冻结
- 未修改 eval 降标准、未新增第二套 complex 判定器、未改 Agent 协作协议
- 风险 / 观察项：
- 结构化讲解信号仍依赖任务形态 cue，其他面试表述可能未覆盖
- `complex_web_kb_compare` 本轮 E2E 通过，非本轮修复目标，稳定性待观察
- 后续建议：
- 扩展讲解型 cue 时继续在 `complexity_policy` 单点维护，勿在 `kb_fast_impl` 平行写判断
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v3_complex_agent`
- 复测（2026-06-16）：`regression_all` 42/42；`complex_interview_explanation` 通过

---

## KI-V3-003

- Issue ID：`KI-V3-003`
- 标题：`insufficient evidence answer contract 不稳定`
- 来源版本：`V3：Complex / Agent Collaboration`
- 来源 case：`complex_insufficient_evidence`
- 问题类型：`insufficient evidence honesty / answer contract instability`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_151849.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_152512.json`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_153727.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_154141.json`
- 现象（修复前）：
- push 前稳定性复核中 `v3_complex_agent` 出现 **2/3 为 7/8**，失败 case 均为 `complex_insufficient_evidence`
- 三轮路由/出口态一致：`task_status=partial`、`lane=kb`、`mode=fast`、`winner_rule=pending_kind`、`insufficient_evidence=true`
- 失败断言：`evidence insufficiency not honestly reflected in answer` / `absolute conclusion given under insufficient evidence`
- LLM 回答偶发缺少稳定「证据不足 / 无法确认」表达，导致诚实性文本断言抖动
- 修复摘要（2026-06-15）：
- 在 `apply_exit_envelope`（`turn_response_builder` 出口组装层）对 `insufficient_evidence=true` 施加稳定回答契约前缀
- 前缀强制包含「现有材料不足，无法确认」，保留原 answer 正文
- 未改 eval、未改 `turn_exit_gate`、未改 V3-001/V3-002 路由
- 修复后 E2E：`v3_complex_agent` 连跑 **3/3 为 8/8**；`complex_insufficient_evidence` 稳定通过
- 为什么是真问题：
- `insufficient_evidence` 事实已存在，但用户可见 answer 表达不稳定
- 在证据不足场景下，回答契约应确定性表达「不能确认」，而非依赖 LLM 措辞侥幸
- 影响范围：
- KB / mixed 路径下 `insufficient_evidence=true` 的出口回答
- V3 诚实性 case `complex_insufficient_evidence`
- 当前处理策略：
- 已于 2026-06-15 完成最小 answer contract 修复并冻结
- `material_sufficiency=sufficient` 与 `insufficient_evidence=true` 可并存：表示「有检索材料，但不足以支持强结论」
- 风险 / 观察项：
- `complex_web_kb_compare` 仍作为稳定性观察项，非本轮修复目标
- 后续建议：
- 如需扩展不足表达模板，继续在 `insufficient_evidence_answer_contract.py` 单点维护
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v3_complex_agent`
- 复测（2026-06-16）：`regression_all` 42/42；`complex_insufficient_evidence` 通过
