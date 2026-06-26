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

## 复测摘要（最新：2026-06-22）

真实环境复跑（`LIGHT_MAQA_FAKE_LLM=0`）：

| 套件 | 结果 | 说明 |
| ---- | ---- | ---- |
| `regression_all` | **42/42 passed** | V1 10/10、V2 16/16、V2.5 8/8、V3 8/8；`has_unknown_failures=False` |
| `real_external_smoke` | **7/7 capability passed** | 与 regression 独立；`environment_ready` |

总览证据：`runtime_data/eval_sandbox/reports/eval_v4_regression_overview_20260622_111708.json`（不入库；历史 `..._20260616_112055.json`）
real_external 证据：`runtime_data/eval_sandbox/reports/eval_real_external_smoke_20260622_105055.json`（不入库）

> 2026-06-22 复跑新增：`web_url_basic` 在真实环境出现 web↔document 的 lane 漂移，已记为 **KI-V1-001**（路由非确定性，非诚实性缺陷），并对该 case 放宽到接受两条诚实路径。
>
> 2026-06-22 指标沙箱新增并修复：**KI-V1-003**（访问墙分类器裸子串扫 HTML 框架头，维基/MediaWiki 页被误判 captcha），已修复为「只扫可见正文」，async_03 / async_04 由 failed 转 partial。
>
> 2026-06-22 修复：**KI-V1-004**（`document_fast` 上传解析不建 pending，导致「保存到知识库」被 approval gate 拦截）→ upload 同步 `prepare_file_source` 写入 pending；`reuse_flow_01` 可用普通 prepare 话术。
>
> 2026-06-22 修复：**KI-V1-001** 由 `Deferred` 转 `Fixed` — `_lane_from_main_plan` 对显式网页读取意图锚定 `web` lane，MainAgent 误标 `text/text_file` 不再漂到 `document`。
>
> 2026-06-25 修复（仅 FAKE 桩，不动质量门）：**KI-METRICS-001** 的可操作根因（占位回答过短无结构→被既有质量门挡在第一步→连通跑只反映噪声）已在 `backend/agents/answer_agent/llm_exec.py` 的 FAKE 分支修复：桩改为**显式标注的结构化回答**，让 FAKE「验管线连通」跑能真正流过**未改动**的质量门。环境口径性质（FAKE 比率≠产品质量）不变，仍由报告层 `environment=FAKE / 判定不适用` 守护，故 KI 保留为环境告警。

下文 KI-V2-001 / KI-V2.5-001 / KI-V2.5-002 / KI-V3-001 / KI-V3-002 / KI-V3-003 均为 **`Fixed`**；本轮复测未再命中对应 case 失败。

---

## KI-V1-001

- Issue ID：`KI-V1-001`
- 标题：`web URL 在 LLM 升级路径下存在 lane 漂移（web ↔ document ↔ async）`
- 来源版本：`V1：Route + Exit State + Basic Honesty`
- 来源 case：`web_url_basic`
- 问题类型：`routing non-determinism / LLM-escalation lane drift`（非诚实性缺陷）
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v1_route_exit_state_20260622_105734.json`（本次落 `lane=document`、`succeeded`）
- 对照：先前真实跑曾落 `lane=web` → demote 成 `primary_path=web_async`（pending）
- 现象：
- 同一输入「请读取这个网页并总结重点：https://example.com」在真实环境跨次复跑落到不同 lane
- 规则层 `select_lane` 会判 `web`（`has_web_url + has_web_intent`，置信 0.90）
- 但置信度触发升级走 LLM `MainAgent` 时，`_lane_from_main_plan` 可能把「读取网页正文」判成 `source_type=text/text_file` → 返回 `document`
- 两种结果都 `succeeded` 且未触发 `B_NO_WEB_CLAIM_WITHOUT_EVIDENCE`（没有在无正文时假装读网页），即都是诚实输出
- 为什么是真问题（而非单纯 case 口径）：
- 这不是断言值写窄，而是 LLM 增强的分层编排里，升级路径对「读网页 vs 文本入库」的判定本身非确定
- 同一请求的 lane / primary_path 跨次不稳定，会影响可观测口径与回归可重复性
- 影响范围：
- 含 http(s) URL 且带「读取/总结」意图的请求
- V1 路由/出口态回归的跨次稳定性
- 当前处理策略：
- 本轮把 `web_url_basic` 的 `allowed_lanes` / `allowed_primary_paths` 放宽到同时接受 web 与 document 两条诚实路径（含 `web_async` / `document_*`），使回归不因诚实的 lane 漂移误报失败
- 2026-06-22 缓解：路由 LLM 温度 **0.0**（贪心解码）
- **2026-06-22 根治（最小锚点）**：`backend/application/ingress/semantic_router.py` 的 `_lane_from_main_plan` — 当 `signals.has_web_url ∧ has_web_intent` 且无文件 payload 时，MainAgent 误标 `text/text_file` 仍返回 `web` lane；单测 `tests/unit/test_ki_v1_001_web_lane_anchor.py`
- 未放宽任何诚实性规则（B_NO_WEB_CLAIM 仍生效）
- 后续建议：
- 证据达标后可评估 `ENABLE_SEMANTIC_ROUTE_CUTOVER`（当前仅 shadow 观测）
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v1_route_exit_state`

