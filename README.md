# LightMultiAgentQA

当前仓库的**现行目录口径**：

- `backend/`：后端源码与主链
- `frontend/`：前端源码
- `tests/`：分层测试
- `scripts/`：项目级操作脚本
- `data/`：可提交样本
- `_local/`：本地运行产物

当前只保留两条有效版本线：

- `V16`：Tool 集成与真实资料处理
- `V17`：三 Agent 架构与多来源协商

## 系统概述

用户请求
→ `POST /chat/agno`
→ **默认 fast profile 优先**；`complex_candidate` 由 ingress 判定，质量门控不通过则 **升级 complex profile**（Main→Middle→Answer）
→ tools 拿内容；KB 默认 **shared retrieval + auto**
→ knowledge 处理 pending / commit / retrieve
→ 返回 `answer + extra + trace`

路由与升级口径详见 `docs/current/17_默认路由_材料流与质量门控规则.md`。

## 检索主路口径

当前知识检索对业务侧统一只有一条默认主路：

- 默认检索策略：`auto`
- `keyword / semantic / hybrid`：仅保留给内部调试、验收和定向实验

`auto` 的真实落点由运行时条件决定：

- `EMBEDDING_ENABLED=1` 且 `rag_embeddings` 有数据：优先走 `hybrid`
- `EMBEDDING_ENABLED=0`：自动降级为 `keyword`（且不 commit 写向量）
- `hybrid` 失败：降级 `semantic`
- `semantic` 失败：再降级 `keyword`

因此，**对业务方不再承诺“当前系统默认就是 keyword 或 hybrid”**；真正执行路径以 trace 中的
`strategy_requested / strategy_used / auto_reason` 为准。

当前仓库默认运行值：

- `RETRIEVAL_MODE=auto`
- `EMBEDDING_ENABLED=1`
- `CHAT_SYNC_BUDGET_MS=30000`

也就是说，默认主路已升级到“优先 hybrid、失败再回退 keyword”，复杂题同步预算默认 30 秒。

## 目录边界

- `backend/agents/`：Main / Middle / Answer 三 Agent（**只消费**门控结果，不做路由/充分度/二轮决策）
- `backend/api/`：FastAPI 对外接口
- `backend/application/chat/`：单轮聊天主链编排（**见该目录 README**）
- `backend/application/ingress/`：lane / complex_candidate / 初始 profile
- `backend/services/capabilities/knowledge/`：KB 检索编排、充分度、pending
- `backend/tools/`：拿内容的能力层
- `backend/knowledge/`：知识材料管理（pending / commit / search / index）
- `backend/storage/`：数据库 / 文件 / 向量存储访问
- `backend/config/`：成本/安全/上传/URL 等规则
- `backend/core/`：错误模型、请求上下文、可观测性

## 聊天主链门控（高层）

| 层 | 落点 | 判什么 |
|----|------|--------|
| Ingress | `application/ingress/` | lane、complex_candidate、初始 executor profile |
| Shared retrieval | `application/chat/shared_material_prep.py` | KB snapshot（fast/complex 共用） |
| Quality gate | `application/chat/delivery_gate_flow.py` | 交付 / 升级 / 二轮 |
| Feedback gate | `services/execution/feedback_gate.py` | 二轮动作许可 |
| Approval gate | `application/chat/approval_gate_flow.py` | 用户确认 + **commit 执行闭环** |
| Material trace | `application/chat/material_flow.py` | 全路径 temporary / pending / committed |

**已拍板**：`multi_source_compare` 无豁免，与普通 complex 共用 `quality_gate` 二轮模型；material trace 与 trace baseline 必须全路径一致。

## 入口汇总（唯一入口）

| 用途 | 入口 |
|------|------|
| 后端启动 | 推荐 `python scripts/run_dev.py --backend`；等价手动：先设置 `PYTHONPATH` 指向 `backend/`（见下文），再 `python -m uvicorn api.main:app`。不要使用 `backend.api.main:app`，易与包路径不一致。 |
| 前端启动 | `cd frontend && npm run dev` |
| 聊天主链 | `backend/application/chat/run_chat_turn.py` |
| API 路由 | `backend/api/main.py` |
| OpenAPI 快照 | `docs/current/openapi.json`；刷新：`PYTHONPATH=backend python scripts/export_openapi.py docs/current/openapi.json` |
| CI | `.github/workflows/ci.yml`（pytest 覆盖率 **`--cov-fail-under=60`**；nightly KB benchmark 见 `nightly_benchmark.yml`） |
| 真实验收 | `.github/workflows/real_external.yml`（手动触发） |

## 启动方式

### 后端

```powershell
py -3.12 -m pip install -r requirements.lock
# 须配置 .env 中 DATABASE_URL=postgresql://…（见 .env.example）。本地可先启动 PostgreSQL
# 或仅起数据库：docker compose up -d postgres
py -3.12 scripts/run_dev.py --backend
```

若需**直接**启动 uvicorn（与 `run_dev.py` 一致：`PYTHONPATH` **仅**含 `backend/`，cwd 为仓库根）：

