# Evaluation Test Assets

本目录用于存放评测工程资产，不直接承载业务主链代码。

当前阶段为 `V0-R1`，目标是建立：

- case schema
- 最小 smoke case
- case loader
- 基础断言
- eval sandbox 工具
- 最小命令行脚本

当前 smoke 只做 **Schema Smoke**，不做真实能力验证。

## 目录说明

- `schemas/`：评测样例与结果 schema
- `cases/`：评测样例集
- `fixtures/`：固定测试资产说明
- `runners/`：loader、断言、sandbox 等执行工具

## 当前边界

本目录当前不做：

- 不调用 `/chat/agno`
- 不访问外部网络
- 不跑真实 OCR / ASR / Web / KB
- 不接 LLM judge