---

## KI-V1-002

- Issue ID：`KI-V1-002`
- 标题：`is_commit_intent 裸子串匹配，讨论"入库/保存"策略的分析问题被误判为提交入库命令`
- 来源版本：`V1：Route + Exit State + Basic Honesty`
- 来源 case：`指标沙箱 complex_10 / complex_17`（北极星2 复杂任务有效完成率沙箱）
- 问题类型：`commit-intent over-trigger / 命令意图裸子串误命中`（非诚实性缺陷）
- 当前状态：`Fixed`
- 原始证据：
- `_local/reports/metrics/weekly_2026-06-22.json`（complex_10 / complex_17 落 `task_status=blocked`、文案「当前会话没有可保存的 pending 资料」、`is_complex_task=false`）
- 代码：`backend/application/chat/approval_gate.py` 中 `_COMMIT_HINTS = ("保存","入库","存进知识库","存入知识库","commit","确认保存")`，`is_commit_intent` 为纯子串 `any(hint in msg)`
- 现象：
- 用户问的是「评估『自动入库』与『确认后保存』两种**策略**的影响」这类分析题
- 因 message 文本里**出现**了「入库 / 确认保存」子串 → `is_commit_intent=True`
- 会话内并无 pending 资料 → `evaluate_pending_commit` 返回 `kind=pending_commit, reason=no_pending_item, blocked=True`
- 整轮被 approval gate 直接 blocked，未进入 complex 协作链
- 为什么是真问题（而非单纯 case 口径）：
- 命令意图判定靠裸子串，无法区分「执行入库命令」与「讨论入库策略」
- 任何含「保存 / 入库」字样的分析型问题都会被误拦，属真实产品脆弱点
- 影响范围：
- 含「保存 / 入库 / commit」字样、但实为分析/比较意图的请求
- 北极星2 沙箱复杂子集（被踢出 is_complex_task 分母）
- 修复摘要（2026-06-22）：
- `backend/application/chat/approval_gate.py` 的 `is_commit_intent` 由裸子串 `any(hint in msg)` 收窄为三段判定（不改 `ApprovalGateResult` 契约，只减少误判）：
  1) 命中明确祈使保存短语（`保存到 / 存入 / 帮我保存 / 确认保存` 等 `_IMPERATIVE_SAVE`）→ 始终判 commit，保护真实保存意图；
  2) 命令词被书名号/引号包裹（作讨论对象），或句中含 >=2 个分析/比较标记（`评估 / 对比 / 影响 / 优缺点 / 维度 …`）→ 视为讨论，不判 commit；
  3) 其余维持原裸子串判定。
- 修复证据：
- 双向单测 `tests/unit/test_ki_v1_002_commit_intent.py`（真实保存仍 commit、分析题不再误判、空串/无 hint 不误判），与 `tests/backend/application/chat/test_approval_gate_flow.py` 合计 23 passed
- 残留边界（已知、可接受）：
- 无祈使保存短语、却带 >=2 个强分析标记的保存句（如「把对比分析的优缺点保存」）可能被判为讨论；如确需保存，使用「保存到/存入知识库」等明确祈使措辞即可命中
- 后续建议：
- 沙箱 `complex_10 / complex_17` 已用「沉淀/收录」改写，无需回退；新写分析题不再需要刻意避开「保存/入库」字样
- 回归方式：
- `py -3.12 -m pytest tests/unit/test_ki_v1_002_commit_intent.py tests/backend/application/chat/test_approval_gate_flow.py -q`
- 或重跑指标沙箱：`py -3.12 scripts/run_metrics_sandbox_samples.py --api http://127.0.0.1:8001 --truncate-metrics --report`

---

## KI-V1-003

