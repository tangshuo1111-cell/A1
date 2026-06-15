# 评测层治理红线

## 定位

评测层是业务系统之外的验证与治理层，不是第二控制面，不参与产品运行时决策。

当前评测层范围：

- `tests/evaluation/`
- `scripts/evaluation/`
- `runtime_data/eval_sandbox/`

评测层职责只包括：

- 发请求
- 读取稳定输出字段
- 运行断言与分类规则
- 生成报告与归档证据

评测层不得承担：

- 业务路由推理
- 产品回答策略推理
- 运行时编排决策
- 通过保留临时内部字段来反向绑架业务实现

## 红线

后续在评测层新增逻辑时，禁止出现以下行为：

1. 新增“如果我是业务层，这个请求理论上应该怎么走”的内部路由推理逻辑。
2. 仅根据回答措辞细节判定产品失败，并将其作为硬失败依据。
3. 为了通过评测，要求业务层长期保留临时 `extra`、`trace`、`legacy` 字段。
4. 在 runner 中加入新的业务决策分支、补路由、补状态机或补材料判断。

## 字段分层

### 稳定验收字段

以下字段属于稳定验收字段，可作为 hard fail 的主要依据：

- `task_status`
- `primary_path`
- `pending_kind`
- `lane`
- `mode`
- `answer`

### 脆弱观测字段

以下字段属于脆弱观测字段，默认只用于 observability / warning：

- `extra.*`
- `v6_*`
- `v15_*`
- `trace*`
- 其他内部诊断字段、阶段性迁移字段、legacy 字段

### 使用原则

1. 稳定验收字段缺失或错误，可以判定为 hard fail。
2. 脆弱观测字段缺失，默认只记 warning，不直接判 failed。
3. 只有当某个脆弱字段被正式升级为公共契约后，才允许进入 hard fail。

## 规则分级

`must_not_happen` 的分级口径由评测代码中的规则目录统一维护，禁止在 case 文件中隐式发明新的硬规则语义。

### A 级：状态诚实性硬规则

用于约束“不能假成功、不能假状态”。

示例：

- 没有任务信号，不能声称已完成后台处理
- 没有 transcript / 视频材料信号，不能声称“看完视频”

规则要求：

- 允许 hard fail
- 优先依赖稳定字段

### B 级：证据一致性规则

用于约束“回答声称的依据，必须和材料信号一致”。

示例：

- 没有 KB 命中或检索信号，不能声称“根据知识库明确得出”
- 没有网页材料信号，不能声称“根据网页内容”

规则要求：

- 可 hard fail
- 不降低判定强度，只降低脆弱性
- 必须遵循“字段优先，文案辅助”

### C 级：文案与可观测性辅助规则

用于辅助观察，不直接充当产品是否失败的主依据。

示例：

- 是否出现限制性表达
- 是否提到材料来源
- 是否暴露了某些观测字段

规则要求：

- 默认只记 warning
- 原则上不得阻塞回归

## 文案依赖收缩原则

评测层必须优先用字段判断，谨慎用措辞判断。

执行规则：

1. 字段优先，文案辅助。
2. 纯关键词命中不得单独导致 hard fail。
3. 只有“文案声称了不存在的能力或证据”这类假成功风险，文案才可参与 hard fail。
4. 其余文案类规则默认降级为 warning。

治理原则：

- 我们要降低的是脆弱性，不是判定强度。
- 事实型 fake success 规则必须保留 hard fail 能力。

如某条规则高度依赖具体措辞，应标记为“高脆弱规则”，不得继续扩张为更多硬规则。

## extra / trace 降级策略

后续评测规则在读取 `extra`、`trace`、`legacy` 字段时，必须遵循：

1. 有则提取，无则 warning。
2. 不得因缺少 `extra.v6_*`、`extra.v15_*`、`trace` 字段直接 hard fail。
3. 只有稳定出口字段缺失时，才允许判定为硬失败。

## known issue 与运行异常分离

评测治理中，必须区分产品缺陷与运行态异常。

### 只进入 known issues 的内容

- 稳定复现的错误业务结果
- 已确认是产品行为问题，而非环境噪音

### 不进入 known issues 的内容

- `backend_unavailable`
- `case_timeout`
- `execution_error`
- 单纯字段未暴露
- 单纯 warning

只有稳定复现且拿到错误业务结果时，才允许升级为 known issue。

## suite 增长控制

新增 case 前，必须先回答：

1. 这是在补真实用户风险，还是只是在观察更细？
2. 这个问题能否用已有 case 的 warning 扩展代替？
3. 这个 case 是否依赖脆弱字段或措辞细节？

准入原则：

- 如果只是“观察更细”，优先新增 warning，不新增 hard case。
- 每个版本只补关键缺口，不追求无限扩 case。

## runner 边界

runner 必须保持为薄层，只负责：

- 组织 payload
- 发请求
- 抽字段
- 跑规则
- 写报告

runner 不得负责：

- 推断业务理论路径
- 决定业务应该进入哪条内部 lane
- 自行补全业务状态机
- 代替业务做材料充分性或回答策略判断

## 优先治理顺序

评测层后续治理时，优先顺序固定为：

1. 减少对 `extra` / legacy trace 的硬依赖
2. 把文案型 hard rule 降成 warning
3. 把“观察字段”和“验收字段”彻底分开

## 下一阶段演进

下一阶段优化目标不是增强评测层存在感，而是增强一致性与可维护性。

### 1. rule_id 体系

目标：

- 让 `must_not_happen` 不再只依赖自然语言句子
- 让 case、runner、报告、known issue 共用稳定规则标识

要求：

- 新增规则优先进入规则目录
- case 可同时保留自然语言和 `rule_id`

### 2. case 结构分层

目标：

- 把 hard fail、warning、observability 从结构上拆开

推荐层次：

- `hard_assertions`
- `warning_assertions`
- `soft_observability`

### 3. 报告分栏

目标：

- 让产品失败、运行异常、观测性 warning 不再混读

建议分栏：

- stable contract failure
- evidence / state failure
- runtime issue
- observability warning
- wording / quality warning

### 4. known issue 与 eval gap 区分

目标：

- 避免把“评测没法稳定证明”误记成产品缺陷

建议区分：

- `product_defect`
- `eval_gap`
- `runtime_issue`
