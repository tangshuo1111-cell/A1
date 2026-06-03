# 25 KB补强：基准题直答材料 B

## 用途

本文件专门为 KB benchmark 中的 `KBX6 ~ KBX10` 提供直答型知识块。

重点覆盖：

- 不依赖后台 task join 的原则
- 两条重视频 compare 信息流
- 哪些问题已降级为实现收口问题
- 为什么 Agent 能力上限存在但工程成熟度还不够
- 未来 4 周整改路线图

---

## KBX6

### 问题

请基于知识库，解释为什么“多 Agent 主链不该依赖后台 task join 才成立”这个判断是合理的，同时给出它成立的前提和边界。

### 直答材料

这个判断合理，因为：

1. **Agent 主链的核心职责是消费材料并组织结论**  
   Agent 主链的价值在于分析、比较、取舍、综合和表达，而不是自己长成第二套后台任务系统。

2. **后台 task join 属于专项能力链 / async plane 的职责**  
   视频下载、ASR、OCR、大文档解析等长后台重处理，本质上是 capability / worker / async 的职责，不应让 Agent 自己承担 enqueue / poll / join / retry。

3. **temporary / pending / committed 三层材料流就是解耦手段**  
   更合理的做法是：专项链先把资料变成可消费材料，再交给 Agent 做复杂分析。

成立前提：

- 专项链能稳定产出可消费材料
- temporary / pending / committed 三层语义清楚
- shared retrieval 与 material trace 一致

边界：

- Agent 可以要求补材料
- 可以触发第二轮 gather
- 但不应把“等待长后台任务完成”当成自己的常规基础能力

---

## KBX7

### 问题

请结合知识库中的协作施工计划和你对当前实现的评测，设计一个“更合理的两条重视频 compare 信息流”，要求说明每一层负责什么。

### 直答材料

更合理的两条重视频 compare 信息流应是：

1. **ingress / complexity_policy**
   - 识别这是 compare 类复杂题
   - 产出 `complex_candidate`

2. **approval_gate**
   - 判断是否需要确认长视频 / 重处理

3. **capability / async 预处理链**
   - 各自处理两条视频
   - 产出两份 temporary / pending material

4. **shared retrieval / material pool**
   - 汇总两份材料
   - 形成同一份 shared snapshot

5. **complex round0 answer**
   - 先完成第一轮比较和结论组织

6. **quality_gate**
   - 判断 round0 是否够交付
   - 判断是否 need_second_round

7. **feedback_round / round1**
   - 如需要，优先补材料，再增强结构和结论

每层负责什么：

- capability / async：把视频变成材料
- Agent 主链：比较与综合
- quality_gate：决定 round0 是否足够

---

## KBX8

### 问题

请基于知识库里的材料，说明当前系统中哪些问题已经从“架构协作问题”降级成了“实现收口问题”，哪些还不是。

### 直答材料

已经从架构协作问题降级成实现收口问题的：

- `multisource_compare` 并入统一 quality gate 二轮模型
- approval 与 commit 闭环
- material trace 全路径输出
- shared retrieval / `kb_sufficiency` / `quality_gate` 的协议统一

这些问题的主设计已经明确，后续主要是：

- trace 一致性
- baseline
- 测试
- 边缘路径治理

还不是单纯实现收口问题的：

- 复杂题升级阈值是否足够稳
- complex 题进入 Agent 后能否完整交付
- KB 证据覆盖度与厚度是否足够

也就是说：

当前系统真正剩下的硬问题，不再是“架构有没有”，而是“能力是否稳定生效”。

---

## KBX9

### 问题

请结合知识库中的 Agent 评测基准结果，分析当前系统为什么“复杂推理组织能力上限存在，但工程成熟度还不够”。

### 直答材料

当前系统“复杂推理组织能力上限存在，但工程成熟度还不够”的原因是：

1. **能力上限存在**  
   在真正进入 `agno_basic / complex` 的题上，系统可以做多维分析、比较、路线图和结构化结论，这说明 Agent 主链能力上限不是问题。

2. **工程成熟度不足体现在稳定性**  
   问题在于：
   - 复杂题是否稳定进入 Agent 主链
   - 进入后是否完整交付
   - KB 材料是否够厚
   - 路由、trace、测试、baseline 是否一致

3. **所以当前短板更偏工程收口，不偏能力缺失**  
   不是模型完全不会答，而是：
   - 有时没走到该走的链
   - 或证据不足
   - 或预算内只给了 partial

---

## KBX10

### 问题

如果你是这个项目的架构负责人，请基于知识库给出未来 4 周的整改优先级路线图，要求分成：统一口径、行为收口、数据能力、专项链优化。

### 直答材料

未来 4 周整改优先级路线图建议如下：

### 第 1 周：统一口径

- 冻结 fast / complex / async executor profile
- 冻结 `complex candidate` 规则
- 冻结 `quality_gate` / `feedback_gate` / `approval_gate` 职责
- 冻结 temporary / pending / committed 三层材料语义

### 第 2 周：行为收口

- 复杂题升级与二轮统一走 `quality_gate`
- `multisource_compare`、general fast、kb_fast 不再有核心豁免
- approval 与 commit 闭环
- integration tests、trace baseline、README 对齐

### 第 3 周：数据能力

- `RETRIEVAL_MODE=auto`
- `EMBEDDING_ENABLED=1`
- 补强 KB benchmark 定向材料
- 检查 chunk 厚度是否从 `0/1` 提升到 `2~4`

### 第 4 周：专项链优化

- complex 题完整交付能力
- partial / async 出口统一表达
- 视频、文档等专项链与 Agent 协作质量继续收口

一句话总结：

先统一口径，再统一行为，再提升数据能力，最后打专项链质量。