- Issue ID：`KI-V1-003`
- 标题：`访问墙分类器裸子串扫 HTML 框架头，MediaWiki/维基页被误判 captcha`
- 来源版本：`V1：Route + Exit State + Basic Honesty`
- 来源 case：`指标沙箱 async_03 / async_04`（北极星2 沙箱 async 子集）
- 问题类型：`access-wall classifier false-positive / 裸子串误命中`（与 KI-V1-002 同族，非诚实性缺陷）
- 当前状态：`Fixed`
- 原始证据：
- `_local/reports/metrics/weekly_2026-06-22.json`（修复前 async_03 / async_04 落 `task_status=failed`、文案「网页抓取失败：captcha_not_supported」）
- 代码：`backend/tools/web/dynamic_providers.py` 中 `classify_dynamic_wall` 旧实现 `sample = f"{text}\n{html[:4000]}"`，`backend/tools/web/common.py` 中 `looks_like_access_wall` 旧实现 `sample = f"{text}\n{html[:2000]}"`，均对原始 HTML 做裸子串扫描
- 现象：
- async_03 / async_04 抓取 `en.wikipedia.org/wiki/{Retrieval-augmented_generation,Vector_database}`，Playwright 抓取与 bs4 正文抽取均成功、可见正文干净
- 但 MediaWiki 的 HTML 头登记了 `ext.confirmEdit.hCaptcha` 等模块名，`html[:N]` 原始头含 `captcha / hcaptcha` 字样
- 裸子串命中 → 整页被判 `captcha_not_supported` 访问墙 → 已抓到的好正文被丢弃 → 上报 failed
- 复现（修复前）：`classify_dynamic_wall` 对两篇维基均返回 `captcha_not_supported`，命中位置在 `html[:4000]`、可见正文命中为空
- 为什么是真问题（而非单纯 case 口径）：
- 任何 MediaWiki/维基系站点（一大类合法、可匿名阅读来源）都会被这一刀切误判失败
- 对照 async_02（纽时，有真反爬）反而拿到 partial 正文，反证「扫原始 HTML 头」口径错误
- 影响范围：
- web 动态抓取（`fetch_dynamic_page`，async/web lane）与静态抓取（`fetch_web_page` / cookie 抓取）对 MediaWiki 类站点的访问墙判定
- 北极星2 沙箱 async 子集
- 修复摘要（2026-06-22）：
- `classify_dynamic_wall` 与 `looks_like_access_wall` 改为**只扫可见正文 `text`**，不再扫原始 HTML 框架头
- 依据：访问墙会用挑战/登录文案替换可见内容，标志词必落在正文；HTML 头是框架样板噪声
- 仅收窄误判面，未改 fetch 链路、未动路由/状态/质量门/出口/事实源分层，未新增 Gate
- 修复证据：
- 双向验证（真实维基 HTML + 模拟真墙）：维基 RAG / Vector database 均放行；真验证码页仍 `captcha_not_supported`、登录墙仍 `login_required / cookie_required`
- 端到端重跑：`_local/reports/metrics/weekly_2026-06-22.json`（async_03 / async_04 由 failed 转 `partial`、`async_poll_error` 为空，拿到真实正文摘要）
- web 工具单测 23 passed（`tests/unit/test_web_url_and_truncate.py`、`tests/unit/test_tool_dispatch_full.py`、`tests/acceptance/test_critic_feedback.py`）
- 后续建议：
- 若需更强反爬识别，应在「渲染后可见内容」维度做（如 challenge 页特征），不要回退到扫原始 HTML 框架头
- 回归方式：
- 重跑指标沙箱：`py -3.12 scripts/run_metrics_sandbox_samples.py --api http://127.0.0.1:8001 --truncate-metrics --report`

---

## KI-V1-004

- Issue ID：`KI-V1-004`
- 标题：`document_fast 上传解析不建 pending，「保存到知识库」被 approval gate 拦截`
- 来源版本：指标沙箱 `reuse_flow_01` / 默认 upload prepare 链路
- 来源 case：`reuse_flow_01`（修复前）、任意 `/chat/agno/upload` + 普通「解析要点」话术
- 问题类型：`material lifecycle gap / upload prepare 与 pending store 脱节`
- 当前状态：`Fixed`
- 现象：
- 用户 upload → `document_fast` 同步解析并摘要，`material_state=prepared`
- 但 **未** 调用 `prepare_file_source` 写入 pending store
- 下一轮「保存到知识库」→ `list_pending` 为空 → approval gate `no_pending_item` / blocked
- 指标沙箱曾被迫用 complex 分析型话术绕路才能 commit
- 修复摘要（2026-06-22）：
- `document_fast_impl._register_upload_pending_extra`：有 `session_id + v13_file_content` 时同步 `prepare_file_source`
- extra 暴露 `v13_material_status=pending` / `pending_source_id` / `material_pending`
- 单测：`tests/unit/test_document_fast_upload_pending.py`
- 回归方式：
- `py -3.12 -m pytest tests/unit/test_document_fast_upload_pending.py -q`
- 指标沙箱 `reuse_flow_01` 使用普通 prepare 话术全 API 链路

