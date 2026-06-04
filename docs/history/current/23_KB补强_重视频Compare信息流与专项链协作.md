# 23 KB补强：重视频 Compare 信息流与专项链协作

## 目的

本文件主要补强 `KBX4`、`KBX7`、`KBX10`，聚焦：

- Agent 主链、capability 主链、async task 主链如何协作
- 两条重视频 compare 的合理信息流
- 各层到底负责什么

## 一、两条重视频 compare 的理想信息流

当用户要求：

- 对比两条长视频
- 做主题差异分析
- 给路线图、结论或优先级判断

更合理的信息流应是：

```text
用户请求
-> ingress / complexity_policy 识别为复杂 compare
-> approval_gate 判断是否需要明确确认重处理
-> 两条视频分别进入 capability / async 预处理链
-> 产出两份 temporary material 或 pending material
-> shared retrieval / material_pool 汇总这两份材料
-> complex round0 answer
-> quality_gate 判断是否 need_second_round
-> 如需要，再 feedback_round 补材料或补综合
-> 交付最终 compare 结论
```

## 二、每一层分别负责什么

### 1. ingress / complexity_policy

负责：

- 识别这是 compare 类复杂题
- 给出 `complex_candidate`
- 只做初始建议，不直接把所有逻辑写死

不负责：

- 直接决定答案是否可交付
- 决定是否二轮

### 2. approval_gate

负责：

- 判断是否需要确认长视频 / 重处理
- 判断是否涉及 pending commit

不负责：

- 直接给复杂结论
- 替代质量门控

### 3. capability / async 预处理链

负责：

- 视频下载
- 音频准备
- 转写
- 重资料提取
- 生成 `temporary material` / `pending material`

不负责：

- 最终比较
- 最终取舍
- 最终路线图输出

### 4. shared retrieval / material pool

负责：

- 汇总可消费材料
- 形成统一 snapshot
- 供 fast / complex 共享

不负责：

- 自己替用户下结论

### 5. complex round0 answer

负责：

- 基于当前材料做第一轮比较
- 看是否已经能覆盖：
  - 差异
  - 共同点
  - 结论
  - 建议

### 6. quality_gate

负责：

- 判断 round0 是否足够交付
- 判断是否 need_second_round
- 决定是：
  - pass
  - escalate
  - need_more_material

### 7. feedback_round / round1

负责：

- 当 quality 不过线时再做：
  - 补材料
  - 扩 gather
  - 改善比较结构
  - 强化结论

## 三、为什么不该让 AnswerAgent 自己偷偷触发 compare 二轮

如果让 AnswerAgent 在 compare 场景下自己决定：

- 再抓一轮
- 再补一轮
- 再看一轮

就会出现：

- multisource 一套逻辑
- 普通 complex 一套逻辑
- trace 和预算语义不一致

因此，更合理的原则是：

- round0 先统一产出
- `quality_gate` 统一判是否二轮
- `feedback_gate` 再判允不允许执行二轮动作

这能保证：

- compare 路径与普通 complex 路径一致
- 不再有核心豁免

## 四、重视频 compare 场景下三条主链的真实分工

### Agent 主链

负责：

- 比较
- 综合
- 判断
- 表达

### capability 主链

负责：

- 两条视频分别变成可消费材料

### async task 主链

负责：

- 如果任一视频超出同步预算，就承接后台重处理

所以两条重视频 compare 的合理架构不是：

- “让 Agent 直接等待两个后台任务完成”

而是：

- “让专项链先把两份材料准备好，再交给 Agent 做 compare”

## 五、当前系统里哪些问题仍然会影响重视频 compare

即使主链职责已经更清楚，重视频 compare 仍会受这些问题影响：

1. 复杂题升级是否足够稳定  
如果没有稳定进入 complex / Agent，compare 会偏浅。

2. 专项链能否产出足够厚的材料  
如果两条视频只产出很薄的文本，Agent compare 也会变薄。

3. quality_gate 是否能稳定判断 need_second_round  
如果 round0 明显不够，却没有稳定开 round1，最终结果仍会偏弱。

## 六、直接结论

如果要设计一个“更合理的两条重视频 compare 信息流”，最关键的不是新增一个 Agent，而是明确三件事：

1. capability / async 负责把两条视频变成材料
2. Agent 主链负责比较与综合
3. `quality_gate` 负责决定 round0 是否足够、是否需要二轮

一句话总结：

**重视频 compare 的正确做法，不是让 Agent 负责等后台 join，而是让专项链先把两份视频转成可消费材料，再由 Agent 基于同一份 shared snapshot 做复杂比较。**
