# Phoenix 项目简报（指标沙箱代表资料）

项目代号：**Phoenix**

唯一追踪词：**METRICS_REUSE_TOKEN_PHX9**

Phoenix 是 LightMultiAgentQA 指标沙箱里用于验证「资料二次调用率（北极星1）」的代表资料。
口径：用户 commit 入库后，后续带 `use_knowledge` 的检索应命中 `source_kind=user_committed` 的 chunk。

简要说明：Phoenix 负责多来源资料沉淀、pending/commit 生命周期，以及检索复用观测。