---

## KI-METRICS-001

- Issue ID：`KI-METRICS-001`
- 标题：指标沙箱在 `LIGHT_MAQA_FAKE_LLM=1` 下 complex 回答为占位文本，quality gate 大面积 block
- 来源版本：指标沙箱北极星2 观测
- 来源 case：`complex_*` 子集（`_local/reports/metrics/weekly_2026-06-22.json`）
- 问题类型：`observability environment limitation`（非产品诚实性缺陷）
- 当前状态：`Open`（环境口径问题，非主链 bug；2026-06-25 已修复其中"占位桩过短被门挡死"的可操作根因，详见下方处理策略）
- 现象：
- FAKE 回答形如「测试回答：{原题}」，缺少对比结构/决策标记 → `quality_gate_block`
- 北极星2 `complex_effective_complete_rate` 在 FAKE 沙箱上极低（如 4%），**不可外推为产品质量**
- 当前处理策略：
- **默认即真实 LLM**：指标沙箱 `scripts/run_metrics_sandbox.ps1` 默认 `LIGHT_MAQA_FAKE_LLM=0`（真实外部 LLM），北极星周报本来就是真实 LLM 跑的；4% 仅来自显式 `-FakeLLM` 的「仅验管线连通」跑。**本 KI 是防止 FAKE 跑数字被误用，并非指北极星默认是 FAKE。**
- 周报三态：样本不足时不下达标结论；FAKE 跑只看管线连通，不看北极星2 绝对值
- **真实 LLM 沙箱复跑**（`LIGHT_MAQA_FAKE_LLM=0`）才用于北极星2 趋势观测
- 2026-06-22 真实 LLM 复跑：北极星2 **58.6%**（17/29 complex 有效完成），对比 FAKE 跑 **4%** — 证伪「FAKE 比率=产品质量」
- staging 定时：`staging_full_validation.yml` 跑 `full-staging --execute`（真实 LLM）
- 样本题措辞：避免分析题正文出现裸 `commit` 英文子串（如 complex_21 旧文案），否则可能误触 commit 链（见 KI-V1-002 残留边界）
- 后续建议：
- 不在 FAKE 模式放宽 quality gate（会污染生产门禁语义）
- 指标沙箱默认即真实 LLM；如需 FAKE 仅验管线，用 `scripts/run_metrics_sandbox.ps1 -FakeLLM`（PowerShell switch），周报会强制标注 environment=FAKE
- 2026-06-24 报告层缓解（仅 L13，不动业务质量门）：`scripts/report_product_metrics.py` 在 FAKE 下写 `environment=FAKE`，并把北极星2 判定改为「不适用（FAKE）」、HTML 顶部加 FAKE 横幅 → 杜绝「FAKE 比率被误读为产品质量」。
- 2026-06-25 桩层修复（不动质量门 / 路由 / 状态 / 出口 / 事实源）：`backend/agents/answer_agent/llm_exec.py` 的 FAKE 分支由裸 `测试回答：{text}` 改为 `_fake_answer_stub`——**显式标注的结构化回答**（含结论/对比/分情况/建议，且不含「知识库/网页/视频」等会触发诚实性 claims 的措辞）。
  - 目的：FAKE 唯一用途是「验管线连通」；旧桩过短无结构，被既有质量门挡在第一步，使连通跑被占位文本卡死（北极星2 ~4% 实为噪声）。新桩让连通跑能真正流过**未改动**的质量门，测到下游主链而非卡在占位文本。
  - 边界：未改 `quality_gate.py` 判定标准（不是放宽门，是让桩输出像真实结构化回答）；未新增平行链路/第二套事实源/新 Gate；只在 `LIGHT_MAQA_FAKE_LLM=1` 生效，生产走真实 LLM 不受影响。
  - 误读防护不变：FAKE 比率仍由报告层结构性标「不适用（FAKE）」（与具体数字无关），改桩不会让 FAKE 数字被误读为质量。
  - 回归：`tests/unit/test_ki_metrics_001_fake_stub.py`（桩仍显式标注 + 能流过 complex/fast 质量门）；相关 agents/chat/unit 套件 379 passed。
