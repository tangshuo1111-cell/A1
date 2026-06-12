# Redis 异步队列联调记录 (§15.8 / P9) — 已归档

> **归档说明**：本文是 P9 阶段一次性的 async 队列联调/签字记录（2026-05-22），
> 仅作历史存档，不代表当前运行手册。当前 `ENABLE_ASYNC_CONTROL_PLANE_V2` 已默认开启。

> **Date**: 2026-05-22  
> **Scope**: `tasks.queue.async_task_queue` + `workers.entry.task_plane_worker`

---

## 环境

| Item | Value |
|---|---|
| Queue backend (dev default) | `memory` |
| Redis URL (staging) | `REDIS_URL=redis://127.0.0.1:6379/0` |
| Worker entry | `workers.entry.task_plane_worker.ensure_task_plane_workers_started` |
| Dispatcher | `services.execution.async_dispatcher.process_async_task` |

---

## 联调步骤

1. 设置 `ENABLE_ASYNC_CONTROL_PLANE_V2=1`
2. 设置 `ASYNC_TASK_QUEUE_BACKEND=redis`（或项目等价 env）
3. 启动 API + task plane worker
4. 入队 `web_heavy_fetch` / `video_asr_background` / `document_ocr`
5. 轮询 `GET /tasks/{task_id}` 至 `succeeded` 或 `failed`

---

## 记录结果

| task_type | enqueue | dequeue | worker 执行 | /tasks API | 备注 |
|---|---|---|---|---|---|
| `video_asr_background` | PASS (memory) | PASS | PASS (mock ASR) | PASS | 单元测试 `test_async_task_contract` |
| `web_heavy_fetch` | PASS (memory) | PASS | PASS (monkeypatch) | PASS | `test_web_heavy_fetch_task_enters_shared_task_plane` |
| `document_ocr` | PASS (memory) | PASS | PASS (monkeypatch) | PASS | contract 含 document_ocr |
| `multi_source_research` | PASS (schema) | N/A | **optional** | FAIL expected | error_code=`multi_source_research_optional` |

---

## Redis staging 手测（待运维环境）

```bash
# 1. redis-cli ping → PONG
# 2. py -m pytest tests/migration/test_async_task_contract.py -q
# 3. 手动 POST 触发长视频 → 确认 task_id 在 Redis list 可见
```

**结论**: memory backend 全绿；Redis 路径 schema/contract 已就绪，staging 手测待运维 Redis 实例可用后补签字。

---

## 故障回滚

- 关 `ENABLE_ASYNC_CONTROL_PLANE_V2`
- 队列积压时切 `ASYNC_TASK_QUEUE_BACKEND=memory` 并重启 worker
