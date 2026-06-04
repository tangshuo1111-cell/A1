# KB Agent Eval Benchmark

这个目录存放“知识库检索 + Agent 组织能力”的固定评测题集。

## 文件说明

- [questions_v1.json](/D:/1/A1_publish/benchmarks/kb_agent_eval/questions_v1.json)
  - 固定 10 题 KB benchmark

## 推荐工作流

优先直接跑当前工作区代码：

```powershell
py -3.12 scripts/benchmarks/run_kb_agent_eval.py --runner local
```

如果要验证某个独立服务进程，再显式指定 HTTP：

```powershell
py -3.12 scripts/benchmarks/run_kb_agent_eval.py --runner http --base-url http://127.0.0.1:8001
```

这样可以避免“知识库 benchmark 命中旧进程 / 旧配置”的误判。

## 定向补强材料

如果要专门提升 `KBX1~KBX10` 这组题的知识支撑，可以先把 `docs/history/current` 里的定向补强材料入库：

```powershell
py -3.12 scripts/benchmarks/ingest_kb_strengthening_pack.py
```

当前补强 pack 默认包含：

- [20_KB补强_主链边界与复杂题升级规则.md](/D:/1/A1_publish/docs/history/current/20_KB补强_主链边界与复杂题升级规则.md)
- [21_KB补强_材料流与不依赖后台TaskJoin原则.md](/D:/1/A1_publish/docs/history/current/21_KB补强_材料流与不依赖后台TaskJoin原则.md)
- [22_KB补强_当前系统风险优先级与四周整改路线图.md](/D:/1/A1_publish/docs/history/current/22_KB补强_当前系统风险优先级与四周整改路线图.md)
- [23_KB补强_重视频Compare信息流与专项链协作.md](/D:/1/A1_publish/docs/history/current/23_KB补强_重视频Compare信息流与专项链协作.md)

入库完成后，再复跑：

```powershell
py -3.12 scripts/benchmarks/run_kb_agent_eval.py --runner local
```

重点观察：

- `agno_basic_v3_web` 是否下降
- `retrieved_chunks_count` 是否从 `0/1` 提升到 `2+`
- `KBX1 / KBX2 / KBX6` 是否不再轻易掉到 web fallback