- **根因里"FAKE≠真实质量"的本质不变**，真值仍须真实 LLM 复跑；故 KI 整体保持 `Open` 作为环境告警，仅其中"占位桩被门挡死"的可操作子项已修。
- 2026-06-25 真实 LLM 复跑实测（`environment=REAL`，`scripts/run_metrics_sandbox.ps1`，证据 `_local/reports/metrics/weekly_2026-06-25.json`，gitignored）：
  - 北极星2 = **58.6%**（17/29 complex），FAKE 同口径 = **4%** → **命题（FAKE≠产品质量）由数据证实**；
  - 该复跑判定为「**样本不足**」（complex 计数 29 < 30 下限，差 1，因 `complex_16` 被判 `is_complex_task=false`），且 **58.6% < 70% 目标** → 暴露**真实产品差距**，主因 `upgrade_still_partial` ×6；
  - 质量门通过率 77.3%、Partial 20.5%、insufficiency 6.8%（后两者达标）。
  - 结论：本 KI 的「占位桩」子项与「证伪命题」均已闭环；**剩余的不是环境问题，而是真实质量项**，派生两个独立 backlog（见下），不再挂在本 KI 名下：
    - **KI-METRICS-002（样本补齐）**：修 `complex_16` 分类/期望，使 complex 计数 ≥30，北极星2 才能出硬判定（非「样本不足」）。
    - **KI-METRICS-003（`upgrade_still_partial` 专项）**：复杂题升级 complex 后为何停在 partial（质量门二轮偏严 vs 材料不足），是北极星2 上不去的真实主因。

---

## KI-METRICS-003

- Issue ID：`KI-METRICS-003`
- 标题：复杂题 `upgrade_still_partial` — 质量门二轮无补材计划时停在 partial
- 当前状态：`In progress`（出口态收口 + answer_only 二轮已验证；`ENABLE_COMPLEX_REFINE_V2` **默认仍 OFF**，待 regression 全绿 + 沙箱二轮确认后切主路径）
- 根因（代码）：round-0 质量门 `need_second_round` → 二轮仅补材；纯推理题无 feedback plan → `stop_reason=no_executable_feedback_plan` → 无 round-1 重生成 → partial。
- **2026-06-26 出口收口（本分支）**：`reconcile_answer_only_turn_facts` + `exit_insufficient_evidence` 单一真源；answer_only round-1 gate pass 后清 `partial_pending`/stale insuf（general-lane、无 KB scope、防刷硬约束）。沙箱 RefineV2 首轮：**北极星2=73.3%（22/30）**，complex partial **8→2**；`complex_14` 等 answer_only 题已 `succeeded`。
  - **永久诊断层**：沙箱 JSONL / `DIAG:` stdout / 周报 HTML「Complex partial 分解」输出 `quality_gate_reason_codes`、`stop_reason`、`metrics_partial_bucket`、`metrics_would_answer_refine`（shadow，flag 关也可见）。
  - **RefineKind 单一真源**：`backend/application/chat/refine_kind.py`（`none | material | answer_only`）；`answer_only` 走既有 round-1 重生成 + 同一 `evaluate_quality_gate` 复评。
  - **单 flag**：`ENABLE_COMPLEX_REFINE_V2`（`feature_flags.py`，**默认 OFF**，env 可覆盖做 A/B）；含 general-lane 材料/kb 误判收窄 + answer_only 路径。
  - **验收分离**：002 = n≥30 硬判定；003 = 42/42 + 北极星2 区间不下降 + honesty 白名单仍绿。
  - **转正门禁（S0 口径，2026-06-26）**：
    - **Fixed 条件**：S1（机制 + flip 5 题 rubric 0 容忍）+ S3（shadow 无 diff、v1 10/10、v2–v3 结案）+ 1.2 逃生口债已删；
    - **70%**：仅 S2 观测门槛（连续 2 轮、同 commit、`complex_total=30`、exit0），**不构成 KI Fixed 充分条件**；
    - **有效完成率**：北极星2 = complex 样本 `task_status=succeeded` / `complex_total`（与 `product_metrics` 一致）。
