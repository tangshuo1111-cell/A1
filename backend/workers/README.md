# backend/workers

## Responsibilities

- 承载异步执行平面，是系统的后台执行层
- 负责消费队列、启动 worker、维护执行 runtime、提交后台结果
- 与 `tasks/` 配合实现 `Async Control Plane`
- 隔离后台执行细节，避免同步主链直接承担长期任务处理

## Boundary / What not to put here

- 不要把业务主判断或 lane 决策放进 `workers/`
- 不要把 HTTP 接口层和前端交互层放进这里
- 不要把平台状态机和任务查询主体逻辑塞进这里，那些属于 `tasks/`
- 不要继续维持重复目录和重复任务实现，后续应收敛为 entry / pools / runtimes

## Owned files

- `backend/workers/entry/`
- `backend/workers/tasks/`
- `backend/workers/task_trace_cache.py`
- `backend/workers/video_worker_pool.py`
- 未来预留：
  - `backend/workers/pools/`
  - `backend/workers/runtimes/`

## Files that must not keep growing

- `backend/workers/video_worker_pool.py`
  应收敛为执行资源管理，不应继续吸收任务编排与业务分支。
- `backend/workers/entry/video_task_worker.py`
  应保持 worker entry 协议简洁，不应承载视频后台处理核心。
- `backend/workers/tasks/task_runner.py`
  当前与 `backend/tasks/task_runner.py` 存在职责重叠，后续应清债，不应继续增长。
