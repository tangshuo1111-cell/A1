# 21 KB补强：材料流与不依赖后台 Task Join 原则

## 目的

本文件主要为 `KBX2`、`KBX6`、`KBX7`、`KBX8` 提供稳定知识材料。

重点回答两个问题：

1. 为什么“多 Agent 主链不该依赖后台 task join 才成立”这个判断是合理的
2. temporary / pending / committed 三层材料流在当前系统里分别承担什么职责

## 一、为什么多 Agent 主链不该依赖后台 task join

这个判断合理，是因为：

### 1. Agent 主链的核心价值是“消费材料并组织结论”

Agent 主链的核心价值在于：

- 做复杂分析
- 做比较与取舍
- 做多材料综合
- 输出有结构的结论

它最值钱的部分是：

- 怎么判断
- 怎么比较
- 怎么收口

而不是：

- 怎么排后台任务
- 怎么等两个 worker 同时完成
- 怎么自己长成第二套任务系统

### 2. 后台 task join 属于专项重处理编排问题

当问题涉及：

- 视频下载
- 音频提取
- ASR
- OCR
- 大文档解析

这些本质上是 capability / worker / async plane 的职责。

如果让 Agent 主链自己负责：

- enqueue
- poll
- join
- retry
- merge status

那么 Agent 主链就会和专项后台工作流重复，结果通常是：

- 多一套状态机
- 多一套超时语义
- 多一套失败恢复
- 复杂度更高

### 3. 正确的方式是“先把重资料变成可消费材料”

更合理的模式是：

专项链先处理重资料
-> 产出 `temporary material` / `pending material`
-> Agent 基于这些材料做分析、比较、组织

这样：

- 重处理归专项链
- 复杂分析归 Agent 主链
- 责任边界更清楚

## 二、三层材料流：temporary / pending / committed

### 1. `temporary material`

定义：

- 当轮或短期会话内可消费的材料
- 默认不进入长期知识库
- 供 fast / complex / compare 直接使用

特点：

- 生命周期短
- 可以来自视频转写、网页抓取、文档解析、共享检索
- 主要服务“这次回答”

### 2. `pending material`

定义：

- 已经准备好，但还未正式 commit 到长期知识库的材料

特点：

- 可以先被当前会话消费
- 用户确认前，不应自动变成长期知识
- 常用于：
  - 文件解析结果
  - 待保存材料
  - 待确认入库结果

### 3. `committed knowledge`

定义：

- 用户已确认，已正式写入长期知识库的知识

特点：

- 可被后续 `retrieve`
- 是长期 RAG / KB 的正式语料
- 不应和 temporary/pending 混为一谈

## 三、为什么不应默认自动 commit

默认自动 commit 会带来三个问题：

1. 污染知识库  
临时分析材料、一次性网页、低质量抓取结果容易被永久写入。

2. 用户失去确认权  
很多场景下，用户需要先看内容再决定是否保存。

3. 材料语义混乱  
如果没有清晰地区分 temporary / pending / committed，后续很难判断当前答案到底是基于哪一层材料做的。

因此，更合理的原则是：

- 默认先 temporary
- 需要时进入 pending
- 用户确认后才 committed

## 四、两条重视频 compare 的合理信息流

对“两个重视频 compare”这类问题，合理的信息流应该是：

1. 视频专项链分别处理两条视频
2. 产出两份 `temporary material` 或 `pending material`
3. Agent 主链读取这两份材料
4. Agent 做：
   - 比较
   - 差异分析
   - 结论组织
5. 如用户要求保存，再走 commit

不合理的方式是：

1. Agent 先起 compare
2. Agent 自己等两个后台 task 都完成
3. Agent 再继续 compare

这种方式会让 Agent 主链承担原本不该承担的 worker / join 职责。

## 五、这条原则成立的前提与边界

### 成立的前提

这条原则成立的前提是：

- 专项链能稳定产出可消费材料
- temporary / pending / committed 三层语义清楚
- Agent 能明确消费哪一层材料
- 共享检索与材料 trace 一致

### 它的边界

这条原则并不意味着：

- Agent 永远不发起补料
- Agent 永远不能触发第二轮 gather

更准确地说：

- Agent 可以判断“还缺什么材料”
- 但 Agent 不应把自己做成第二套长后台任务系统

也就是说：

- `need_more_material` 可以存在
- 第二轮补料可以存在
- 但长后台 join 不应成为 Agent 主链的常规基础能力

## 六、直接结论

“多 Agent 主链不该依赖后台 task join 才成立”这个判断之所以合理，是因为：

1. Agent 主链的职责是分析、比较、组织结论
2. 长后台 task join 的职责属于专项能力链 / async plane
3. temporary / pending / committed 三层材料流，正是把这两者解耦的关键

所以更健康的系统形态是：

**专项链负责把资料处理成可消费材料，Agent 主链负责基于这些材料完成复杂分析，而不是亲自把自己长成第二套后台任务系统。**