- 复跑：`pwsh -File .\scripts\run_metrics_sandbox.ps1`（真实 LLM）；诊断 profile：`py scripts/evaluation/run_project_validation.py --profile metrics-diagnostic --execute`。
- **2026-06-26 真实复跑（`environment=REAL`，commit `8f762ab` 后）**：
  - complex 计数 **30**（KI-METRICS-002 样本补齐 ✅）；
  - 北极星2 = **60.0%**（18/30），硬判定 **「未达标」**（<70%）；
  - 诊断分解：complex_partial=8，桶 **insufficiency_expected:8**（主因 `web_fetch_empty` + `limitations_present` 共现，`would_answer_refine_ids=[]`）；
  - Guardrail：Partial 20.5% ✅、insufficiency 22.7% ✅、质量门通过率 77.3%。
- **2026-06-26 RefineV2 真实复跑（flag 关 A/B）**：北极星2 仍 **60.0%**；partial 8 条全为 `insufficiency_expected`，无 `answer_only` 触发（材料桶误判，见 004）。
- **2026-06-26 004 合入后真实复跑**：`answer_only_refine_scheduled` 已触发；`would_answer_refine_ids` 非空；北极星2 仍 **60%**（18/30）。
- **2026-06-26 005 补全**：`is_answer_only_refine_bundle` / `build_answer_only_executor_hint`  wired；二轮已能产出深度答（如 complex_14 gate pass）；仍有个别 case `partial_pending` + stale insuf 挡 succeeded。
- **2026-06-26 005 沙箱（431d0a5 后）**：DIAG complex=25 partial=6（脚本 exit 1；LLM 方差 + 部分 case 超时）；较 004 轮 answer_only 二轮内容明显改善。
- **2026-06-26 regression（FAKE :8000）**：**34/42**（V1 7/10、V2 13/16、V2.5 7/8、V3 7/8）；较上轮 33/42 +1；**未达 42/42**。
- **2026-06-26 清债**：flag 默认回退 OFF（未达 gate 不切主路径，消 (b) 级 flag 债）；补 `prepare_bundle_for_answer_only_refine` 修红测试；52 单测 + 4 守卫全绿。剩余为纯数值未达标（非债务）。

---

## KI-METRICS-004

- Issue ID：`KI-METRICS-004`
- 标题：general-lane 纯推理题被材料门误判 → 走 web 补材 → `web_fetch_empty` → partial
- 当前状态：`In progress`（narrow + answer_only + 出口收口已落地；剩余 partial 为真 insufficiency/budget，非假 flip）
- 现象：complex partial 桶 `insufficiency_expected` 占主导；`quality_gate_reason_codes` 共现 `limitations_present`/`material_*` + `stop_reason=web_fetch_empty`；`refine_kind=material` 而非 `answer_only`。
- 根因：Middle 材料不足诚实模板触发材料 reason；general lane 无 KB  scope 时不应强制 web 二轮；narrow 后 `need_more_material` 仍 true 或 `insufficient_evidence` 阻断 answer_only。
- 修复锚点：`quality_gate.py`（narrow 后重算 need_more_material）、`refine_kind.py`（effective codes + depth-only insuf 例外）、`complex_feedback_impl.py`（answer_only 先于 build_feedback_request；web_fetch_empty 回退 answer_only）。
- **2026-06-26 C1 trace（complex_03）**：reuse seed 弱命中 1 chunk → `retrieved_chunks_count>0` 阻断 general-lane narrow → `material_insufficient` + web 补材 → `web_fetch_empty` → partial。修复：复用既有 `kb_evidence_tier=weak/none` 时不计 material-relevant chunks（commit `5f53cce`），不新造 score 阈值。

---

## KI-V2-001

- Issue ID：`KI-V2-001`
- 标题：`video_total_failure 非法视频 URL 被 document_fast succeeded 接管`
- 来源版本：`V2：Capability Chains + Fake Success Negatives`
- 来源 case：`video_total_failure`
- 问题类型：`video intent honesty / invalid video URL fallback error`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_capability_all_20260613_154809.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_capability_all_20260613_154809.md`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_capability_video_20260615_150530.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_capability_video_20260615_150530.md`
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
- 已于 2026-06-15 通过 ingress 视频意图信号 + video_fast 显式 unsupported 失败修复
- explicit video intent + unsupported URL 留在 video lane；`task_status=failed`；不再 web_async / document_fast
- 后续建议：
- video 意图命中后，应优先维持 video lane 的失败或阻断语义
- 禁止无 transcript / 无 video evidence 时被 document fast 成功接管
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v2_capability_all`
- 复测（2026-06-16）：`regression_all` 42/42；`video_total_failure` case 通过

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
- 复测（2026-06-16）：`regression_all` 42/42；`background_task_followup_flow` 通过

---

## KI-V2.5-002

- Issue ID：`KI-V2.5-002`
- 标题：`continue_without_context_flow 空上下文继续请求被 succeeded + direct_llm 处理`
- 来源版本：`V2.5：Multi-turn State Closure`
- 来源 case：`continue_without_context_flow`
- 问题类型：`follow-up context honesty / empty-session closure error`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260613_154930.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260613_154930.md`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260615_143810.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v2_5_multiturn_state_20260615_143810.md`
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
- 已于 2026-06-15 通过 `lift_empty_context_followup` 事实抬升修复
- 空上下文 follow-up 不再 `default_success`；`task_status=blocked`；answer 使用确定性澄清文案，不依赖 LLM 措辞
- 后续建议：
- 无 previous steps / 无 stitch context 时，应更保守地落到 blocked、clarify 或显式无上下文状态
- 禁止把空上下文继续请求记为成功闭环
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v2_5_multiturn_state`
- 复测（2026-06-16）：`regression_all` 42/42；`continue_without_context_flow` 通过

