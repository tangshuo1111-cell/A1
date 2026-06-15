# 评测规则脆弱性盘点

## 目的

本清单用于回答三个问题：

1. 当前哪些规则直接依赖回答措辞。
2. 当前哪些规则必须依赖 `extra`、`v6_*`、`v15_*` 等脆弱观测字段。
3. 当前哪些失败其实只是“字段没暴露”，应优先降级。

本清单是 `eval_governance_guardrails.md` 的配套落地文档。

当前 `must_not_happen` 的 A/B/C 分级由：

- `tests/evaluation/runners/eval_rule_catalog.py`

统一维护，用于避免 case 文案直接变成新的隐式硬规则。

## 一、直接依赖回答措辞的规则

以下文件存在直接关键词判断，应视为高脆弱规则来源：

### `tests/evaluation/runners/eval_agent_extractors.py`

- `groundedness_markers.has_limitation_statement`
- `groundedness_markers.claims_strong_conclusion`

风险：

- 依赖固定措辞集合
- 业务文案风格一改就可能漂移

当前处理：

- 只作为辅助 marker 使用
- 不应单独触发 hard fail

### `tests/evaluation/runners/eval_agent_collaboration_rules.py`

直接依赖措辞的判断：

- `claims_kb`
- `claims_web`
- `claims_video`
- “已经达到准生产级”
- “完整如下”
- “视频里主要讲了”
- “看完视频”

风险：

- 更像“答案口径审查器”而不是“稳定契约检查器”

当前处理：

- 仅文案辅助类保留在 warning 侧
- 涉及“无材料却声称有依据”的事实型 fake success 仍可 hard fail

### `tests/evaluation/runners/eval_state_extractors.py`

直接依赖措辞的判断：

- `answer_commit_signal`
- `followup_detected`
- `answer_mentions_previous`

风险：

- 依赖“保存成功”“已保存”“继续刚才”“刚才”等词

当前处理：

- 仅作为多轮闭环辅助观测

### `tests/evaluation/runners/eval_state_closure_rules.py`

直接依赖措辞的判断：

- “保存成功”
- “刚才”
- “上一轮”
- “网页”
- “初学者”
- “后台”

风险：

- 文案变动会影响规则结论

当前处理：

- 事实型闭环欺骗风险保留 hard fail
- 上下文承接质量、可观测性不足等高脆弱项保留 warning

## 二、强依赖脆弱观测字段的规则与提取器

### 高密度依赖文件

#### `tests/evaluation/runners/eval_agent_extractors.py`

主要依赖：

- `extra.*`
- `v6_main_pan_*`
- `v6_middle_pan_*`
- `v6_answer_pan_*`
- `v7_middle_pan_*`
- `v11_middle_video_url_text_source`
- `quality_gate.*`
- `material_bundle`
- `retrieval_snapshot`

判定：

- 属于复杂协作 observability 抽取器
- 不应被当成稳定验收字段来源

#### `tests/evaluation/runners/eval_state_extractors.py`

主要依赖：

- `extra.pending_kind`
- `extra.mode`
- `extra.lane`
- `extra.material_sufficiency`
- `extra.quality_gate.*`
- `extra.history_used`
- `extra.v8_middle_history_used`
- `extra.v15_pending_reference`
- `extra.commit_status`
- `extra.background_task_id`

判定：

- 属于多轮状态辅助观测
- 除稳定出口字段外，其余均应按 warning 处理

#### `tests/evaluation/runners/eval_capability_extractors.py`

主要依赖：

- `extra.web_*`
- `extra.capability_*`
- `extra.v13_material_status`
- `extra.provider_chain`
- `extra.v16_*`
- `extra.v15_retrieval_strategy`
- `extra.kb_*`

判定：

- 属于能力链观测抽取
- 适合做 fake-success 风险扫描，不适合做字段缺失硬失败

## 三、当前已识别的“字段没暴露”类失败源

### `required_trace_fields`

位置：

- `tests/evaluation/runners/eval_runner.py`
- `tests/evaluation/runners/eval_multiturn_runner.py`

问题：

- 名字就说明它依赖 trace / extra 观测层
- 不适合继续作为硬失败

当前处理：

- 已降为 warning

### `must_have_one_of` 中混入脆弱字段

位置：

- `tests/evaluation/cases/v3_complex_agent.yaml`
- `tests/evaluation/runners/eval_complex_agent_runner.py`

典型字段：

- `quality_gate`
- `material_sufficiency`
- `v6_main_pan_renwu`
- `v6_middle_pan_laiyuan`

问题：

- 这些字段不是稳定出口字段
- 以前会让“没暴露观察字段”看起来像产品失败

当前处理：

- runner 已改成：稳定字段参与 hard fail，脆弱字段只记 warning

## 四、建议保留为 hard fail 的内容

当前更适合继续保留 hard fail 的，仅限以下类型：

- `task_status` 非 canonical
- 稳定字段 `task_status / primary_path / pending_kind / lane / mode / answer` 缺失
- 稳定字段不在 case 允许值集合中
- 明确的状态诚实性硬错误

## 五、建议继续保留为 warning 的内容

- 文案中的限制性表达是否充分
- 是否声称“根据知识库/网页/视频”但观测字段不足
- second-round / quality-gate / material-gap 可观测性缺失
- 各类 `v6_* / v7_* / v11_* / v15_* / trace` 缺失
- 依赖具体措辞细节的上下文承接质量判断

## 六、下一步治理顺序

1. 继续减少 `eval_assertions.py` 中对 `extra + answer` 组合的硬依赖。
2. 逐步把 case 里的 `must_not_happen` 从文案描述改成更稳定的状态诚实性描述。
3. 把复杂协作与多轮评测中的 observability summary 和验收结论彻底分栏。
