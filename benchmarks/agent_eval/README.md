# Agent Eval Benchmark

这个目录存放“复杂推理与组织能力”的固定评测基线。

## 文件说明

- [questions_v1.json](D:/1/Rag_and_Agent_repo_staging/项目代码/benchmarks/agent_eval/questions_v1.json)
  - 固定题集
- [scoring_guide.md](D:/1/Rag_and_Agent_repo_staging/项目代码/benchmarks/agent_eval/scoring_guide.md)
  - 评分标准
- [baseline_2026-05-26.json](D:/1/Rag_and_Agent_repo_staging/项目代码/benchmarks/agent_eval/baseline_2026-05-26.json)
  - 第 1 轮人工评分基线

## 推荐工作流

1. 用 `scripts/benchmarks/run_agent_eval.py` 跑题，得到原始结果 JSON
2. 用 `scripts/benchmarks/score_agent_eval.py` 生成带汇总的评分文件
3. 用 `scripts/benchmarks/render_agent_eval_report.py` 生成可读 Markdown 报告
4. 用 `scripts/benchmarks/ingest_agent_eval.py` 把报告和评分结果写入 PG 知识库

默认建议直接跑 **当前工作区代码**：

```powershell
py -3.12 scripts/benchmarks/run_agent_eval.py --runner local
```

只有在你明确要验证某个独立 HTTP 服务进程时，才用：

```powershell
py -3.12 scripts/benchmarks/run_agent_eval.py --runner http --base-url http://127.0.0.1:8001
```

这样可以避免 benchmark 误打到旧进程或漂移配置。

推荐落点：

- 题集与基线：`benchmarks/agent_eval/`
- 执行脚本：`scripts/benchmarks/`
- 轻量框架测试：`tests/benchmarks/`

不把真实 12 题评测直接放进普通 `pytest` 主流程。

## 为什么不直接放进普通 tests

因为这类评测：

- 耗时长
- 含 LLM 波动
- 更像 benchmark/eval，而不是 deterministic 单元测试

所以：

- `benchmarks/agent_eval/` 放题集和基线
- `scripts/benchmarks/` 放执行脚本
- `tests/benchmarks/` 只测脚本输出 schema，不跑真实 12 题评测

## 当前脚本

- `run_agent_eval.py`
  - 真实跑题，生成原始结果 JSON
- `score_agent_eval.py`
  - 汇总原始结果，生成 summary JSON
- `render_agent_eval_report.py`
  - 从带评分 JSON 生成 Markdown 报告
- `ingest_agent_eval.py`
  - 把 Markdown 报告和评分 JSON 写入 PG 知识库