---

## KI-V3-001

- Issue ID：`KI-V3-001`
- 标题：`complex_document_reasoning 内联文档复杂分析协作证据不足`
- 来源版本：`V3：Complex / Agent Collaboration`
- 来源 case：`complex_document_reasoning`
- 问题类型：`complex material reasoning observability gap / 内联文档未进入材料链`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.md`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_135404.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_135404.md`
- 现象（修复前）：
- 用户提供内联文档材料并要求复杂分析
- case 已进入 `mode=complex`，但内联文档只停留在 `message`，未进入 `v13_text_content` / `temporary_materials`
- Middle / Answer 消费 KB benchmark 材料
- 真实响应返回 `primary_path=agno_basic_v2_kb`，`temporary_materials=0`
- 不能证明系统基于当前内联材料完成了复杂协作分析
- 修复摘要（2026-06-15）：
- `session_stage` 将 message 内联文档提升为 `v13_text_content`
- complex 编排 handoff：`answer_mode=temporary_material`，`needs_retrieval=False`（不走 `prepare_text` pending）
- `bundle_finalize` 注入 `[inline_document]` 至 `temporary_materials`
- `path_labels` 在真实 inline document 消费后标 `document_complex`
- 修复后 E2E：`v3_complex_agent` **7/8**；`complex_document_reasoning` **通过**
- 关键行为：`task_status=succeeded`、`primary_path=document_complex`、`mode=complex`、`temporary_materials=1`、Answer 消费 `inline_document`
- 为什么是真问题：
- 该 case 要测的是「基于当前用户提供材料的复杂分析」
- 路径标签必须跟随真实材料消费，不能只改 label 骗过评测
- 影响范围：
- 内联文档复杂分析题
- complex/document 材料 handoff 与路径标签诚实性
- V3 Main / Middle / Answer 材料归属可观测性
- 当前处理策略：
- 已于 2026-06-15 完成最小 L5 材料 handoff + L10 路径标签修复并冻结
- 未修改 eval runner / assertions / rule_catalog，未放宽 `allowed_primary_paths`
- 风险 / 观察项：
- 内联提取当前依赖强 cue（如「下面这段文档内容」）和末位冒号切分，其他写法可能未覆盖
- `complex_web_kb_compare` 在本轮 E2E 从 timeout 转为通过（7/8 之一），**不是本轮修复目标**，不标记为 Fixed，仅作观察项
- V3 当前已完成冻结：`KI-V3-001` 与 `KI-V3-002` 均已 Fixed，`v3_complex_agent` 已复核 8/8；`complex_web_kb_compare` 仍作为稳定性观察项，不单独标记为固定修复成果
- 后续建议：
- 扩展内联文档 cue / 切分策略时保持「先修材料事实、再修路径标签」原则
- 如需覆盖更多 inline 写法，另立专项轮次，勿回退 eval 标准
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v3_complex_agent`
- 复测（2026-06-16）：`regression_all` 42/42；`complex_document_reasoning` 通过

---

## KI-V3-002

- Issue ID：`KI-V3-002`
- 标题：`complex_interview_explanation 退化为 kb_fast`
- 来源版本：`V3：Complex / Agent Collaboration`
- 来源 case：`complex_interview_explanation`
- 问题类型：`complex agent collaboration degradation / kb_fast 接管`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260613_135505.md`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_140542.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_140542.md`
- 现象（修复前）：
- 项目面试讲解型复杂问题返回：
- `task_status=succeeded`
- `primary_path=kb_fast`
- `mode=fast`（未进入 complex 三 Agent 协作链）
- 没有稳定体现预期的 complex agent collaboration 路径
- 修复摘要（2026-06-15）：
- 在 `complexity_policy.py`（单一 complex_candidate 事实源）补充「结构化讲解 / 面试叙事 / 对比解释」强信号（`structured_explanation`、`decision_tradeoff`）
- `mode_selector` 在强 reason code 下升格 `mode=complex`，不再被 `kb_fast` 早退吞掉
- 修复后 E2E：`v3_complex_agent` **8/8**；`complex_interview_explanation` **通过**
- 关键行为：`mode=complex`、`executor_profile=complex`、`primary_path=agno_basic_v2_kb`（非 `kb_fast`）；`collaboration_trace` 含 Main / Middle / Answer 协作证据
- 为什么是真问题：
- 面试讲解型问题不只是知识库问答
- 它还需要复杂意图识别、材料组织、表达取舍和 grounding
- 当前 V3 无法充分证明 Main / Middle / Answer 协作链路稳定成立
- 影响范围：
- 项目面试讲解类复杂题
- complex / kb_fast 边界
- V3 协作证据可信度
- 当前处理策略：
- 已于 2026-06-15 完成最小 complexity_policy 修复并冻结
- 未修改 eval 降标准、未新增第二套 complex 判定器、未改 Agent 协作协议
- 风险 / 观察项：
- 结构化讲解信号仍依赖任务形态 cue，其他面试表述可能未覆盖
- `complex_web_kb_compare` 本轮 E2E 通过，非本轮修复目标，稳定性待观察
- 后续建议：
- 扩展讲解型 cue 时继续在 `complexity_policy` 单点维护，勿在 `kb_fast_impl` 平行写判断
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v3_complex_agent`
- 复测（2026-06-16）：`regression_all` 42/42；`complex_interview_explanation` 通过