```powershell
$env:PYTHONPATH = "backend"
py -3.12 -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

多 worker（`>1` 时关闭 `--reload`）：`py -3.12 scripts/run_dev.py --backend --workers 4`。`Dockerfile` 中生产进程默认 **`uvicorn --workers 2`**。

对外提供或共享后端时，在 `.env` 中设置 **`API_BEARER_TOKEN`**（见 `.env.example`）。非空时除 `/health`、`/docs`、`/openapi.json`、`/redoc` 外，所有 API 须带请求头 **`Authorization: Bearer <与环境中相同的 token>`**；未设置该变量则与旧行为一致（本地开发可留空）。前端在 **`frontend/.env.local`** 设置 **`NEXT_PUBLIC_API_BEARER_TOKEN`**（与后端相同值）时，`frontend/lib/client.ts` 会自动为 API 请求附带该头；未设置则不发送 `Authorization`。

**运行数据与数据库**：服务端会话、任务、RAG、向量元数据等均落在 **PostgreSQL**。必须在 `.env` 配置 **`DATABASE_URL=postgresql://…`**（见 `.env.example`）；未配置则进程启动会失败。**生产/一体化运行**推荐 **`docker compose up`**（`docker-compose.yml` 已包含 `postgres` 与 `DATABASE_URL`）。本地可单独启动数据库：`docker compose up -d postgres`，再运行 `scripts/run_dev.py --backend`。pytest 默认期望本机或 CI 中已提供可用的 `DATABASE_URL`（与 compose 账号一致）。

（依赖以 `requirements.lock` 为准，由 `pyproject.toml` 经 `pip-compile` 生成。更新锁文件时请使用 **Python 3.12**（与本仓库 `Dockerfile` / 工具链一致）。当前锁文件默认覆盖 `dev + ocr + asr-local + test-pdf`，例如：`py -3.12 -m piptools compile pyproject.toml --extra dev --extra ocr --extra asr-local --extra test-pdf -o requirements.lock --strip-extras`。）

### 运行时外部依赖

`requirements.lock` 已覆盖 Python 包依赖，但以下运行时组件仍需按场景准备：

- Playwright 浏览器：`py -3.12 -m playwright install chromium`
- OCR 本地 fallback：默认文档 OCR 主路应走腾讯云等外部 provider；只有启用 `local_tesseract`，或腾讯 OCR 失败后希望自动回退本地 OCR 时，才需要系统安装 [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- 音视频处理：视频链在“无字幕 -> 抽音频 / 分段 -> 在线 ASR”这条路径上会真实依赖 `ffmpeg`

如果你只跑默认聊天主链、KB、网页和普通文档流程，Playwright 是最常见的额外依赖；`Tesseract` 不是默认必需项，`ffmpeg` 则主要在视频能力开启时需要。

### 前端

```powershell
cd frontend
npm install
npm run dev
```

与后端 **Bearer** 对齐：若后端启用了 `API_BEARER_TOKEN`，请在 `frontend/.env.local`（勿提交）写入 **`NEXT_PUBLIC_API_BEARER_TOKEN`**（值与后端一致）；未设置则浏览器请求不携带 `Authorization`。

## 测试

全部回归：

```powershell
python -m pytest -q
```

仅 smoke：

```powershell
python -m pytest -q -m smoke
```

CI 默认门禁：

```powershell
python -m pytest -q -m "not real_external"
```

按目录分层跑（默认 **不** 收集 `tests/legacy/` 考古用例）：

```powershell
python -m pytest -q tests/smoke tests/backend tests/integration tests/acceptance
```

可选：仅跑历史归档（V14 等，依赖已删除的 SQLite 测试桩；可能失败）：

```powershell
python -m pytest -q tests/legacy
```

## 目录总览

```text
项目代码/
├─ backend/
│  ├─ agents/
│  ├─ api/
│  ├─ application/chat/
│  ├─ config/
│  ├─ core/
│  ├─ knowledge/
│  ├─ llm/
│  ├─ rag/
│  ├─ services/
│  ├─ storage/
│  ├─ tools/
│  └─ video/
├─ frontend/
├─ tests/
│  ├─ unit/
│  ├─ backend/
│  ├─ integration/
│  ├─ smoke/
│  ├─ acceptance/
│  ├─ legacy/          # 历史测试（pytest 默认不收集）
│  ├─ _support/
│  ├─ _fixtures/
│  └─ fixtures/
├─ data/
├─ docs/
│  ├─ current/
│  ├─ archive/
│  └─ evidence/
├─ scripts/
├─ _local/
├─ pyproject.toml
├─ requirements.lock
└─ .env.example
```

## 文档入口

- `docs/current/01_架构与主路径.md`
- `docs/current/04_目标架构冻结与术语表.md`
- `docs/current/02_目录规则.md`
- `docs/current/03_运行说明.md`
- `docs/current/成本与外部能力边界.md`
- `AGENTS.md` — Agent 架构与规则说明

## Benchmark 约定

- `scripts/benchmarks/run_agent_eval.py` 与 `scripts/benchmarks/run_kb_agent_eval.py`
  默认都使用 `--runner local`
- `local` 表示直接调用当前工作区代码，不依赖外部 `127.0.0.1:8001` 服务进程
- 只有在明确要验证独立运行中的 HTTP 服务时，才使用 `--runner http`

这样可以避免 benchmark 误打到旧进程、旧配置或热重载不一致的运行态。

## 当前收口状态

- 目录迁移（R-001~R-018）：全部完成
- `backend/` 是唯一 Python 包根（`pythonpath = ["backend"]`）
- 旧顶层源码目录已全部删除
- 成本/安全/上传/URL 四层规则已建立
