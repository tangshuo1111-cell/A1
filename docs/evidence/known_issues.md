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

## KI-V2-001

- Issue ID：`KI-V2-001`
- 标题：`video_total_failure 非法视频 URL 被 document_fast succeeded 接管`
- 来源版本：`V2：Capability Chains + Fake Success Negatives`
- 来源 case：`video_total_failure`
- 问题类型：`video intent honesty / invalid video URL fallback error`
- 当前状态：`Deferred`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_capability_all_20260613_154809.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_capability_all_20260613_154809.md`
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
- 当前不修业务主链
- 先纳入 known issue 台账
- 后续优先排查 video intent 命中后的 invalid URL / non-video URL 失败出口
- 后续建议：
- video 意图命中后，应优先维持 video lane 的失败或阻断语义
- 禁止无 transcript / 无 video evidence 时被 document fast 成功接管
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v2_capability_all`

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

---

## KI-V2.5-002

- Issue ID：`KI-V2.5-002`
- 标题：`continue_without_context_flow 空上下文继续请求被 succeeded + direct_llm 处理`
- 来源版本：`V2.5：Multi-turn State Closure`
- 来源 case：`continue_without_context_flow`
- 问题类型：`follow-up context honesty / empty-session closure error`
- 当前状态：`Deferred`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260613_154930.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260613_154930.md`
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
- 当前不修业务主链
- 先纳入 known issue 台账
- 后续优先排查 follow-up 检测、empty-session 守门和 closure honesty
- 后续建议：
- 无 previous steps / 无 stitch context 时，应更保守地落到 blocked、clarify 或显式无上下文状态
- 禁止把空上下文继续请求记为成功闭环
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v2_5_multiturn_state`

---

## KI-V3-001

- Issue ID：`KI-V3-001`
- 标题：`complex_document_reasoning 内联文档复杂分析协作证据不足`
- 来源版本：`V3：Complex / Agent Collaboration`
- 来源 case：`complex_document_reasoning`
- 问题类型：`complex material reasoning observability gap / 路由退化`
- 当前状态：`Deferred`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.md`
- 现象：
- 用户提供内联文档材料并要求复杂分析
- 真实响应返回：
- `task_status=succeeded`
- `primary_path=agno_basic_v2_kb`
- `lane=agno_basic_v2_kb`
- 这没有稳定体现 `document / material reasoning / general-complex` 的协作证据
- 为什么是真问题：
- 该 case 要测的是“基于当前用户提供材料的复杂分析”
- 真实路径更像 KB/basic path
- 不能充分证明系统基于当前内联材料完成了复杂协作分析
- 影响范围：
- 内联文档复杂分析题
- complex/document 路由可信度
- V3 Main / Middle / Answer 协作可观测性
- 当前处理策略：
- 当前不修业务主链
- 保留为 known issue
- 后续在 complex intent routing、inline material 标注、material reasoning 可观测性层统一治理
- 后续建议：
- 增强 inline material 场景的复杂题识别与材料归属信号
- 让 document/material reasoning 证据能稳定暴露到响应侧
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v3_complex_agent`

---

## KI-V3-002

- Issue ID：`KI-V3-002`
- 标题：`complex_interview_explanation 退化为 kb_fast`
- 来源版本：`V3：Complex / Agent Collaboration`
- 来源 case：`complex_interview_explanation`
- 问题类型：`complex agent collaboration degradation / kb_fast 接管`
- 当前状态：`Deferred`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.md`
- 现象：
- 项目面试讲解型复杂问题返回：
- `task_status=succeeded`
- `primary_path=kb_fast`
- 没有稳定体现预期的 complex agent collaboration 路径
- 为什么是真问题：
- 面试讲解型问题不只是知识库问答
- 它还需要复杂意图识别、材料组织、表达取舍和 grounding
- 当前 V3 无法充分证明 Main / Middle / Answer 协作链路稳定成立
- 影响范围：
- 项目面试讲解类复杂题
- complex / kb_fast 边界
- V3 协作证据可信度
- 当前处理策略：
- 当前不修业务主链
- 保留为 known issue
- 后续在 complex intent routing、kb_fast fallback、answer grounding 可观测性层统一治理
- 后续建议：
- 减少复杂项目讲解题被 `kb_fast` 直接吞掉的概率
- 增强该题型的 Main plan / Middle material / Answer grounding 暴露
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v3_complex_agent`