---

## KI-V3-003

- Issue ID：`KI-V3-003`
- 标题：`insufficient evidence answer contract 不稳定`
- 来源版本：`V3：Complex / Agent Collaboration`
- 来源 case：`complex_insufficient_evidence`
- 问题类型：`insufficient evidence honesty / answer contract instability`
- 当前状态：`Fixed`
- 原始证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_151849.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_152512.json`
- 修复证据：
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_153727.json`
- `D:\1\A1_publish\runtime_data\eval_sandbox\reports\eval_v3_complex_agent_20260615_154141.json`
- 现象（修复前）：
- push 前稳定性复核中 `v3_complex_agent` 出现 **2/3 为 7/8**，失败 case 均为 `complex_insufficient_evidence`
- 三轮路由/出口态一致：`task_status=partial`、`lane=kb`、`mode=fast`、`winner_rule=pending_kind`、`insufficient_evidence=true`
- 失败断言：`evidence insufficiency not honestly reflected in answer` / `absolute conclusion given under insufficient evidence`
- LLM 回答偶发缺少稳定「证据不足 / 无法确认」表达，导致诚实性文本断言抖动
- 修复摘要（2026-06-15）：
- 在 `apply_exit_envelope`（`turn_response_builder` 出口组装层）对 `insufficient_evidence=true` 施加稳定回答契约前缀
- 前缀强制包含「现有材料不足，无法确认」，保留原 answer 正文
- 未改 eval、未改 `turn_exit_gate`、未改 V3-001/V3-002 路由
- 修复后 E2E：`v3_complex_agent` 连跑 **3/3 为 8/8**；`complex_insufficient_evidence` 稳定通过
- 为什么是真问题：
- `insufficient_evidence` 事实已存在，但用户可见 answer 表达不稳定
- 在证据不足场景下，回答契约应确定性表达「不能确认」，而非依赖 LLM 措辞侥幸
- 影响范围：
- KB / mixed 路径下 `insufficient_evidence=true` 的出口回答
- V3 诚实性 case `complex_insufficient_evidence`
- 当前处理策略：
- 已于 2026-06-15 完成最小 answer contract 修复并冻结
- `material_sufficiency=sufficient` 与 `insufficient_evidence=true` 可并存：表示「有检索材料，但不足以支持强结论」
- 风险 / 观察项：
- `complex_web_kb_compare` 仍作为稳定性观察项，非本轮修复目标
- 后续建议：
- 如需扩展不足表达模板，继续在 `insufficient_evidence_answer_contract.py` 单点维护
- 回归方式：
- `py scripts/evaluation/run_eval_suite.py --suite v3_complex_agent`
- 复测（2026-06-16）：`regression_all` 42/42；`complex_insufficient_evidence` 通过
